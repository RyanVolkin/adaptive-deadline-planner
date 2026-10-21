from contextlib import contextmanager

import psycopg
from flask import current_app, g
from psycopg.rows import dict_row


def get_db():
    if "db" not in g:
        url = current_app.config.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL must be configured")
        g.db = psycopg.connect(url, autocommit=True, row_factory=dict_row)
    return g.db


def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@contextmanager
def transaction(connection, user_id):
    with connection.transaction():
        # Keep changes to one user's tasks and schedule from overlapping.
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (str(user_id),),
        )
        yield
