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


def create_game(data):
    title = require_text(data.get("title"), "Title", 120)
    rules = require_text(data.get("rules"), "Rules", 10000)
    players = data.get("players")
    if not isinstance(players, list) or not players:
        raise BadRequest("Provide at least one player in a players array.")
    players = [require_text(player, "Player name", 80) for player in players]
    if len(set(players)) != len(players):
        raise BadRequest("Player names must be unique.")
    connection = get_db()
    with connection:
        cursor = connection.execute(
            "INSERT INTO games (title, rules, players_json) VALUES (?, ?, ?)",
            (title, rules, json.dumps(players)),
        )
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
