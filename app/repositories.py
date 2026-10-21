from dataclasses import asdict

from app.estimation import HISTORY_LIMIT
from app.task import Task


TASK_COLUMNS = """id, user_id, name, type, priority, deadline,
                  original_estimate, starting_estimate, adjusted_estimate,
                  remaining_work, completion_pct, estimate_ratio,
                  completed_at, created_at, updated_at"""


def _to_task(row):
    if row is None:
        return None
    row["user_id"] = str(row["user_id"])
    return Task(**row)


class TaskRepository:
    def __init__(self, connection):
        self.connection = connection

    def get(self, user_id, task_id):
        row = self.connection.execute(
            f"SELECT {TASK_COLUMNS} FROM public.tasks WHERE user_id = %s AND id = %s",
            (user_id, task_id),
        ).fetchone()
        return _to_task(row)

    def list_by_user(self, user_id):
        rows = self.connection.execute(
            f"SELECT {TASK_COLUMNS} FROM public.tasks WHERE user_id = %s ORDER BY deadline, id",
            (user_id,),
        ).fetchall()
        return [_to_task(row) for row in rows]

    def recent_ratios(self, user_id, task_type, limit=HISTORY_LIMIT):
        rows = self.connection.execute(
            """SELECT estimate_ratio FROM public.tasks
               WHERE user_id = %s AND type = %s
                 AND completion_pct = 100 AND estimate_ratio IS NOT NULL
               ORDER BY completed_at DESC NULLS LAST, id DESC
               LIMIT %s""",
            (user_id, task_type, min(limit, HISTORY_LIMIT)),
        ).fetchall()
        return [row["estimate_ratio"] for row in rows]

    def insert(self, user_id, task):
        values = asdict(task)
        values["user_id"] = user_id
        row = self.connection.execute(
            """INSERT INTO public.tasks (
                   user_id, name, type, priority, deadline, original_estimate,
                   starting_estimate, adjusted_estimate, remaining_work,
                   completion_pct, estimate_ratio, completed_at, created_at, updated_at
               ) VALUES (
                   %(user_id)s, %(name)s, %(type)s, %(priority)s, %(deadline)s,
                   %(original_estimate)s, %(starting_estimate)s, %(adjusted_estimate)s,
                   %(remaining_work)s, %(completion_pct)s, %(estimate_ratio)s,
                   %(completed_at)s, %(created_at)s, %(updated_at)s
               ) RETURNING id""",
            values,
        ).fetchone()
        return row["id"]

    def update(self, user_id, task):
        values = asdict(task)
        values["user_id"] = user_id
        self.connection.execute(
            """UPDATE public.tasks SET
                   name = %(name)s, type = %(type)s, priority = %(priority)s,
                   deadline = %(deadline)s, original_estimate = %(original_estimate)s,
                   starting_estimate = %(starting_estimate)s,
                   adjusted_estimate = %(adjusted_estimate)s,
                   remaining_work = %(remaining_work)s, completion_pct = %(completion_pct)s,
                   estimate_ratio = %(estimate_ratio)s, completed_at = %(completed_at)s,
                   updated_at = %(updated_at)s
               WHERE user_id = %(user_id)s AND id = %(id)s""",
            values,
        )

    def delete(self, user_id, task_id):
        self.connection.execute(
            "DELETE FROM public.tasks WHERE user_id = %s AND id = %s",
            (user_id, task_id),
        )


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
