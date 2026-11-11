# Unlimited Games — starter

A small Python + plain HTML/CSS/JavaScript project. Flask serves both the frontend
and JSON API from one process. Python's built-in `sqlite3` stores games, rules,
players, and the complete ordered move history. Docker runs Gunicorn and keeps
the SQLite database in a persistent volume. No Node build step or separate
database container is needed.

Create a game by describing an idea and optionally choosing a genre and complexity.
AI returns a structured design with a premise, objective, setup, turns, rules,
and ending. Ask for revisions as often as needed, then approve and save the idea.
Saved ideas can start multiple independent play sessions with different players
and separate move histories. Revising a saved idea produces a new draft; the
saved version remains available until you approve the new version as another idea.
Drafts stay in the current page until saved; reloading discards unsaved work.

Play currently uses manual, pass-the-screen move recording. Players follow the
generated rules and resolve outcomes themselves; AI does not referee moves or
maintain game-specific state.

## AI configuration

Set `OPENAI_API_KEY` in the project's root `.env` file before starting the app.
Local runs load this file automatically; existing environment variables take
precedence. Docker Compose also reads the root `.env` file automatically and
passes the key into the container without copying the file into the image.
Optionally set `OPENAI_MODEL` (default `gpt-4o-mini`) to a model supporting Chat
Completions JSON mode. Docker Compose passes both variables to the backend.
Set these entries in `.env` before `docker compose up --build -d`.
Without a key, saved ideas and sessions remain accessible, but generation returns
an actionable configuration error. Keys stay on the server. Idea prompts,
selected preferences, and the current design for revisions are sent to OpenAI.

The adapter uses [OpenAI JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)
and validates every required field before showing the result. Provider errors,
timeouts, incomplete responses, and malformed definitions leave the current draft
intact so the user can retry.

## Run with Docker

Install Docker Engine/Desktop with the Compose plugin, then from this folder:

```bash
docker compose up --build -d
```

Open http://localhost:8000. Generate and revise an idea, approve it, then add
players to start a session. Saved ideas and sessions appear in the sidebar.

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
| `backend/app/ai_client.py` | AI generation adapter; builds context from saved rules/history |
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
| POST | `/api/games` | Create a manual session (legacy API) |
| POST | `/api/ideas/draft` | Generate or revise an unsaved idea |
| GET | `/api/ideas` | List approved ideas |
| POST | `/api/ideas` | Save an approved structured idea |
| POST | `/api/ideas/<id>/instances` | Start an independent session with players |
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

## Design and persistence

`POST /api/ideas/draft` takes `prompt`, optional `genre` and `complexity`, and
optional `idea` for revisions. It returns `{ "idea": ... }` without persisting it.
`POST /api/ideas` takes `{ "idea": ... }`; required string fields are `title`,
`premise`, `objective`, `setup`, `turns`, `rules`, and `ending`.
`POST /api/ideas/<id>/instances` takes `{ "players": ["Ada", "Lin"] }`.
Each session snapshots the complete design into its rules.

Schema initialization adds `ideas` and `idea_instances` tables alongside existing
games and moves, preserving existing records. AI calls happen before any database
write transaction. Further AI play support can use `build_context(game)` for the
rules, players, and ordered move history.

## Verify

After installing dependencies, from the project root:

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

The tests use disposable SQLite files. Check actual Docker deployment with
`docker compose up --build -d` and `docker compose ps`; this package was tested
with Python API tests and a local Gunicorn smoke test, not an actual Docker
build in the authoring environment.
