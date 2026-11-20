import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app):
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        connection = get_db()
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(Path(__file__).with_name("schema.sql").read_text())
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(moves)")}
        for name in ("referee_explanation", "referee_state", "referee_response"):
            if name not in columns:
                connection.execute(f"ALTER TABLE moves ADD COLUMN {name} TEXT")
        # Preserve the latest scene created by earlier versions, once per session.
        connection.execute("INSERT INTO scene_images (game_id, description, image_data) "
                           "SELECT s.game_id, s.description, s.image_data FROM scenes s "
                           "WHERE s.turn_number >= 0 AND NOT EXISTS "
                           "(SELECT 1 FROM scene_turns t WHERE t.game_id = s.game_id AND t.turn_number = s.turn_number)")
        connection.execute("INSERT OR IGNORE INTO scene_turns (game_id, turn_number, image_id) "
                           "SELECT s.game_id, s.turn_number, (SELECT MAX(i.id) FROM scene_images i WHERE i.game_id = s.game_id) "
                           "FROM scenes s WHERE s.turn_number >= 0")
        connection.commit()
