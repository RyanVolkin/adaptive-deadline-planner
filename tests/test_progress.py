from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.db import transaction
from app.domain.estimation import EstimationEngine
from app.repositories import TaskRepository, WorkRecordRepository
from app.services.progress_service import ProgressService
from app.services.task_service import TaskNotFound, TaskService


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


@pytest.fixture
def progress(db_connection, user_id):
    return ProgressService(TaskRepository(db_connection), WorkRecordRepository(db_connection),
                           EstimationEngine(), None, lambda: transaction(db_connection, user_id),
                           clock=lambda: NOW)


@pytest.fixture
def new_task(db_connection, user_id):
    def create(estimate=600, due=NOW.date(), created=NOW - timedelta(days=2)):
        service = TaskService(TaskRepository(db_connection), WorkRecordRepository(db_connection),
                              EstimationEngine(), None, lambda: transaction(db_connection, user_id),
                              clock=lambda: created)
        return service.create_task(user_id, {
            "name": "Essay", "type": "homework", "priority": "medium",
            "original_estimate": str(estimate), "deadline": due.isoformat(),
        })
    return create


def records(db_connection, task):
    return WorkRecordRepository(db_connection).list_for_task(task.user_id, task.id)


def test_work_entries_update_estimate_using_total_time(progress, new_task, db_connection, user_id):
    task = new_task()
    tasks = TaskRepository(db_connection)
    progress.record_work(user_id, task.id, 50, 25)
    saved = tasks.get(user_id, task.id)
    assert (saved.adjusted_estimate, saved.remaining_work) == (400, 300)

    progress.record_work(user_id, task.id, 100, 25)
    progress.record_work(user_id, task.id, 0, 50)
    saved = tasks.get(user_id, task.id)
    assert (saved.adjusted_estimate, saved.remaining_work, saved.updated_at) == (450, 225, NOW)
    saved_entries = records(db_connection, task)
    assert [(r.minutes, r.completion_pct, r.created_at) for r in saved_entries] == [
        (50, 25, NOW), (100, 25, NOW), (0, 50, NOW),
    ]


def test_complete_overdue_task(progress, new_task, db_connection, user_id):
    yesterday = NOW.date() - timedelta(days=1)
    task = new_task(due=yesterday)
    for day in (yesterday, NOW.date(), NOW.date() + timedelta(days=1)):
        db_connection.execute(
            "INSERT INTO public.schedule_entries (task_id, user_id, date, minutes) "
            "VALUES (%s, %s, %s, 15)", (task.id, user_id, day),
        )
    progress.record_work(user_id, task.id, 50, 25)
    progress.record_work(user_id, task.id, 850, 100)
    saved = TaskRepository(db_connection).get(user_id, task.id)
    assert (saved.completion_pct, saved.remaining_work, saved.completed_at) == (100, 0, NOW)
    assert saved.adjusted_estimate == 400
    assert saved.estimate_ratio == 1.5
    assert new_task(120, created=NOW + timedelta(minutes=1)).starting_estimate == 180
    assert db_connection.execute(
        "SELECT date FROM public.schedule_entries WHERE task_id = %s", (task.id,),
    ).fetchall() == [{"date": yesterday}]
    with pytest.raises(ValueError):
        progress.record_work(user_id, task.id, 10, 100)
    assert len(records(db_connection, task)) == 2


def test_zero_time_completion_does_not_affect_history(progress, new_task, db_connection, user_id):
    task = new_task()
    progress.record_work(user_id, task.id, 0, 100)
    assert TaskRepository(db_connection).recent_ratios(user_id, "homework") == []


@pytest.mark.parametrize("minutes, pct", [(-1, 60), (2.5, 60), (2_147_483_648, 60), (5, -1), (5, 101),
                                         (5, 50.5), (5, 40), (0, 50)])
def test_invalid_entry_leaves_task_unchanged(progress, new_task, db_connection, user_id, minutes, pct):
    task = new_task()
    progress.record_work(user_id, task.id, 60, 50)
    tasks = TaskRepository(db_connection)
    before = tasks.get(user_id, task.id)
    with pytest.raises(ValueError):
        progress.record_work(user_id, task.id, minutes, pct)
    assert tasks.get(user_id, task.id) == before
    assert len(records(db_connection, task)) == 1


def test_other_users_work_is_private(progress, new_task, db_connection, user_id, other_user_id):
    task = new_task()
    progress.record_work(user_id, task.id, 15, 10)
    assert WorkRecordRepository(db_connection).list_for_task(other_user_id, task.id) == []
    with pytest.raises(TaskNotFound):
        progress.record_work(other_user_id, task.id, 50, 25)
    assert len(records(db_connection, task)) == 1


def test_progress_regenerates_schedule(progress, new_task, db_connection, user_id):
    task = new_task()

    def regenerate(owner):
        saved = TaskRepository(db_connection).get(owner, task.id)
        assert (saved.completion_pct, saved.remaining_work) == (25, 300)
        assert len(records(db_connection, task)) == 1
        db_connection.execute(
            "INSERT INTO public.schedule_entries (task_id, user_id, date, minutes) "
            "VALUES (%s, %s, %s, 60)", (task.id, owner, NOW.date()),
        )

    progress.schedules = Mock()
    progress.schedules.regenerate.side_effect = regenerate
    progress.record_work(user_id, task.id, 50, 25)
    progress.schedules.regenerate.assert_called_once_with(user_id)
    assert db_connection.execute(
        "SELECT minutes FROM public.schedule_entries WHERE task_id = %s", (task.id,),
    ).fetchall() == [{"minutes": 60}]


def test_schedule_failure_rolls_back_progress(progress, new_task, db_connection, user_id):
    class FailingSchedule:
        def regenerate(self, user_id):
            db_connection.execute(
                "UPDATE public.schedule_entries SET minutes = 1 WHERE user_id = %s", (user_id,),
            )
            raise RuntimeError("schedule failed")

    task = new_task()
    db_connection.execute(
        "INSERT INTO public.schedule_entries (task_id, user_id, date, minutes) "
        "VALUES (%s, %s, %s, 60)", (task.id, user_id, NOW.date()),
    )
    progress.schedules = FailingSchedule()
    with pytest.raises(RuntimeError, match="schedule failed"):
        progress.record_work(user_id, task.id, 50, 25)
    assert TaskRepository(db_connection).get(user_id, task.id) == task
    assert records(db_connection, task) == []
    assert db_connection.execute(
        "SELECT minutes FROM public.schedule_entries WHERE task_id = %s", (task.id,),
    ).fetchall() == [{"minutes": 60}]
