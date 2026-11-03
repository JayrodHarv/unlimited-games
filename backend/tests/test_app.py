import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.ai_client import build_context


class AppTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "games.db"
        self.app = create_app(self.path)
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def create_game(self):
        response = self.client.post("/api/games", json={
            "title": "Test game", "rules": "Take turns.", "players": ["Ada", "Lin"],
        })
        self.assertEqual(response.status_code, 201)
        return response.json

    def test_persistent_rules_and_ordered_moves(self):
        game = self.create_game()
        for player, action in [("Ada", "Go north"), ("Lin", "Open door")]:
            response = self.client.post(f"/api/games/{game['id']}/moves", json={
                "player": player, "action": action,
            })
            self.assertEqual(response.status_code, 201)
        restarted = create_app(self.path).test_client()
        saved = restarted.get(f"/api/games/{game['id']}").json
        self.assertEqual(saved["rules"], "Take turns.")
        self.assertEqual([m["turn_number"] for m in saved["moves"]], [1, 2])
        self.assertEqual([m["action"] for m in saved["moves"]], ["Go north", "Open door"])
        self.assertEqual(len(build_context(saved)["moves"]), 2)
        self.assertEqual(len(restarted.get("/api/games").json["games"]), 1)

    def test_invalid_moves_do_not_change_history(self):
        game = self.create_game()
        url = f"/api/games/{game['id']}/moves"
        for payload in [{"player": "Unknown", "action": "Move"}, {"player": "Ada", "action": " "}]:
            self.assertEqual(self.client.post(url, json=payload).status_code, 400)
        self.assertEqual(self.client.get(f"/api/games/{game['id']}").json["moves"], [])
        valid = self.client.post(url, json={"player": "Ada", "action": "Move"})
        self.assertEqual(valid.json["moves"][0]["turn_number"], 1)

    def test_validation_and_missing_game(self):
        for payload in [[], {}, {"title": "X", "rules": "Y", "players": ["Ada", " Ada "]}]:
            self.assertEqual(self.client.post("/api/games", json=payload).status_code, 400)
        self.assertEqual(self.client.get("/api/games/999").status_code, 404)
        self.assertEqual(self.client.post("/api/games/999/moves", json={"player": "Ada", "action": "Move"}).status_code, 404)

    def test_frontend_and_health(self):
        for path in ["/", "/static/app.js", "/static/styles.css", "/api/health"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()


if __name__ == "__main__":
    unittest.main()
