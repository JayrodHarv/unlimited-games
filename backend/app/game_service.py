"""Database operations. Game-specific rule enforcement can be added here."""
import json

from werkzeug.exceptions import BadRequest, NotFound

from .db import get_db


def require_text(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise BadRequest(f"{name} must be nonempty text, at most {limit} characters.")
    return value.strip()


def game_dict(row):
    game = dict(row)
    game["players"] = json.loads(game.pop("players_json"))
    return game


def list_games():
    return [game_dict(row) for row in get_db().execute("SELECT * FROM games ORDER BY id DESC")]


def get_game(game_id):
    row = get_db().execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if row is None:
        raise NotFound("Game not found.")
    game = game_dict(row)
    game["moves"] = [dict(move) for move in get_db().execute(
        "SELECT * FROM moves WHERE game_id = ? ORDER BY turn_number", (game_id,)
    )]
    return game


def validate_players(players):
    if not isinstance(players, list) or not players:
        raise BadRequest("Provide at least one player in a players array.")
    players = [require_text(player, "Player name", 80) for player in players]
    if len(set(players)) != len(players):
        raise BadRequest("Player names must be unique.")
    return players


def create_game(data, commit=True):
    title = require_text(data.get("title"), "Title", 120)
    rules = require_text(data.get("rules"), "Rules", 10000)
    players = validate_players(data.get("players"))
    connection = get_db()
    cursor = connection.execute(
        "INSERT INTO games (title, rules, players_json) VALUES (?, ?, ?)",
        (title, rules, json.dumps(players)),
    )
    if commit:
        connection.commit()
    return get_game(cursor.lastrowid)


def record_move(game_id, data):
    player = require_text(data.get("player"), "Player", 80)
    action = require_text(data.get("action"), "Action", 5000)
    connection = get_db()
    # Lock before assigning a turn number, so simultaneous submissions cannot
    # receive the same number. AI calls should happen outside this transaction.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        game = get_game(game_id)
        if player not in game["players"]:
            raise BadRequest("Player must belong to this game.")
        turn = len(game["moves"]) + 1
        connection.execute(
            "INSERT INTO moves (game_id, turn_number, player, action) VALUES (?, ?, ?, ?)",
            (game_id, turn, player, action),
        )
    return get_game(game_id)


def validate_idea(data):
    from .ai_client import FIELDS
    if not isinstance(data, dict):
        raise BadRequest("Provide a structured game idea.")
    return {field: require_text(data.get(field), field.capitalize(),
                               120 if field == "title" else 1200) for field in FIELDS}


def draft_idea(data):
    from .ai_client import generate_idea
    prompt = require_text(data.get("prompt"), "Game idea or revision", 5000)
    context = {"request": prompt}
    if data.get("idea") is not None:
        context["current_idea"] = validate_idea(data["idea"])
    for field in ("genre", "complexity"):
        value = data.get(field)
        if value:
            context[field] = require_text(value, field, 80)
    return generate_idea(context)


def list_ideas():
    return [dict(id=row["id"], idea=json.loads(row["definition_json"]))
            for row in get_db().execute("SELECT * FROM ideas ORDER BY id DESC")]


def save_idea(data):
    idea = validate_idea(data.get("idea"))
    connection = get_db()
    with connection:
        cursor = connection.execute("INSERT INTO ideas (definition_json) VALUES (?)", (json.dumps(idea),))
    return {"id": cursor.lastrowid, "idea": idea}


def start_instance(idea_id, data):
    connection = get_db()
    row = connection.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    if row is None:
        raise NotFound("Saved idea not found.")
    idea = json.loads(row["definition_json"])
    rules = "\n\n".join(f"{field.capitalize()}\n{value}" for field, value in idea.items() if field != "title")
    # Both the new session and its source link commit together.
    with connection:
        game = create_game({"title": idea["title"], "rules": rules, "players": data.get("players")}, commit=False)
        connection.execute("INSERT INTO idea_instances (game_id, idea_id) VALUES (?, ?)", (game["id"], idea_id))
    return game


def update_idea(idea_id, data):
    idea = validate_idea(data.get("idea"))
    connection = get_db()
    with connection:
        cursor = connection.execute("UPDATE ideas SET definition_json = ? WHERE id = ?", (json.dumps(idea), idea_id))
        if cursor.rowcount == 0:
            raise NotFound("Saved idea not found.")
    return {"id": idea_id, "idea": idea}


def delete_idea(idea_id):
    connection = get_db()
    with connection:
        connection.execute("DELETE FROM idea_instances WHERE idea_id = ?", (idea_id,))
        cursor = connection.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        if cursor.rowcount == 0:
            raise NotFound("Saved idea not found.")


def update_game(game_id, data):
    title = require_text(data.get("title"), "Title", 120)
    rules = require_text(data.get("rules"), "Rules", 10000)
    players = validate_players(data.get("players"))
    connection = get_db()
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        game = get_game(game_id)
        if any(move["player"] not in players for move in game["moves"]):
            raise BadRequest("Keep players who have recorded moves so history remains consistent.")
        connection.execute("UPDATE games SET title = ?, rules = ?, players_json = ? WHERE id = ?",
                           (title, rules, json.dumps(players), game_id))
    return get_game(game_id)


def delete_game(game_id):
    connection = get_db()
    with connection:
        get_game(game_id)
        connection.execute("DELETE FROM moves WHERE game_id = ?", (game_id,))
        connection.execute("DELETE FROM idea_instances WHERE game_id = ?", (game_id,))
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
