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
        self.narrator = patch("app.ai_client.narrate_move", return_value="The door opens.").start()
        self.referee = patch("app.ai_client.referee_move", return_value={"accepted": True, "response": "The door opens.", "explanation": "Allowed", "state": "Play continues"}).start()

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
        self.assertEqual(valid.json["game"]["moves"][0]["turn_number"], 1)

    def test_referee_rejection_failure_and_persistence(self):
        game = self.create_game()
        url = f"/api/games/{game['id']}/moves"
        self.referee.return_value = {"accepted": False, "response": "Wait for your turn.", "explanation": "Not your turn", "state": "Unchanged"}
        response = self.client.post(url, json={"player": "Ada", "action": "Move"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["ruling"]["accepted"])
        self.assertEqual(response.json["game"]["moves"], [])
        self.referee.return_value = {"accepted": True, "response": "The door opens.", "explanation": "Allowed", "state": "Ada moved"}
        response = self.client.post(url, json={"player": "Ada", "action": "Move"})
        self.assertEqual(response.status_code, 201)
        saved = create_app(self.path).test_client().get(f"/api/games/{game['id']}").json
        self.assertEqual(saved["moves"][0]["referee_response"], "The door opens.")
        self.assertEqual(saved["moves"][0]["referee_state"], "Ada moved")
        self.assertEqual(saved["moves"][0]["referee_explanation"], "Allowed")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("app.ai_client.urlopen")
    def test_referee_response_validation(self, urlopen):
        self.referee.stop()
        self.narrator.stop()
        provider = MagicMock()
        urlopen.return_value.__enter__.return_value = provider
        ruling = {"accepted": True, "response": "A door opens.", "explanation": "Allowed", "state": "Door open"}
        def set_response(value):
            provider.read.return_value = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]})
        game = self.create_game()
        url = f"/api/games/{game['id']}/moves"
        provider.read.side_effect = [json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(ruling)}}]}),
                                     json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"response": "A door opens."})}}]})]
        result = self.client.post(url, json={"player": "Ada", "action": "Open door"})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json["game"]["moves"][0]["referee_response"], "A door opens.")
        provider.read.side_effect = [json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(ruling)}}]}),
                                     json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"response": ""})}}]})]
        self.assertEqual(self.client.post(url, json={"player": "Lin", "action": "Enter"}).status_code, 502)
        self.assertEqual(len(self.client.get(f"/api/games/{game['id']}").json["moves"]), 1)

    def test_stale_referee_result_is_not_saved(self):
        game = self.create_game()
        url = f"/api/games/{game['id']}"
        def edit_during_review(*args):
            other = self.app.test_client()
            other.put(url, json={"title": "Changed", "rules": "New rules", "players": ["Ada", "Lin"]})
            return {"accepted": True, "response": "The door opens.", "explanation": "Allowed", "state": "Moved"}
        self.referee.side_effect = edit_during_review
        response = self.client.post(url + "/moves", json={"player": "Ada", "action": "Move"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(url).json["moves"], [])

    @patch.dict("os.environ", {"FAL_KEY": "test-key"})
    @patch("app.scene_service.describe_scene")
    def test_scene_persists_and_reuses_unchanged_image(self, describe):
        import sys
        game = self.create_game()
        url = f"/api/games/{game['id']}/scene"
        fal = MagicMock()
        fal.subscribe.return_value = {"images": [{"url": "data:image/jpeg;base64,YWJj"}]}
        describe.return_value = {"changed": True, "description": "A detective in a hall"}
        with patch.dict(sys.modules, {"fal_client": fal}):
            first = self.client.post(url)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.json["scene"]["description"], "A detective in a hall")
            self.client.post(f"/api/games/{game['id']}/moves", json={"player": "Ada", "action": "Ask a question"})
            describe.return_value = {"changed": False, "description": "Same hall"}
            second = self.client.post(url)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json["scene"]["image_data"], first.json["scene"]["image_data"])
            self.assertEqual(second.json["scene"]["turn_number"], 1)
            self.assertEqual(fal.subscribe.call_count, 1)
            history = self.client.get(url + "s").json["scenes"]
            self.assertEqual([item["turn_number"] for item in history], [0, 1])
            self.assertEqual(history[0]["image_id"], history[1]["image_id"])
            image = self.client.get(f"/api/games/{game['id']}/scene-images/{history[1]['image_id']}")
            self.assertEqual(image.data, b"abc")
            restarted = create_app(self.path).test_client()
            self.assertEqual(restarted.get(url + "s").json["scenes"], history)
            self.assertEqual(self.client.delete(f"/api/games/{game['id']}").status_code, 200)

    @patch.dict("os.environ", {"FAL_KEY": "test-key"})
    @patch("app.scene_service.describe_scene")
    def test_history_generates_old_turns_without_future_moves(self, describe):
        import sys
        game = self.create_game()
        move_url = f"/api/games/{game['id']}/moves"
        self.client.post(move_url, json={"player": "Ada", "action": "Open door"})
        self.client.post(move_url, json={"player": "Lin", "action": "Enter"})
        describe.return_value = {"changed": True, "description": "A scene"}
        fal = MagicMock()
        fal.subscribe.return_value = {"images": [{"url": "data:image/jpeg;base64,YWJj"}]}
        with patch.dict(sys.modules, {"fal_client": fal}):
            for turn in range(3):
                self.assertEqual(self.client.post(f"/api/games/{game['id']}/scene").status_code, 200)
                self.assertEqual(len(describe.call_args.args[0]["moves"]), turn)
            history = self.client.get(f"/api/games/{game['id']}/scenes").json["scenes"]
            self.assertEqual([item["turn_number"] for item in history], [0, 1, 2])
            self.assertEqual(len({item["image_id"] for item in history}), 3)

    @patch.dict("os.environ", {"FAL_KEY": ""})
    def test_missing_image_key_does_not_prevent_moves(self):
        game = self.create_game()
        self.assertEqual(self.client.post(f"/api/games/{game['id']}/scene").status_code, 503)
        self.assertEqual(self.client.post(f"/api/games/{game['id']}/moves", json={"player": "Ada", "action": "Look around"}).status_code, 201)

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
        self.assertEqual(generate.call_args.args[0]["genre"], "Mystery")
        self.client.post("/api/ideas/draft", json={"prompt": "A game", "genre": "Strategy"})
        self.assertEqual(generate.call_args.args[0]["genre"], "Mystery")
        saved = self.client.post("/api/ideas", json={"idea": revised})
        self.assertEqual(saved.status_code, 201)
        restarted = create_app(self.path).test_client()
        self.assertEqual(restarted.get("/api/ideas").json["ideas"][0]["idea"], revised)

    @patch("app.ai_client.generate_idea")
    def test_mystery_setting_fields(self, generate):
        generate.return_value = self.idea()
        url = "/api/ideas/draft"
        response = self.client.post(url, json={"timeframe": " 1920s ", "location": " Chicago ",
                                               "details": " A winter storm ", "complexity": "Simple"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_args.args[0], {"genre": "Mystery", "timeframe": "1920s",
                         "location": "Chicago", "additional_details": "A winter storm", "complexity": "Simple"})
        response = self.client.post(url, json={"timeframe": "Present", "location": "London", "details": " "})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("additional_details", generate.call_args.args[0])
        for body in ({"timeframe": "", "location": "London"}, {"timeframe": "Present"},
                     {"timeframe": "Present", "location": "London", "details": []}):
            self.assertEqual(self.client.post(url, json=body).status_code, 400)

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

    def test_edit_idea_preserves_sessions_and_delete_keeps_them(self):
        saved = self.client.post("/api/ideas", json={"idea": self.idea()}).json
        url = f"/api/ideas/{saved['id']}"
        original = self.client.post(url + "/instances", json={"players": ["Ada"]}).json
        updated = {**self.idea(), "title": "Revised title", "rules": "New rules"}
        self.assertEqual(self.client.put(url, json={"idea": updated}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/games/{original['id']}").json["rules"], original["rules"])
        new = self.client.post(url + "/instances", json={"players": ["Lin"]}).json
        self.assertEqual(new["title"], "Revised title")
        self.assertIn("New rules", new["rules"])
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.get("/api/ideas").json["ideas"], [])
        self.assertEqual(self.client.get(f"/api/games/{original['id']}").status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_edit_and_delete_session_preserves_history_and_idea(self):
        saved = self.client.post("/api/ideas", json={"idea": self.idea()}).json
        game = self.client.post(f"/api/ideas/{saved['id']}/instances", json={"players": ["Ada", "Lin"]}).json
        url = f"/api/games/{game['id']}"
        self.client.post(url + "/moves", json={"player": "Ada", "action": "Explore"})
        changes = {"title": "Renamed session", "rules": "Updated rules", "players": ["Ada", "Sam"]}
        response = self.client.put(url, json=changes)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["title"], changes["title"])
        self.assertEqual(response.json["moves"][0]["action"], "Explore")
        for players in [["Sam"], ["Ada", "Ada"], []]:
            self.assertEqual(self.client.put(url, json={**changes, "players": players}).status_code, 400)
        self.assertEqual(self.client.get(url).json["players"], ["Ada", "Sam"])
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(len(self.client.get("/api/ideas").json["ideas"]), 1)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_management_validation_and_missing_records(self):
        self.assertEqual(self.client.put("/api/ideas/999", json={"idea": self.idea()}).status_code, 404)
        self.assertEqual(self.client.put("/api/ideas/999", json={"idea": {}}).status_code, 400)
        self.assertEqual(self.client.put("/api/games/999", json={"title": "X", "rules": "Y", "players": ["Ada"]}).status_code, 404)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "OPENAI_REASONING_EFFORT": "high"})
    @patch("app.ai_client.urlopen")
    def test_reasoning_effort_configuration(self, urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(self.idea())}}]})
        urlopen.return_value.__enter__.return_value = response
        for effort in ["high", ""]:
            with patch.dict("os.environ", {"OPENAI_REASONING_EFFORT": effort}):
                self.assertEqual(self.client.post("/api/ideas/draft", json={"prompt": "Adventure"}).status_code, 200)
                payload = json.loads(urlopen.call_args.args[0].data)
                if effort:
                    self.assertEqual(payload["reasoning_effort"], effort)
                else:
                    self.assertNotIn("reasoning_effort", payload)
        urlopen.reset_mock()
        with patch.dict("os.environ", {"OPENAI_REASONING_EFFORT": "invalid"}):
            self.assertEqual(self.client.post("/api/ideas/draft", json={"prompt": "Adventure"}).status_code, 503)
            urlopen.assert_not_called()

    def test_frontend_and_health(self):
        for path in ["/", "/static/app.js", "/static/styles.css", "/api/health"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()


if __name__ == "__main__":
    unittest.main()
