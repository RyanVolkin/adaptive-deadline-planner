from datetime import date, timedelta


class ScheduleService:
    def __init__(
        self,
        task_repo,
        availability_service,
        schedule_repo,
        scheduler,
        risk_detector=None,
        clock=date.today,
    ):
        self.task_repo = task_repo
        self.availability_service = availability_service
        self.schedule_repo = schedule_repo
        self.scheduler = scheduler
        self.risk_detector = risk_detector
        self.clock = clock

    def regenerate(self, user_id, today=None):
        if not self.availability_service.has_availability(user_id):
            print("[schedule] skipped: weekly availability is not saved", flush=True)
            return "AVAILABILITY_NEEDED"

        today = self.clock() if today is None else today
        tasks = self.task_repo.list_incomplete(user_id)
        availability = self.availability_service.get_week(user_id)
        print(
            f"[schedule] generating: tasks={len(tasks)}, today={today}, "
            f"availability={availability}",
            flush=True,
        )
        if self.risk_detector is None:
            at_risk_ids = set()
        else:
            at_risk_ids = {
                alert.task.id
                for alert in self.risk_detector.at_risk_tasks(
                    tasks, availability, today
                )
            }
        entries = self.scheduler.generate(
            tasks, availability, today, at_risk_ids
        )
        self.schedule_repo.replace_for_user(user_id, entries)
        print(
            f"[schedule] saved: entries={len(entries)}, user={user_id}",
            flush=True,
        )
        return "PLAN_UPDATED"

    def get_daily_plan(self, user_id, date):
        return self._map_entries(
            user_id, self.schedule_repo.get_for_date(user_id, date)
        )

    def get_weekly_plan(self, user_id, week_start):
        week_end = week_start + timedelta(days=6)
        entries = self.schedule_repo.get_for_week(user_id, week_start, week_end)
        tasks = {
            task.id: task
            for task in self.task_repo.list_incomplete(user_id)
        }
        by_date = {}
        for entry in entries:
            if entry.task_id in tasks:
                by_date.setdefault(entry.date, []).append(
                    (tasks[entry.task_id], entry.minutes)
                )
        return [
            (day, by_date.get(day, []))
            for day in (week_start + timedelta(days=offset) for offset in range(7))
        ]

    def _map_entries(self, user_id, entries):
        if not entries:
            return []
        tasks = {
            task.id: task
            for task in self.task_repo.list_incomplete(user_id)
        }
        return [
            (tasks[entry.task_id], entry.minutes)
            for entry in entries
            if entry.task_id in tasks
        ]

    def get_alerts(self, user_id, today=None):
        if self.risk_detector is None:
            return []

        today = self.clock() if today is None else today
        tasks = self.task_repo.list_incomplete(user_id)
        missed = self.risk_detector.missed_deadlines(tasks, today)
        if not self.availability_service.has_availability(user_id):
            return missed

        availability = self.availability_service.get_week(user_id)
        return missed + self.risk_detector.at_risk_tasks(
            tasks, availability, today
        )
