from app.domain.work_record import WorkRecord


class WorkRecordRepository:
    def __init__(self, connection):
        self.connection = connection

    def insert(self, user_id, record):
        row = self.connection.execute(
            """INSERT INTO public.work_records (task_id, minutes, completion_pct, created_at)
               SELECT id, %s, %s, %s FROM public.tasks
               WHERE user_id = %s AND id = %s RETURNING id""",
            (record.minutes, record.completion_pct, record.created_at, user_id, record.task_id),
        ).fetchone()
        if row is None:
            raise ValueError({"task": "Task not found."})
        return row["id"]

    def list_for_task(self, user_id, task_id):
        rows = self.connection.execute(
            """SELECT w.id, w.task_id, w.minutes, w.completion_pct, w.created_at
               FROM public.work_records w JOIN public.tasks t ON t.id = w.task_id
               WHERE t.user_id = %s AND t.id = %s ORDER BY w.created_at, w.id""",
            (user_id, task_id),
        ).fetchall()
        return [WorkRecord(**row) for row in rows]

    def sum_minutes(self, user_id, task_id):
        row = self.connection.execute(
            """SELECT COALESCE(SUM(work_records.minutes), 0) AS minutes
               FROM public.work_records
               JOIN public.tasks ON tasks.id = work_records.task_id
               WHERE tasks.user_id = %s AND tasks.id = %s""",
            (user_id, task_id),
        ).fetchone()
        return row["minutes"]
