from datetime import datetime
import secrets
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from app.db import get_db, transaction
from app.estimation import EstimationEngine
from app.repositories import TaskRepository, WorkRecordRepository
from app.task import PRIORITIES, TASK_TYPES
from app.task_service import TaskNotFound, TaskService


tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")


@tasks_bp.app_template_filter("hours_minutes")
def hours_minutes(total):
    hours, minutes = divmod(total, 60)
    return f"{hours}h {minutes:02d}m"


def _now():
    return datetime.now(ZoneInfo(current_app.config["APP_TIMEZONE"]))


def _task_service():
    connection = get_db()
    return TaskService(
        TaskRepository(connection), WorkRecordRepository(connection),
        EstimationEngine(), None,  # ScheduleService will be connected in #6.
        lambda: transaction(connection, session["user_id"]), clock=_now,
    )


@tasks_bp.before_request
def require_login_and_check_form():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        provided = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode(), provided.encode()):
            abort(400)
    elif "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)


def _form(data, errors=None, task_id=None):
    return render_template(
        "task_form.html", data=data, errors=errors or {}, task_id=task_id,
        task_types=TASK_TYPES, priorities=PRIORITIES, today=_now().date(),
    )


@tasks_bp.get("")
def list_tasks():
    return render_template(
        "tasks.html", tasks=_task_service().list_tasks(session["user_id"]),
        today=_now().date(),
    )


@tasks_bp.route("/new", methods=["GET", "POST"])
def create_task():
    if request.method == "POST":
        try:
            _task_service().create_task(session["user_id"], request.form)
        except ValueError as error:
            return _form(request.form, error.args[0]), 400
        flash("Task added.")
        return redirect(url_for("tasks.list_tasks"))
    return _form({"type": "homework", "priority": "medium"})


@tasks_bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):
    service = _task_service()
    if request.method == "POST":
        try:
            service.update_task(session["user_id"], task_id, request.form)
        except TaskNotFound:
            abort(404)
        except ValueError as error:
            return _form(request.form, error.args[0], task_id), 400
        flash("Task updated.")
        return redirect(url_for("tasks.list_tasks"))
    task = service.get_task(session["user_id"], task_id)
    if task is None:
        abort(404)
    if task.is_complete():
        abort(400, description="Completed tasks cannot be edited.")
    return _form(vars(task), task_id=task_id)


@tasks_bp.route("/<int:task_id>/delete", methods=["GET", "POST"])
def delete_task(task_id):
    service = _task_service()
    task = service.get_task(session["user_id"], task_id)
    if task is None:
        abort(404)
    if request.method == "GET":
        return render_template("task_delete.html", task=task)
    try:
        service.delete_task(
            session["user_id"], task_id,
            confirmed=request.form.get("confirmed") == "yes",
        )
    except TaskNotFound:
        abort(404)
    except ValueError as error:
        return render_template(
            "task_error.html", errors=error.args[0],
        ), 400
    flash("Task deleted.")
    return redirect(url_for("tasks.list_tasks"))
