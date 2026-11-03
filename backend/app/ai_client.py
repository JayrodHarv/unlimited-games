"""Future AI integration boundary. No API requests are made by this starter.

Call build_context(get_game(id)) to obtain stored rules and complete history.
Keep API keys in backend environment variables, never in frontend JavaScript.
"""


def build_context(game):
    return {
        "title": game["title"],
        "rules": game["rules"],
        "players": game["players"],
        "moves": game["moves"],
    }
