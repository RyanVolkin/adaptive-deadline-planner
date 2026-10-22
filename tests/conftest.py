import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest


@pytest.fixture(scope="session")
def db_url():
    admin_url = os.environ.get("TEST_DATABASE_URL")
    if not admin_url:
        if os.environ.get("CI") == "true":
            pytest.fail("TEST_DATABASE_URL is required in CI.")
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL tests.")
    name = "adp_test_" + uuid4().hex
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = make_conninfo(admin_url, dbname=name)
        try:
            with psycopg.connect(url, autocommit=True) as connection:
                # Supabase supplies these roles and auth.users in production.
                for role in ("anon", "authenticated"):
                    if not connection.execute(
                        "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
                    ).fetchone():
                        connection.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
                connection.execute("CREATE SCHEMA auth")
                connection.execute("CREATE TABLE auth.users (id uuid PRIMARY KEY)")
                migration = Path(__file__).resolve().parents[1] / "sql/001_tasks.sql"
                connection.execute(migration.read_text())
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def user_id():
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def other_user_id():
    return "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def db_connection(db_url, user_id, other_user_id):
    with psycopg.connect(db_url, autocommit=True, row_factory=dict_row) as connection:
        connection.execute("TRUNCATE auth.users CASCADE")
        connection.execute("INSERT INTO auth.users (id) VALUES (%s), (%s)", (user_id, other_user_id))
        yield connection
