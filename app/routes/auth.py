from functools import wraps

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from app.services.auth_service import AuthService


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _auth_service():
    return AuthService(current_app.config["SUPABASE_CLIENT"])

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = _auth_service().authenticate(request.form.get("email"), request.form.get("password"))
        if user is None:
            error = "Invalid email or password."
        else:
            return redirect(url_for("index"))
    return render_template("auth.html", mode="login", error=error)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        user, error = _auth_service().register(
            request.form.get("email"), request.form.get("password")
        )
        if user:
            return redirect(url_for("index"))
    return render_template("auth.html", mode="register", error=error)


@auth_bp.post("/logout")
def logout():
    _auth_service().logout()
    return redirect(url_for("auth.login"))