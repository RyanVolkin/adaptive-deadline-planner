from datetime import date, datetime

from app.estimation import HISTORY_LIMIT
from app.task import MAX_ORIGINAL_ESTIMATE, PRIORITIES, TASK_TYPES, Task


class TaskNotFound(ValueError):
    pass


class TaskService:
    """Task operations using repositories and a shared transaction."""

    def __init__(self, tasks, work_records, estimation, schedules,
                 transaction, clock=datetime.now):
        self.tasks = tasks
        self.work_records = work_records
        self.estimation = estimation
        self.schedules = schedules
        # Repositories and scheduling must share this transaction's connection.
        self.transaction = transaction
        self.clock = clock

    def validate(self, data, today):
        errors = {}
        name = data.get("name", "").strip()
        if not name or len(name) > 100:
            errors["name"] = "Enter a task name from 1 to 100 characters."

        estimate = str(data.get("original_estimate", "")).strip()
        if (not estimate.isdecimal() or len(estimate) > len(str(MAX_ORIGINAL_ESTIMATE))
                or not 1 <= int(estimate) <= MAX_ORIGINAL_ESTIMATE):
            errors["original_estimate"] = "Enter a positive whole number of minutes within the supported range."

        try:
            deadline = date.fromisoformat(data.get("deadline", ""))
        except ValueError:
            errors["deadline"] = "Enter a valid deadline date."
        else:
            if deadline < today:
                errors["deadline"] = "The deadline cannot be before today."

        if data.get("type") not in TASK_TYPES:
            errors["type"] = "Choose a task type."
        if data.get("priority") not in PRIORITIES:
            errors["priority"] = "Choose a priority."
        return errors

    def create_task(self, user_id, data):
        now = self.clock()
        errors = self.validate(data, now.date())
        if errors:
            raise ValueError(errors)

        with self.transaction():
            original = int(data["original_estimate"])
            starting = self._starting_estimate(user_id, data["type"], original)
            task = Task(
                user_id=user_id,
                name=data["name"].strip(),
                type=data["type"],
                priority=data["priority"],
                deadline=date.fromisoformat(data["deadline"]),
                original_estimate=original,
                starting_estimate=starting,
                adjusted_estimate=starting,
                remaining_work=starting,
                created_at=now,
                updated_at=now,
            )
            task.id = self.tasks.insert(user_id, task)
            if self.schedules is not None:
                self.schedules.regenerate(user_id)
        return task

    def update_task(self, user_id, task_id, data):
        now = self.clock()
        with self.transaction():
            task = self._get_task(user_id, task_id)
            if task.is_complete():
                raise ValueError({"task": "Completed tasks cannot be edited."})
            errors = self.validate(data, now.date())
            if errors:
                raise ValueError(errors)

            original = int(data["original_estimate"])
            if task.type != data["type"] or task.original_estimate != original:
                task.starting_estimate = self._starting_estimate(
                    user_id, data["type"], original
                )
                actual = self.work_records.sum_minutes(user_id, task_id)
                task.adjusted_estimate = self.estimation.adjusted_estimate(
                    task.starting_estimate, actual, task.completion_pct
                )
                task.remaining_work = self.estimation.remaining_work(
                    task.adjusted_estimate, task.completion_pct
                )

            task.name = data["name"].strip()
            task.type = data["type"]
            task.priority = data["priority"]
            task.deadline = date.fromisoformat(data["deadline"])
            task.original_estimate = original
            task.updated_at = now
            self.tasks.update(user_id, task)
            if self.schedules is not None:
                self.schedules.regenerate(user_id)
        return task

    def delete_task(self, user_id, task_id, confirmed=False):
        if confirmed is not True:
            raise ValueError({"task": "Confirm task deletion first."})
        with self.transaction():
            self._get_task(user_id, task_id)
            self.tasks.delete(user_id, task_id)
            if self.schedules is not None:
                self.schedules.regenerate(user_id)

    def list_tasks(self, user_id):
        return self.tasks.list_by_user(user_id)

    def get_task(self, user_id, task_id):
        return self.tasks.get(user_id, task_id)

    def _get_task(self, user_id, task_id):
        task = self.tasks.get(user_id, task_id)
        if task is None or task.user_id != user_id:
            raise TaskNotFound({"task": "Task not found."})
        return task

    def _starting_estimate(self, user_id, task_type, original):
        ratios = self.tasks.recent_ratios(user_id, task_type, HISTORY_LIMIT)
        factor = self.estimation.history_factor(ratios)
        return self.estimation.starting_estimate(original, factor)
