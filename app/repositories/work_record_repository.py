class WorkRecordRepository:
    def __init__(self, connection):
        self.connection = connection

    def sum_minutes(self, user_id, task_id):
        row = self.connection.execute(
            """SELECT COALESCE(SUM(work_records.minutes), 0) AS minutes
               FROM public.work_records
               JOIN public.tasks ON tasks.id = work_records.task_id
               WHERE tasks.user_id = %s AND tasks.id = %s""",
            (user_id, task_id),
        ).fetchone()
        return row["minutes"]
