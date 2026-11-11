import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

from app.ai_client import FIELDS

from app import create_app
from app.ai_client import build_context


class AppTest(unittest.TestCase):
    def setUp(self):
        # Never read the developer's real .env while testing.
        self.dotenv = patch("app.load_dotenv").start()
        self.addCleanup(patch.stopall)
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "games.db"
        self.app = create_app(self.path)
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def test_loads_root_dotenv_without_overriding_environment(self):
        self.dotenv.assert_called_once_with(
            Path(__file__).resolve().parents[2] / ".env", override=False
        )

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

    def idea(self):
        return {field: f"Example {field}" for field in FIELDS}

    @patch("app.ai_client.generate_idea")
    def test_generation_revision_and_approval(self, generate):
        generate.return_value = self.idea()
        response = self.client.post("/api/ideas/draft", json={"prompt": "A space mystery", "genre": "Mystery"})
        self.assertEqual(response.status_code, 200)
        original = response.json["idea"]
        self.assertEqual(self.client.get("/api/ideas").json["ideas"], [])
        revised = {**original, "objective": "Cooperate to escape"}
        generate.return_value = revised
        response = self.client.post("/api/ideas/draft", json={"prompt": "Make it cooperative", "idea": original})
        self.assertEqual(response.json["idea"], revised)
        self.assertEqual(generate.call_args.args[0]["current_idea"], original)
        self.assertEqual(generate.call_args.args[0]["request"], "Make it cooperative")
        saved = self.client.post("/api/ideas", json={"idea": revised})
        self.assertEqual(saved.status_code, 201)
        restarted = create_app(self.path).test_client()
        self.assertEqual(restarted.get("/api/ideas").json["ideas"][0]["idea"], revised)

    def test_independent_instances_and_invalid_players(self):
        saved = self.client.post("/api/ideas", json={"idea": self.idea()}).json
        url = f"/api/ideas/{saved['id']}/instances"
        self.assertEqual(self.client.post(url, json={"players": ["Ada", "Ada"]}).status_code, 400)
        self.assertEqual(self.client.get("/api/games").json["games"], [])
        first = self.client.post(url, json={"players": ["Ada"]}).json
        second = self.client.post(url, json={"players": ["Lin"]}).json
        self.assertNotEqual(first["id"], second["id"])
        self.client.post(f"/api/games/{first['id']}/moves", json={"player": "Ada", "action": "Explore"})
        self.assertEqual(self.client.get(f"/api/games/{second['id']}").json["moves"], [])
        self.assertIn(self.idea()["setup"], first["rules"])
        self.assertEqual(self.client.post("/api/ideas/999/instances", json={"players": ["Ada"]}).status_code, 404)

    def test_idea_validation_and_missing_configuration(self):
        for payload in [{}, {"prompt": " "}, {"prompt": "x", "idea": []}]:
            self.assertEqual(self.client.post("/api/ideas/draft", json=payload).status_code, 400)
        self.assertEqual(self.client.post("/api/ideas", json={"idea": {}}).status_code, 400)
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            self.assertEqual(self.client.post("/api/ideas/draft", json={"prompt": "Adventure"}).status_code, 503)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("app.ai_client.urlopen")
    def test_ai_adapter_validates_provider_output(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(self.idea())}}]})
        urlopen.return_value.__enter__.return_value = response
        self.assertEqual(self.client.post("/api/ideas/draft", json={"prompt": "Adventure"}).status_code, 200)
        response.read.return_value = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]})
        self.assertEqual(self.client.post("/api/ideas/draft", json={"prompt": "Adventure"}).status_code, 502)
        urlopen.side_effect = TimeoutError()
        self.assertEqual(self.client.post("/api/ideas/draft", json={"prompt": "Adventure"}).status_code, 502)

    def test_frontend_and_health(self):
        for path in ["/", "/static/app.js", "/static/styles.css", "/api/health"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()


if __name__ == "__main__":
    unittest.main()
