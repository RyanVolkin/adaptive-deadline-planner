from app.domain.scheduling import ScheduleEntry


class ScheduleRepository:
    def __init__(self, connection):
        self.connection = connection

    def list_by_user(self, user_id):
        rows = self.connection.execute(
            """SELECT date, task_id, minutes
               FROM public.schedule_entries
               WHERE user_id = %s
               ORDER BY date, task_id""",
            (user_id,),
        ).fetchall()
        return [
            ScheduleEntry(
                date=row["date"],
                task_id=row["task_id"],
                minutes=row["minutes"],
            )
            for row in rows
        ]

    def get_for_date(self, user_id, date):
        rows = self.connection.execute(
            """SELECT date, task_id, minutes
               FROM public.schedule_entries
               WHERE user_id = %s AND date = %s
               ORDER BY task_id""",
            (user_id, date),
        ).fetchall()
        return [
            ScheduleEntry(
                date=row["date"],
                task_id=row["task_id"],
                minutes=row["minutes"],
            )
            for row in rows
        ]

    def get_for_week(self, user_id, start_date, end_date):
        rows = self.connection.execute(
            """SELECT date, task_id, minutes
               FROM public.schedule_entries
               WHERE user_id = %s AND date BETWEEN %s AND %s
               ORDER BY date, task_id""",
            (user_id, start_date, end_date),
        ).fetchall()
        return [
            ScheduleEntry(
                date=row["date"],
                task_id=row["task_id"],
                minutes=row["minutes"],
            )
            for row in rows
        ]

    def replace_for_user(self, user_id, entries):
        self.connection.execute(
            "DELETE FROM public.schedule_entries WHERE user_id = %s",
            (user_id,),
        )
        for entry in entries:
            self.connection.execute(
                """INSERT INTO public.schedule_entries
                   (task_id, user_id, date, minutes)
                   VALUES (%s, %s, %s, %s)""",
                (entry.task_id, user_id, entry.date, entry.minutes),
            )
