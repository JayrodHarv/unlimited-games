from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest

from . import game_service
from .db import get_db

api = Blueprint("api", __name__)


def body():
    data = request.get_json()
    if not isinstance(data, dict):
        raise BadRequest("JSON body must be an object.")
    return data


@api.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return jsonify(status="ok")


@api.get("/games")
def games():
    return jsonify(games=game_service.list_games())


@api.post("/games")
def create_game():
    return jsonify(game_service.create_game(body())), 201


@api.get("/games/<int:game_id>")
def get_game(game_id):
    return jsonify(game_service.get_game(game_id))


@api.post("/games/<int:game_id>/moves")
def move(game_id):
    return jsonify(game_service.record_move(game_id, body())), 201


@api.post("/ideas/draft")
def draft_idea():
    return jsonify(idea=game_service.draft_idea(body()))


@api.get("/ideas")
def ideas():
    return jsonify(ideas=game_service.list_ideas())


@api.post("/ideas")
def save_idea():
    return jsonify(game_service.save_idea(body())), 201


@api.post("/ideas/<int:idea_id>/instances")
def start_instance(idea_id):
    return jsonify(game_service.start_instance(idea_id, body())), 201
