from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.db import transaction
from app.estimation import EstimationEngine
from app.repositories import TaskRepository, WorkRecordRepository
from app.task import Task
from app.task_service import TaskService


NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def make_task(db_connection):
    repository = TaskRepository(db_connection)

    def create(owner, **changes):
        values = {
            "user_id": owner, "name": "Essay", "type": "homework",
            "priority": "medium", "deadline": NOW.date(),
            "original_estimate": 120, "starting_estimate": 120,
            "adjusted_estimate": 100, "remaining_work": 75,
            "completion_pct": 25, "created_at": NOW, "updated_at": NOW,
        }
        values.update(changes)
        task = Task(**values)
        task.id = repository.insert(owner, task)
        return task

    return create


def test_task_roundtrip_and_scoped_reads(db_connection, user_id, other_user_id, make_task):
    repository = TaskRepository(db_connection)
    task = make_task(user_id)
    other_task = make_task(other_user_id, name="Other essay")

    assert repository.get(user_id, task.id) == task
    assert isinstance(repository.get(user_id, task.id).user_id, str)
    assert repository.get(other_user_id, task.id) is None
    assert repository.list_by_user(user_id) == [task]
    assert repository.list_by_user(other_user_id) == [other_task]


def test_task_reads_ignore_extra_columns(db_connection, user_id, make_task):
    repository = TaskRepository(db_connection)
    task = make_task(user_id)
    db_connection.execute("ALTER TABLE public.tasks ADD COLUMN test_extra_column text")
    try:
        assert repository.get(user_id, task.id) == task
        assert repository.list_by_user(user_id) == [task]
    finally:
        db_connection.execute("ALTER TABLE public.tasks DROP COLUMN test_extra_column")


def test_update_and_delete_require_the_owner(db_connection, user_id, other_user_id, make_task):
    repository = TaskRepository(db_connection)
    task = make_task(user_id)
    task.name = "Changed"

    repository.update(other_user_id, task)
    repository.delete(other_user_id, task.id)
    assert repository.get(user_id, task.id).name == "Essay"

    repository.update(user_id, task)
    assert repository.get(user_id, task.id).name == "Changed"
    repository.delete(user_id, task.id)
    assert repository.get(user_id, task.id) is None


def test_history_uses_latest_five_usable_matching_tasks(
        db_connection, user_id, other_user_id, make_task):
    for ratio, days in [(1.1, 3), (1.2, 1), (1.3, 2), (1.4, 2), (1.5, 0), (1.6, -1)]:
        make_task(user_id, completion_pct=100, remaining_work=0,
                  estimate_ratio=ratio, completed_at=NOW + timedelta(days=days))
    make_task(other_user_id, completion_pct=100, remaining_work=0,
              estimate_ratio=1.8, completed_at=NOW + timedelta(days=10))
    make_task(user_id, type="reading", completion_pct=100, remaining_work=0,
              estimate_ratio=1.9, completed_at=NOW + timedelta(days=10))
    make_task(user_id, completion_pct=100, remaining_work=0,
              estimate_ratio=None, completed_at=NOW + timedelta(days=10))
    make_task(user_id, estimate_ratio=1.7, completed_at=NOW + timedelta(days=10))

    repository = TaskRepository(db_connection)
    assert repository.recent_ratios(user_id, "homework") == pytest.approx(
        [1.1, 1.4, 1.3, 1.2, 1.5]
    )
    assert repository.recent_ratios(user_id, "homework", 2) == pytest.approx([1.1, 1.4])
    assert repository.recent_ratios(user_id, "project") == []


def test_work_totals_are_scoped_to_the_owner(db_connection, user_id, other_user_id, make_task):
    task = make_task(user_id)
    repository = WorkRecordRepository(db_connection)
    assert repository.sum_minutes(user_id, task.id) == 0
    for minutes, pct in [(15, 10), (20, 25)]:
        db_connection.execute(
            "INSERT INTO public.work_records (task_id, minutes, completion_pct, created_at) "
            "VALUES (%s, %s, %s, %s)", (task.id, minutes, pct, NOW),
        )
    assert repository.sum_minutes(user_id, task.id) == 35
    assert repository.sum_minutes(other_user_id, task.id) == 0


def test_deleting_task_removes_work_and_schedule_entries(db_connection, user_id, make_task):
    task = make_task(user_id)
    db_connection.execute(
        "INSERT INTO public.work_records (task_id, minutes, completion_pct, created_at) "
        "VALUES (%s, 30, 25, %s)", (task.id, NOW),
    )
    db_connection.execute(
        "INSERT INTO public.schedule_entries (task_id, user_id, date, minutes) "
        "VALUES (%s, %s, %s, 30)", (task.id, user_id, NOW.date()),
    )
    TaskRepository(db_connection).delete(user_id, task.id)
    assert db_connection.execute(
        "SELECT count(*) AS count FROM public.work_records WHERE task_id = %s", (task.id,),
    ).fetchone()["count"] == 0
    assert db_connection.execute(
        "SELECT count(*) AS count FROM public.schedule_entries WHERE task_id = %s", (task.id,),
    ).fetchone()["count"] == 0


@pytest.fixture
def failing_schedule_service(db_connection, user_id, make_task):
    task = make_task(user_id)
    db_connection.execute(
        "INSERT INTO public.work_records (task_id, minutes, completion_pct, created_at) "
        "VALUES (%s, 30, 25, %s)", (task.id, NOW),
    )
    db_connection.execute(
        "INSERT INTO public.schedule_entries (task_id, user_id, date, minutes) "
        "VALUES (%s, %s, %s, 30)", (task.id, user_id, NOW.date()),
    )

    class FailingSchedule:
        def regenerate(self, owner):
            db_connection.execute(
                "DELETE FROM public.schedule_entries WHERE user_id = %s", (owner,),
            )
            raise RuntimeError("Schedule failed")

    repository = TaskRepository(db_connection)
    service = TaskService(
        repository, WorkRecordRepository(db_connection), EstimationEngine(),
        FailingSchedule(), lambda: transaction(db_connection, user_id), clock=lambda: NOW,
    )
    return service, task


def assert_task_and_related_rows_unchanged(db_connection, user_id, task):
    assert TaskRepository(db_connection).list_by_user(user_id) == [task]
    assert WorkRecordRepository(db_connection).sum_minutes(user_id, task.id) == 30
    assert db_connection.execute(
        "SELECT task_id, minutes FROM public.schedule_entries WHERE user_id = %s", (user_id,),
    ).fetchall() == [{"task_id": task.id, "minutes": 30}]


def test_create_rolls_back_when_scheduling_fails(
        db_connection, user_id, failing_schedule_service):
    service, task = failing_schedule_service
    data = {
        "name": "Changed", "type": "homework", "priority": "high",
        "deadline": NOW.date().isoformat(), "original_estimate": "240",
    }
    with pytest.raises(RuntimeError, match="Schedule failed"):
        service.create_task(user_id, data)
    assert_task_and_related_rows_unchanged(db_connection, user_id, task)


def test_update_rolls_back_when_scheduling_fails(
        db_connection, user_id, failing_schedule_service):
    service, task = failing_schedule_service
    data = {
        "name": "Changed", "type": "homework", "priority": "high",
        "deadline": NOW.date().isoformat(), "original_estimate": "240",
    }
    with pytest.raises(RuntimeError, match="Schedule failed"):
        service.update_task(user_id, task.id, data)
    assert_task_and_related_rows_unchanged(db_connection, user_id, task)


def test_delete_rolls_back_when_scheduling_fails(
        db_connection, user_id, failing_schedule_service):
    service, task = failing_schedule_service
    with pytest.raises(RuntimeError, match="Schedule failed"):
        service.delete_task(user_id, task.id, confirmed=True)
    assert_task_and_related_rows_unchanged(db_connection, user_id, task)


def test_database_checks_ranges_and_schedule_ownership(
        db_connection, user_id, other_user_id, make_task):
    task = make_task(user_id)
    with pytest.raises(psycopg.IntegrityError):
        db_connection.execute(
            "UPDATE public.tasks SET original_estimate = 0 WHERE id = %s", (task.id,),
        )
    with pytest.raises(psycopg.IntegrityError):
        db_connection.execute(
            "INSERT INTO public.work_records (task_id, minutes, completion_pct, created_at) "
            "VALUES (%s, -1, 25, %s)", (task.id, NOW),
        )
    with pytest.raises(psycopg.IntegrityError):
        db_connection.execute(
            "INSERT INTO public.schedule_entries (task_id, user_id, date, minutes) "
            "VALUES (%s, %s, %s, 30)", (task.id, other_user_id, NOW.date()),
        )


def test_planner_tables_are_not_exposed_to_api_roles(db_connection):
    tables = ("tasks", "work_records", "schedule_entries")
    for table in tables:
        assert db_connection.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass",
            (f"public.{table}",),
        ).fetchone()["relrowsecurity"] is True
        for role in ("anon", "authenticated"):
            assert db_connection.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT, INSERT, UPDATE, DELETE') AS allowed",
                (role, f"public.{table}"),
            ).fetchone()["allowed"] is False
