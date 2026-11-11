"""Server-side AI adapter. Credentials never leave the backend."""
import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

from werkzeug.exceptions import BadGateway, ServiceUnavailable

FIELDS = ("title", "premise", "objective", "setup", "turns", "rules", "ending")


def generate_idea(context):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ServiceUnavailable("AI generation needs OPENAI_API_KEY configured on the server.")
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "Design a complete playable text-based, turn-based game. Return only a JSON object "
                f"with these string fields: {', '.join(FIELDS)}. Title at most 120 characters; "
                "each other field at most 1200 characters. Include concrete starting resources, "
                "legal actions, resolution mechanics, turn order and win/loss conditions. "
                "Players resolve moves manually. Do not require an AI referee. "
                "When revising, preserve the existing design except where requested."
            )},
            {"role": "user", "content": json.dumps(context)},
        ],
    }
    effort = os.environ.get("OPENAI_REASONING_EFFORT", "").strip()
    if effort:
        if effort not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ServiceUnavailable("OPENAI_REASONING_EFFORT must be none, minimal, low, medium, high, xhigh, or max.")
        payload["reasoning_effort"] = effort
    request = Request("https://api.openai.com/v1/chat/completions",
                      data=json.dumps(payload).encode(), headers={
                          "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
        choice = result["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete generation")
        idea = json.loads(choice["message"]["content"])
        if not isinstance(idea, dict) or any(
            not isinstance(idea.get(field), str) or not idea[field].strip()
            or len(idea[field]) > (120 if field == "title" else 1200)
            for field in FIELDS
        ):
            raise ValueError("Invalid game definition")
        return {field: idea[field].strip() for field in FIELDS}
    except (URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        raise BadGateway("AI could not produce a complete game idea. Please try again.") from None


def build_context(game):
    return {key: game[key] for key in ("title", "rules", "players", "moves")}
