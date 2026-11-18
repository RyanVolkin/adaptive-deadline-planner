from app.services.task_service import TaskNotFound
from app.domain.work_record import WorkRecord


class ProgressService:
    def __init__(self, tasks, work_records, estimation, schedules, transaction, clock):
        self.tasks = tasks
        self.work_records = work_records
        self.estimation = estimation
        self.schedules = schedules
        self.transaction = transaction
        self.clock = clock

    def validate(self, task, minutes, pct):
        errors = {}
        if task.is_complete():
            errors["task"] = "This task is already completed."
        if type(minutes) is not int or minutes < 0:
            errors["minutes"] = "Enter a whole number of minutes, zero or more."
        elif minutes > 2_147_483_647:
            errors["minutes"] = "Time worked is too large for one entry."
        if type(pct) is not int or not 0 <= pct <= 100:
            errors["completion_pct"] = "Enter a whole percentage between 0 and 100."
        elif pct < task.completion_pct:
            errors["completion_pct"] = "Completion cannot go backwards."
        elif minutes == 0 and pct == task.completion_pct:
            errors["minutes"] = "Add time or increase the completion percentage."
        return errors

    def record_work(self, user_id, task_id, minutes, pct):
        with self.transaction():
            task = self.tasks.get(user_id, task_id)
            if task is None:
                raise TaskNotFound({"task": "Task not found."})
            errors = self.validate(task, minutes, pct)
            if errors:
                raise ValueError(errors)

            now = self.clock()
            self.work_records.insert(user_id, WorkRecord(task_id, minutes, pct, now))
            actual = self.work_records.sum_minutes(user_id, task_id)
            task.completion_pct = pct
            task.updated_at = now
            if pct == 100:
                self.complete_task(task, actual, now)
                self.tasks.clear_scheduled_work(user_id, task_id, now.date())
            else:
                task.adjusted_estimate = self.estimation.adjusted_estimate(
                    task.starting_estimate, actual, pct
                )
                task.remaining_work = self.estimation.remaining_work(task.adjusted_estimate, pct)
            self.tasks.update(user_id, task)
            if self.schedules is not None:
                self.schedules.regenerate(user_id)
        return task

    def complete_task(self, task, actual, now):
        task.remaining_work = 0
        task.completed_at = now
        task.estimate_ratio = self.estimation.estimate_ratio(actual, task.original_estimate)
