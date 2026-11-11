CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    rules TEXT NOT NULL,
    players_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS moves (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES games(id),
    turn_number INTEGER NOT NULL,
    player TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(game_id, turn_number)
);

-- Additive schema upgrade: existing games and move histories are preserved.
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS idea_instances (
    game_id INTEGER PRIMARY KEY REFERENCES games(id),
    idea_id INTEGER NOT NULL REFERENCES ideas(id)
);
