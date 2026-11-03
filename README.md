# Unlimited Games — starter

A small Python + plain HTML/CSS/JavaScript project. Flask serves both the frontend
and JSON API from one process. Python's built-in `sqlite3` stores games, rules,
players, and the complete ordered move history. Docker runs Gunicorn and keeps
the SQLite database in a persistent volume. No Node build step or separate
database container is needed.

This is infrastructure for the AI game project: it records manual moves, but
does not generate games, judge moves, enforce turn order, track game-specific
state, or call an AI provider yet. Any nonempty player list can be stored;
multiplayer currently means passing the interface between players.

## Run with Docker

Install Docker Engine/Desktop with the Compose plugin, then from this folder:

```bash
docker compose up --build -d
```

Open http://localhost:8000. Create a game, enter rules and players, then record
moves. Saved games appear in the sidebar and reload after a restart.

```bash
docker compose logs -f app       # Show server logs
docker compose down              # Stop; keep the saved games
docker compose up --build -d     # Rebuild after code changes
```

The SQLite file is `/app/data/games.db` inside the container; the `game-data`
named volume stores it on the Docker host. SQLite is an embedded file database,
so it has no separate service, port, or database server. Do not run
`docker compose down -v` unless you intend to delete the saved games.

The published port is bound to localhost. To serve other computers, change it
to `"8000:8000"` (or a specific host interface). This starter has no user accounts
or access controls; shared hosting needs those plus HTTPS. Keep one app replica
with its database on a local disk. Put AI credentials in backend environment
variables and keep them out of frontend JavaScript and version control.

## Run locally without Docker

Python 3.12 is used in the container. For development:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flask --app backend.app:create_app run --debug --port 8000
```

Open the same URL. Local development creates `data/games.db` in this project.
The local database and Docker volume are separate. Set `DATABASE_PATH` to use
another file. Use the Flask debug server only for local development.

## Project layout

| Path | Role |
| --- | --- |
| `backend/app/__init__.py` | App factory, frontend serving, configuration |
| `backend/app/routes.py` | JSON API endpoints |
| `backend/app/db.py` | SQLite connections and schema initialization |
| `backend/app/schema.sql` | Games and moves tables |
| `backend/app/game_service.py` | Validation and game persistence |
| `backend/app/ai_client.py` | Future AI boundary; builds context from saved rules/history |
| `backend/tests/test_app.py` | Persistence, validation, API and static-file checks |
| `frontend/index.html` | Page structure |
| `frontend/styles.css` | Responsive styling |
| `frontend/app.js` | API requests and page updates |
| `Dockerfile` | Python container with Gunicorn |
| `compose.yaml` | Port, persistent storage, health check |
| `requirements.txt` | Bounded Python dependency versions |

Dependencies use major-version bounds rather than an exact lockfile. Once you
choose provider SDKs and a deployment environment, lock the tested versions.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | App/database connection check |
| GET | `/api/games` | List saved games |
| POST | `/api/games` | Create a game |
| GET | `/api/games/<id>` | Load rules, players, and move history |
| POST | `/api/games/<id>/moves` | Append a move |

Create body:

```json
{"title":"Space adventure","rules":"Explore a planet in turns.","players":["Ada","Lin"]}
```

Move body:

```json
{"player":"Ada","action":"Inspect the mysterious tower."}
```

Responses use JSON; successful creates return 201, invalid input returns 400,
and missing games return 404. Each move receives a consecutive turn number.
Parameterized SQL handles stored text. Rules and history remain in SQLite;
localStorage only remembers which game to open in your browser.

## Next AI steps

1. Add an API adapter to `ai_client.py` to generate a structured game definition.
2. Add a move evaluator that receives `build_context(game)` plus a proposed move.
3. Validate its structured output before storing accepted moves and state.

Keep `routes.py` thin and orchestration in `game_service.py`. Do not hold SQLite
write locks during network calls. When adding state updates, include a version
check so a response based on an older turn cannot overwrite a newer turn.
Complete history should stay stored even if you later send only a summary and
recent moves to a model to fit its context window.

Schema initialization only creates missing tables. For future schema changes,
add migrations rather than editing existing databases implicitly.

## Verify

After installing dependencies, from the project root:

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

The tests use disposable SQLite files. Check actual Docker deployment with
`docker compose up --build -d` and `docker compose ps`; this package was tested
with Python API tests and a local Gunicorn smoke test, not an actual Docker
build in the authoring environment.
