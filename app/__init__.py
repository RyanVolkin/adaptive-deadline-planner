import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, session

from app.routes.auth import auth_bp


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SUPABASE_URL=os.environ.get("SUPABASE_URL"),
        SUPABASE_KEY=os.environ.get("SUPABASE_KEY"),
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

    @app.route("/")
    def index():
        return render_template("index.html", user_id=session.get("user_id"))

    @app.route("/health")
    def health_check():
        return jsonify({"status": "healthy"}), 200
    return app