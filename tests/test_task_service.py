from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from app.estimation import EstimationEngine
from app.task import MAX_ORIGINAL_ESTIMATE, Task, TaskState
from app.task_service import TaskService


NOW = datetime(2026, 10, 20, 12)
TODAY = NOW.date()
USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def data():
    return {
        "name": " Essay ", "type": "homework", "priority": "medium",
        "deadline": TODAY.isoformat(), "original_estimate": "600",
    }


@pytest.fixture
def task():
    return Task(
        id=12, user_id=USER_ID, name="Essay", type="homework", priority="medium",
        deadline=TODAY, original_estimate=600, starting_estimate=600,
        adjusted_estimate=400, remaining_work=300, completion_pct=25,
        created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def setup(task):
    calls = Mock()
    calls.tasks.get.return_value = task
    calls.tasks.insert.return_value = 12
    calls.tasks.recent_ratios.return_value = []
    calls.work_records.sum_minutes.return_value = 50

    @contextmanager
    def transaction():
        # Records transaction order without simulating database rollback.
        calls.begin()
        try:
            yield
        except Exception:
            calls.rollback()
            raise
        else:
            calls.commit()

    service = TaskService(
        calls.tasks, calls.work_records, EstimationEngine(), calls.schedules,
        transaction, clock=lambda: NOW,
    )
    return service, calls


@pytest.mark.parametrize("days, pct, expected", [
    (-1, 25, TaskState.OVERDUE),
    (0, 25, TaskState.ACTIVE),
    (1, 25, TaskState.ACTIVE),
    (-1, 100, TaskState.COMPLETED),
])
def test_task_state(task, days, pct, expected):
    task.deadline = TODAY + timedelta(days=days)
    task.completion_pct = pct
    assert task.state(TODAY) == expected
    assert task.is_complete() == (pct == 100)


@pytest.mark.parametrize("field, value", [
    ("name", " "), ("name", "x" * 101),
    ("original_estimate", "0"), ("original_estimate", "1.5"),
    ("original_estimate", str(MAX_ORIGINAL_ESTIMATE + 1)),
    ("original_estimate", "9" * 5000),
    ("deadline", "2026-10-19"), ("deadline", "2026-02-30"),
    ("type", "unknown"), ("priority", "urgent"),
])
def test_invalid_task_is_not_saved(setup, data, field, value):
    service, calls = setup
    data[field] = value
    with pytest.raises(ValueError) as error:
        service.create_task(USER_ID, data)
    assert field in error.value.args[0]
    assert calls.mock_calls == []


def test_missing_fields_are_reported(setup):
    service, calls = setup
    assert set(service.validate({}, TODAY)) == {
        "name", "original_estimate", "deadline", "type", "priority",
    }
    assert calls.mock_calls == []


def test_largest_storable_estimate_is_accepted(setup, data):
    service, calls = setup
    data["original_estimate"] = str(MAX_ORIGINAL_ESTIMATE)
    assert service.validate(data, TODAY) == {}


@pytest.mark.parametrize("ratios, expected", [([], 600), ([1.5], 900)])
def test_create_task(setup, data, ratios, expected):
    service, calls = setup
    calls.tasks.recent_ratios.return_value = ratios
    task = service.create_task(USER_ID, data)
    assert (task.id, task.user_id, task.name) == (12, USER_ID, "Essay")
    assert (task.starting_estimate, task.adjusted_estimate,
            task.remaining_work) == (expected, expected, expected)
    assert task.original_estimate == 600
    assert task.completion_pct == 0
    assert task.created_at == task.updated_at == NOW
    calls.tasks.recent_ratios.assert_called_once_with(USER_ID, "homework", 5)
    calls.tasks.insert.assert_called_once_with(USER_ID, task)
    calls.schedules.regenerate.assert_called_once_with(USER_ID)
    assert [call[0] for call in calls.mock_calls] == [
        "begin", "tasks.recent_ratios", "tasks.insert",
        "schedules.regenerate", "commit",
    ]


@pytest.mark.parametrize("field, value, starting, adjusted, remaining", [
    ("type", "reading", 900, 550, 413),
    ("original_estimate", "300", 450, 325, 244),
])
def test_estimate_edits_use_saved_progress(
        setup, data, field, value, starting, adjusted, remaining):
    service, calls = setup
    calls.tasks.recent_ratios.return_value = [1.5]
    data[field] = value
    task = service.update_task(USER_ID, 12, data)
    assert (task.starting_estimate, task.adjusted_estimate,
            task.remaining_work) == (starting, adjusted, remaining)
    assert task.completion_pct == 25
    calls.tasks.get.assert_called_once_with(USER_ID, 12)
    calls.tasks.recent_ratios.assert_called_once_with(USER_ID, data["type"], 5)
    calls.work_records.sum_minutes.assert_called_once_with(USER_ID, 12)
    calls.tasks.update.assert_called_once_with(USER_ID, task)
    calls.schedules.regenerate.assert_called_once_with(USER_ID)


def test_other_edits_keep_existing_estimates(setup, data):
    service, calls = setup
    data.update(name="Revised essay", priority="high", deadline="2026-10-21")
    task = service.update_task(USER_ID, 12, data)
    assert (task.name, task.priority, task.deadline.isoformat()) == (
        "Revised essay", "high", "2026-10-21",
    )
    assert (task.starting_estimate, task.adjusted_estimate,
            task.remaining_work) == (600, 400, 300)
    calls.tasks.recent_ratios.assert_not_called()
    calls.work_records.sum_minutes.assert_not_called()


def test_edit_with_past_deadline_is_not_saved(setup, data, task):
    service, calls = setup
    task.deadline = TODAY - timedelta(days=1)
    data["deadline"] = task.deadline.isoformat()
    with pytest.raises(ValueError) as error:
        service.update_task(USER_ID, 12, data)
    assert "deadline" in error.value.args[0]
    calls.tasks.update.assert_not_called()
    calls.schedules.regenerate.assert_not_called()
    calls.rollback.assert_called_once()


def test_completed_task_cannot_be_edited(setup, data, task):
    service, calls = setup
    task.completion_pct = 100
    with pytest.raises(ValueError) as error:
        service.update_task(USER_ID, 12, data)
    assert error.value.args[0] == {"task": "Completed tasks cannot be edited."}
    calls.tasks.update.assert_not_called()
    calls.schedules.regenerate.assert_not_called()
    calls.rollback.assert_called_once()


def test_completed_task_can_be_deleted(setup, task):
    service, calls = setup
    task.completion_pct = 100
    service.delete_task(USER_ID, 12, confirmed=True)
    calls.tasks.delete.assert_called_once_with(USER_ID, 12)
    calls.schedules.regenerate.assert_called_once_with(USER_ID)


def test_update_rejects_missing_task(setup, data):
    service, calls = setup
    calls.tasks.get.return_value = None
    with pytest.raises(ValueError) as error:
        service.update_task(USER_ID, 12, data)
    assert error.value.args[0] == {"task": "Task not found."}
    calls.tasks.get.assert_called_once_with(USER_ID, 12)
    calls.tasks.update.assert_not_called()
    calls.schedules.regenerate.assert_not_called()
    calls.rollback.assert_called_once()


def test_update_rejects_another_users_task(setup, data, task):
    service, calls = setup
    task.user_id = "00000000-0000-0000-0000-000000000002"
    with pytest.raises(ValueError) as error:
        service.update_task(USER_ID, 12, data)
    assert error.value.args[0] == {"task": "Task not found."}
    calls.tasks.get.assert_called_once_with(USER_ID, 12)
    calls.tasks.update.assert_not_called()
    calls.schedules.regenerate.assert_not_called()
    calls.rollback.assert_called_once()


def test_delete_rejects_missing_task(setup):
    service, calls = setup
    calls.tasks.get.return_value = None
    with pytest.raises(ValueError) as error:
        service.delete_task(USER_ID, 12, confirmed=True)
    assert error.value.args[0] == {"task": "Task not found."}
    calls.tasks.get.assert_called_once_with(USER_ID, 12)
    calls.tasks.delete.assert_not_called()
    calls.schedules.regenerate.assert_not_called()
    calls.rollback.assert_called_once()


def test_delete_rejects_another_users_task(setup, task):
    service, calls = setup
    task.user_id = "00000000-0000-0000-0000-000000000002"
    with pytest.raises(ValueError) as error:
        service.delete_task(USER_ID, 12, confirmed=True)
    assert error.value.args[0] == {"task": "Task not found."}
    calls.tasks.get.assert_called_once_with(USER_ID, 12)
    calls.tasks.delete.assert_not_called()
    calls.schedules.regenerate.assert_not_called()
    calls.rollback.assert_called_once()


@pytest.mark.parametrize("confirmed", [False, "false"])
def test_deletion_requires_confirmation(setup, confirmed):
    service, calls = setup
    with pytest.raises(ValueError) as error:
        service.delete_task(USER_ID, 12, confirmed=confirmed)
    assert error.value.args[0] == {"task": "Confirm task deletion first."}
    assert calls.mock_calls == []


def test_list_tasks_uses_the_current_user(setup, task):
    service, calls = setup
    calls.tasks.list_by_user.return_value = [task]
    assert service.list_tasks(USER_ID) == [task]
    calls.tasks.list_by_user.assert_called_once_with(USER_ID)


def test_schedule_failure_exits_without_committing(setup, data):
    service, calls = setup
    calls.schedules.regenerate.side_effect = RuntimeError("Schedule failed")
    with pytest.raises(RuntimeError, match="Schedule failed"):
        service.create_task(USER_ID, data)
    calls.tasks.insert.assert_called_once()
    calls.rollback.assert_called_once()
    calls.commit.assert_not_called()
