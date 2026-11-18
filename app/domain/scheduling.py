from dataclasses import dataclass
from datetime import date, timedelta
from bisect import bisect_left


@dataclass(frozen=True)
class ScheduleEntry:
    date: date
    task_id: int
    minutes: int

    def __post_init__(self):
        if self.minutes <= 0:
            raise ValueError("ScheduleEntry minutes must be greater than zero.")


class Scheduler:
    _PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    def generate(self, tasks, availability, today, at_risk_ids):
        schedulable = [
            task for task in tasks
            if task.remaining_work > 0 and task.deadline >= today
        ]
        if not schedulable:
            return []

        task_order = sorted(schedulable, key=self._sort_key(at_risk_ids or set()))
        remaining = {task.id: task.remaining_work for task in task_order}
        latest_deadline = max(task.deadline for task in task_order)
        capacities = {}
        current_day = today
        while current_day <= latest_deadline:
            capacities[current_day] = availability[current_day.weekday()]
            current_day += timedelta(days=1)

        capacity_days = sorted(
            day for day, capacity in capacities.items() if capacity > 0
        )
        windows = {
            task.id: [
                day for day in capacity_days
                if day < task.deadline
            ]
            for task in task_order
        }
        entries = {}

        for current_day, daily_capacity in capacities.items():
            if not any(remaining.values()):
                break
            if daily_capacity <= 0:
                continue
            capacity_left = daily_capacity

            for task in task_order:
                if capacity_left == 0:
                    break
                if remaining[task.id] == 0:
                    continue
                window = windows[task.id]
                window_index = bisect_left(window, current_day)
                if window_index == len(window) or window[window_index] != current_day:
                    continue
                days_left = len(window) - window_index
                target = (remaining[task.id] + days_left - 1) // days_left
                assigned = min(target, remaining[task.id], capacity_left)
                self._assign(
                    entries, current_day, task.id,
                    assigned,
                )
                remaining[task.id] -= assigned
                capacity_left -= assigned

            for task in task_order:
                if capacity_left == 0:
                    break
                if remaining[task.id] == 0:
                    continue
                window = windows[task.id]
                window_index = bisect_left(window, current_day)
                if window_index == len(window) or window[window_index] != current_day:
                    continue
                assigned = min(remaining[task.id], capacity_left)
                self._assign(
                    entries, current_day, task.id,
                    assigned,
                )
                remaining[task.id] -= assigned
                capacity_left -= assigned

            for task in task_order:
                if capacity_left == 0:
                    break
                if task.deadline != current_day or remaining[task.id] == 0:
                    continue
                assigned = min(remaining[task.id], capacity_left)
                self._assign(
                    entries, current_day, task.id,
                    assigned,
                )
                remaining[task.id] -= assigned
                capacity_left -= assigned

        order = {task.id: index for index, task in enumerate(task_order)}
        return [
            ScheduleEntry(day, task_id, minutes)
            for (day, task_id), minutes in sorted(
                entries.items(), key=lambda item: (item[0][0], order[item[0][1]])
            )
        ]

    @staticmethod
    def _assign(entries, day, task_id, minutes):
        if minutes <= 0:
            return
        key = (day, task_id)
        entries[key] = entries.get(key, 0) + minutes

    def _sort_key(self, at_risk_ids):
        return lambda task: (
            task.id not in at_risk_ids,
            task.deadline,
            self._priority_order(task.priority),
            task.id,
        )

    @staticmethod
    def _priority_order(priority):
        try:
            return Scheduler._PRIORITY_ORDER[priority]
        except KeyError as error:
            raise ValueError(f"Unknown task priority: {priority!r}") from error
