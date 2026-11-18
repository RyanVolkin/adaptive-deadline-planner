from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.domain.scheduling import ScheduleEntry
from app.domain.task import Task
from app.services.schedule_service import ScheduleService


TODAY = date(2026, 11, 17)
USER_ID = "user-id"


def make_task(task_id, remaining_work=60):
    return Task(
        id=task_id,
        user_id=USER_ID,
        name=f"Task {task_id}",
        type="homework",
        priority="medium",
        deadline=TODAY,
        original_estimate=remaining_work,
        starting_estimate=remaining_work,
        adjusted_estimate=remaining_work,
        remaining_work=remaining_work,
        created_at=TODAY,
        updated_at=TODAY,
    )


@pytest.fixture
def dependencies():
    tasks = [make_task(1), make_task(2)]
    task_repo = Mock()
    task_repo.list_incomplete.return_value = tasks
    availability_service = Mock()
    availability_service.has_availability.return_value = True
    availability_service.get_week.return_value = [60] * 7
    schedule_repo = Mock()
    scheduler = Mock()
    entries = [ScheduleEntry(TODAY, 1, 60)]
    scheduler.generate.return_value = entries
    return (
        tasks, task_repo, availability_service, schedule_repo, scheduler, entries
    )


def make_service(dependencies, risk_detector=None, clock=lambda: TODAY):
    _, task_repo, availability_service, schedule_repo, scheduler, _ = dependencies
    return ScheduleService(
        task_repo, availability_service, schedule_repo, scheduler,
        risk_detector=risk_detector, clock=clock,
    )


def test_availability_needed_does_not_schedule(dependencies):
    dependencies[2].has_availability.return_value = False
    service = make_service(dependencies)

    assert service.regenerate(USER_ID) == "AVAILABILITY_NEEDED"
    dependencies[1].list_incomplete.assert_not_called()
    dependencies[4].generate.assert_not_called()
    dependencies[3].replace_for_user.assert_not_called()


def test_regenerate_passes_inputs_and_saves_generated_entries(dependencies):
    service = make_service(dependencies)

    assert service.regenerate(USER_ID) == "PLAN_UPDATED"

    dependencies[1].list_incomplete.assert_called_once_with(USER_ID)
    dependencies[2].get_week.assert_called_once_with(USER_ID)
    dependencies[4].generate.assert_called_once_with(
        dependencies[0], [60] * 7, TODAY, set()
    )
    dependencies[3].replace_for_user.assert_called_once_with(
        USER_ID, dependencies[5]
    )


def test_regenerate_uses_risk_detector_ids_and_explicit_today(dependencies):
    detector = Mock()
    detector.at_risk_tasks.return_value = [
        SimpleNamespace(task=dependencies[0][1]),
    ]
    explicit_today = date(2026, 11, 18)
    service = make_service(dependencies, detector, clock=lambda: TODAY)

    service.regenerate(USER_ID, explicit_today)

    detector.at_risk_tasks.assert_called_once_with(
        dependencies[0], [60] * 7, explicit_today
    )
    dependencies[4].generate.assert_called_once_with(
        dependencies[0], [60] * 7, explicit_today, {2}
    )


def test_regenerate_uses_injected_clock_when_today_omitted(dependencies):
    service = make_service(dependencies, clock=lambda: TODAY)

    service.regenerate(USER_ID)

    assert dependencies[4].generate.call_args.args[2] == TODAY


def test_no_incomplete_tasks_still_replaces_with_empty_list(dependencies):
    dependencies[1].list_incomplete.return_value = []
    dependencies[4].generate.return_value = []
    service = make_service(dependencies)

    service.regenerate(USER_ID)

    dependencies[3].replace_for_user.assert_called_once_with(USER_ID, [])


def test_scheduler_exception_propagates_without_replacing(dependencies):
    dependencies[4].generate.side_effect = RuntimeError("schedule failed")
    service = make_service(dependencies)

    with pytest.raises(RuntimeError, match="schedule failed"):
        service.regenerate(USER_ID)

    dependencies[3].replace_for_user.assert_not_called()


def test_get_daily_plan_maps_stored_entries_and_skips_missing_tasks(dependencies):
    entries = [
        ScheduleEntry(TODAY, 2, 30),
        ScheduleEntry(TODAY, 99, 15),
        ScheduleEntry(TODAY, 1, 45),
    ]
    dependencies[3].get_for_date.return_value = entries
    service = make_service(dependencies)

    assert service.get_daily_plan(USER_ID, TODAY) == [
        (dependencies[0][1], 30),
        (dependencies[0][0], 45),
    ]
    dependencies[1].list_incomplete.assert_called_once_with(USER_ID)


def test_get_daily_plan_returns_empty_without_entries(dependencies):
    dependencies[3].get_for_date.return_value = []
    service = make_service(dependencies)

    assert service.get_daily_plan(USER_ID, TODAY) == []
    dependencies[1].list_incomplete.assert_not_called()


def test_get_weekly_plan_groups_entries_by_all_seven_days(dependencies):
    entries = [
        ScheduleEntry(TODAY, 1, 30),
        ScheduleEntry(TODAY + timedelta(days=2), 2, 45),
    ]
    dependencies[3].get_for_week.return_value = entries
    service = make_service(dependencies)

    plan = service.get_weekly_plan(USER_ID, TODAY)

    assert [day for day, _ in plan] == [
        TODAY + timedelta(days=offset)
        for offset in range(7)
    ]
    assert plan[0][1] == [(dependencies[0][0], 30)]
    assert plan[2][1] == [(dependencies[0][1], 45)]
    assert all(not day_plan for _, day_plan in plan[1:2] + plan[3:])
    dependencies[3].get_for_week.assert_called_once_with(
        USER_ID, TODAY, TODAY + timedelta(days=6)
    )


def test_get_alerts_without_detector_returns_empty(dependencies):
    service = make_service(dependencies)

    assert service.get_alerts(USER_ID) == []
    dependencies[1].list_incomplete.assert_not_called()


def test_get_alerts_returns_missed_before_at_risk(dependencies):
    detector = Mock()
    missed = [SimpleNamespace(kind="missed")]
    at_risk = [SimpleNamespace(kind="risk")]
    detector.missed_deadlines.return_value = missed
    detector.at_risk_tasks.return_value = at_risk
    service = make_service(dependencies, detector)

    assert service.get_alerts(USER_ID) == missed + at_risk
    detector.missed_deadlines.assert_called_once_with(dependencies[0], TODAY)
    detector.at_risk_tasks.assert_called_once_with(
        dependencies[0], [60] * 7, TODAY
    )


def test_get_alerts_without_availability_returns_only_missed(dependencies):
    dependencies[2].has_availability.return_value = False
    detector = Mock()
    missed = [SimpleNamespace(kind="missed")]
    detector.missed_deadlines.return_value = missed
    service = make_service(dependencies, detector)

    assert service.get_alerts(USER_ID) == missed
    detector.at_risk_tasks.assert_not_called()
    dependencies[2].get_week.assert_not_called()
