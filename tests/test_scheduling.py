from datetime import date, datetime, timedelta

import pytest

from app.domain.scheduling import ScheduleEntry, Scheduler
from app.domain.task import Task


TODAY = date(2026, 11, 17)


def availability_for_dates(capacities):
    weekly = [0] * 7
    for day, minutes in capacities.items():
        weekly[day.weekday()] = minutes
    return weekly


def task(task_id, deadline, priority="medium", remaining_work=60):
    return Task(
        user_id="user",
        name=f"Task {task_id}",
        type="homework",
        priority=priority,
        deadline=deadline,
        original_estimate=remaining_work,
        starting_estimate=remaining_work,
        adjusted_estimate=remaining_work,
        remaining_work=remaining_work,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        id=task_id,
    )


def every_day(capacity, through=4):
    return [capacity] * 7


def test_spreads_work_with_a_one_day_buffer():
    entries = Scheduler().generate(
        [
            task(3, TODAY + timedelta(days=1), remaining_work=120),
            task(1, TODAY + timedelta(days=2), remaining_work=300),
            task(2, TODAY + timedelta(days=3), remaining_work=240),
        ],
        every_day(240),
        TODAY,
        set(),
    )

    assert entries == [
        ScheduleEntry(TODAY, 3, 120),
        ScheduleEntry(TODAY, 1, 120),
        ScheduleEntry(TODAY + timedelta(days=1), 1, 180),
        ScheduleEntry(TODAY + timedelta(days=1), 2, 60),
        ScheduleEntry(TODAY + timedelta(days=2), 2, 180),
    ]


def test_finished_first_task_does_not_stop_spreading_other_tasks():
    entries = Scheduler().generate(
        [
            task(1, TODAY + timedelta(days=1), remaining_work=60),
            task(2, TODAY + timedelta(days=2), remaining_work=180),
            task(3, TODAY + timedelta(days=2), remaining_work=180),
        ],
        every_day(240),
        TODAY,
        set(),
    )

    assert entries == [
        ScheduleEntry(TODAY, 1, 60),
        ScheduleEntry(TODAY, 2, 90),
        ScheduleEntry(TODAY, 3, 90),
        ScheduleEntry(TODAY + timedelta(days=1), 2, 90),
        ScheduleEntry(TODAY + timedelta(days=1), 3, 90),
    ]


def test_ample_capacity_does_not_use_deadline_day():
    deadline = TODAY + timedelta(days=2)
    entries = Scheduler().generate(
        [task(1, deadline, remaining_work=300)],
        every_day(240),
        TODAY,
        set(),
    )

    assert all(entry.date < deadline for entry in entries)
    assert len(entries) > 1


def test_work_ahead_uses_spare_capacity():
    deadline = TODAY + timedelta(days=3)
    entries = Scheduler().generate(
        [
            task(1, deadline, remaining_work=60),
            task(2, deadline, remaining_work=60),
        ],
        every_day(240),
        TODAY,
        set(),
    )

    assert all(entry.date < deadline - timedelta(days=1) for entry in entries)


def test_deadline_day_is_used_only_for_work_that_does_not_fit_before_it():
    deadline = TODAY + timedelta(days=1)
    entries = Scheduler().generate(
        [task(1, deadline, remaining_work=120)],
        availability_for_dates({TODAY: 60, deadline: 60}),
        TODAY,
        set(),
    )

    assert entries == [
        ScheduleEntry(TODAY, 1, 60),
        ScheduleEntry(deadline, 1, 60),
    ]


def test_due_today_uses_deadline_day():
    entries = Scheduler().generate(
        [task(1, TODAY, remaining_work=60)],
        availability_for_dates({TODAY: 60}),
        TODAY,
        set(),
    )

    assert entries == [ScheduleEntry(TODAY, 1, 60)]


def test_no_earlier_capacity_uses_deadline_day():
    deadline = TODAY + timedelta(days=2)
    entries = Scheduler().generate(
        [task(1, deadline, remaining_work=60)],
        availability_for_dates({deadline: 60}),
        TODAY,
        set(),
    )

    assert entries == [ScheduleEntry(deadline, 1, 60)]


def test_ordering_at_risk_then_deadline_then_priority_then_id():
    entries = Scheduler().generate(
        [
            task(4, TODAY, "low", 10),
            task(3, TODAY, "high", 10),
            task(2, TODAY, "medium", 10),
            task(1, TODAY + timedelta(days=1), "high", 10),
        ],
        availability_for_dates({TODAY: 25}),
        TODAY,
        {1},
    )

    assert [entry.task_id for entry in entries] == [1, 3, 2]


def test_zero_minute_days_are_skipped_and_not_counted():
    deadline = TODAY + timedelta(days=2)
    entries = Scheduler().generate(
        [task(1, deadline, remaining_work=120)],
        availability_for_dates({TODAY: 60, deadline: 60}),
        TODAY,
        set(),
    )

    assert entries == [
        ScheduleEntry(TODAY, 1, 60),
        ScheduleEntry(deadline, 1, 60),
    ]


def test_never_exceeds_capacity_or_deadline_and_leaves_excess_unscheduled():
    deadline = TODAY + timedelta(days=1)
    entries = Scheduler().generate(
        [task(1, deadline, remaining_work=200)],
        availability_for_dates({TODAY: 60, deadline: 60}),
        TODAY,
        set(),
    )

    assert sum(entry.minutes for entry in entries) == 120
    assert all(entry.date <= deadline for entry in entries)
    assert all(entry.minutes <= 60 for entry in entries)


@pytest.mark.parametrize(
    ("capacities", "work", "expected_total", "expected_remaining"),
    [
        (
            {TODAY: 120, TODAY + timedelta(days=1): 120},
            [(1, "high", 120), (2, "medium", 120)],
            240,
            {1: 0, 2: 0},
        ),
        (
            {TODAY: 100, TODAY + timedelta(days=1): 100},
            [(1, "high", 150), (2, "medium", 150)],
            200,
            {1: 0, 2: 100},
        ),
        (
            {TODAY: 100, TODAY + timedelta(days=1): 0, TODAY + timedelta(days=2): 100},
            [(1, "high", 80), (2, "low", 200)],
            200,
            {1: 0, 2: 80},
        ),
    ],
)
def test_capacity_and_priority_combinations(
    capacities, work, expected_total, expected_remaining
):
    deadline = TODAY + timedelta(days=3)
    tasks = [
        task(task_id, deadline, priority, remaining_work)
        for task_id, priority, remaining_work in work
    ]

    entries = Scheduler().generate(
        tasks,
        availability_for_dates(capacities),
        TODAY,
        set(),
    )
    scheduled = {
        task_id: sum(entry.minutes for entry in entries if entry.task_id == task_id)
        for task_id, _, _ in work
    }
    daily_totals = {
        day: sum(entry.minutes for entry in entries if entry.date == day)
        for day in {entry.date for entry in entries}
    }

    assert sum(entry.minutes for entry in entries) == expected_total
    assert scheduled == {
        task_id: original - expected_remaining[task_id]
        for task_id, _, original in work
    }
    assert all(entry.date <= deadline for entry in entries)
    assert all(total <= capacities.get(day, 0) for day, total in daily_totals.items())


def test_high_priority_tasks_are_completed_before_lower_priority_overflow():
    deadline = TODAY + timedelta(days=2)
    entries = Scheduler().generate(
        [
            task(1, deadline, "high", 100),
            task(2, deadline, "high", 100),
            task(3, deadline, "medium", 100),
            task(4, deadline, "low", 100),
        ],
        availability_for_dates({
            TODAY: 150,
            TODAY + timedelta(days=1): 150,
        }),
        TODAY,
        set(),
    )

    scheduled = {
        task_id: sum(entry.minutes for entry in entries if entry.task_id == task_id)
        for task_id in range(1, 5)
    }

    assert scheduled[1] == 100
    assert scheduled[2] == 100
    assert scheduled[3] + scheduled[4] == 100


def test_exact_fit_uses_all_capacity_without_overflow():
    deadline = TODAY + timedelta(days=2)
    entries = Scheduler().generate(
        [
            task(1, deadline, "high", 180),
            task(2, deadline, "medium", 120),
        ],
        availability_for_dates({
            TODAY: 150,
            TODAY + timedelta(days=1): 150,
        }),
        TODAY,
        set(),
    )

    assert sum(entry.minutes for entry in entries) == 300
    assert sum(entry.minutes for entry in entries if entry.task_id == 1) == 180
    assert sum(entry.minutes for entry in entries if entry.task_id == 2) == 120
    assert all(entry.date < deadline for entry in entries)


def test_skips_overdue_and_zero_work_tasks():
    entries = Scheduler().generate(
        [
            task(1, TODAY - timedelta(days=1)),
            task(2, TODAY, remaining_work=0),
        ],
        availability_for_dates({TODAY: 60}),
        TODAY,
        set(),
    )

    assert entries == []


def test_deterministic_without_mutating_inputs():
    tasks = [task(1, TODAY + timedelta(days=2), remaining_work=120)]
    before = tasks[0].remaining_work
    availability = every_day(60)

    first = Scheduler().generate(tasks, availability, TODAY, set())
    second = Scheduler().generate(tasks, availability, TODAY, set())

    assert first == second
    assert tasks[0].remaining_work == before


def test_empty_input_returns_empty_list():
    assert Scheduler().generate([], every_day(60), TODAY, set()) == []


def test_none_at_risk_ids_is_treated_as_empty():
    entries = Scheduler().generate(
        [task(1, TODAY, remaining_work=60)],
        availability_for_dates({TODAY: 60}),
        TODAY,
        None,
    )

    assert entries == [ScheduleEntry(TODAY, 1, 60)]


def test_unknown_priority_raises_value_error():
    with pytest.raises(ValueError, match="Unknown task priority"):
        Scheduler().generate(
            [task(1, TODAY, priority="urgent")],
            availability_for_dates({TODAY: 60}),
            TODAY,
            set(),
        )


def test_far_future_deadline_stops_after_work_is_placed():
    deadline = TODAY + timedelta(days=3650)
    entries = Scheduler().generate(
        [task(1, deadline, remaining_work=60)],
        every_day(60),
        TODAY,
        set(),
    )

    assert entries == [ScheduleEntry(TODAY, 1, 60)]


@pytest.mark.parametrize("minutes", [0, -1])
def test_schedule_entry_rejects_non_positive_minutes(minutes):
    with pytest.raises(ValueError):
        ScheduleEntry(TODAY, 1, minutes)
