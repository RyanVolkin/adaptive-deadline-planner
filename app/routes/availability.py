import secrets
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from app.db import get_db, transaction
from app.domain.availability import WEEKDAYS
from app.domain.scheduling import Scheduler
from app.repositories import (
    AvailabilityRepository,
    ScheduleRepository,
    TaskRepository,
)
from app.services.availability_service import AvailabilityService
from app.services.schedule_service import ScheduleService


availability_bp = Blueprint("availability", __name__, url_prefix="/availability")

def _availability_service():
    connection = get_db()
    transaction_for_user = lambda: transaction(connection, session["user_id"])
    availability_service = AvailabilityService(
        AvailabilityRepository(connection),
        None,
        transaction_for_user,
    )
    availability_service.schedules = ScheduleService(
        TaskRepository(connection),
        availability_service,
        ScheduleRepository(connection),
        Scheduler(),
    )
    return availability_service
@availability_bp.before_request    
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

@availability_bp.route("", methods=["GET", "POST"])
def edit_availability():
    service = _availability_service()

    if request.method == "POST":
        try:
            service.save_week(session["user_id"], request.form)
        except ValueError as error:
            return render_template("availability.html", weekdays=WEEKDAYS, data=request.form, errors=error.args[0]), 400
        flash("Availability saved.")
        return redirect(url_for("availability.edit_availability"))
    
    week = service.get_week(session["user_id"])
    data = {}
    for weekday, minutes in enumerate(week):
        data[f"minutes_{weekday}"] = minutes
    return render_template("availability.html", weekdays=WEEKDAYS, data=data, errors={})
