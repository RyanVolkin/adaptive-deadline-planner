from flask import Flask, render_template, jsonify


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health_check():
        return jsonify({"status": "healthy"}), 200
    return app