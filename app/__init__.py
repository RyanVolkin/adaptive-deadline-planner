import os
from datetime import date, timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

from app.routes.auth import auth_bp
from app.routes.tasks import tasks_bp
from app.routes.availability import availability_bp
from app.db import close_db
from app.db import get_db
from app.domain.scheduling import Scheduler
from app.repositories import (
    AvailabilityRepository,
    ScheduleRepository,
    TaskRepository,
)
from app.services.availability_service import AvailabilityService
from app.services.schedule_service import ScheduleService


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SUPABASE_URL=os.environ.get("SUPABASE_URL"),
        SUPABASE_KEY=os.environ.get("SUPABASE_KEY"),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        APP_TIMEZONE=os.environ.get("APP_TIMEZONE", "America/New_York"),
    )
    if test_config:
        app.config.update(test_config)

    if "SUPABASE_CLIENT" not in app.config:
        if not app.config["SUPABASE_URL"] or not app.config["SUPABASE_KEY"]:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured")
        from supabase import create_client

        app.config["SUPABASE_CLIENT"] = create_client(
            app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"]
        )

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(availability_bp)
    app.teardown_appcontext(close_db)

    @app.route("/")
    def index():
        user_id = session.get("user_id")
        if not user_id:
            return render_template("index.html", user_id=None)

        connection = get_db()
        availability_service = AvailabilityService(
            AvailabilityRepository(connection), None, None
        )
        schedule_service = ScheduleService(
            TaskRepository(connection),
            availability_service,
            ScheduleRepository(connection),
            Scheduler(),
        )
        today = date.today()
        view = request.args.get("view", "daily")
        if view not in {"daily", "weekly"}:
            view = "daily"
        try:
            selected_date = date.fromisoformat(
                request.args.get("date", today.isoformat())
            )
        except ValueError:
            selected_date = today
        week_start = selected_date - timedelta(days=selected_date.weekday())
        navigation_step = timedelta(days=7 if view == "weekly" else 1)
        return render_template(
            "schedule.html",
            today=today,
            selected_date=selected_date,
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            previous_date=selected_date - navigation_step,
            next_date=selected_date + navigation_step,
            view=view,
            plan=schedule_service.get_daily_plan(user_id, selected_date),
            weekly_plan=schedule_service.get_weekly_plan(user_id, week_start),
            alerts=schedule_service.get_alerts(user_id, today),
            availability_needed=not availability_service.has_availability(user_id),
        )

    @app.route("/health")
    def health_check():
        return jsonify({"status": "healthy"}), 200
    return app
