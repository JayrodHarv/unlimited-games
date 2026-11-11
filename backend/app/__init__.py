import os
from pathlib import Path

from flask import Flask, jsonify, request
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException

from . import db
from .routes import api


def create_app(database_path=None):
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)
    frontend = root / "frontend"
    app = Flask(__name__, static_folder=str(frontend), static_url_path="/static")
    app.config.update(
        DATABASE=str(database_path or os.environ.get("DATABASE_PATH", root / "data" / "games.db")),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    db.init_app(app)
    app.register_blueprint(api, url_prefix="/api")

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.errorhandler(HTTPException)
    def http_error(error):
        if not request.path.startswith("/api/"):
            return error
        return jsonify(error=error.description), error.code

    return app
