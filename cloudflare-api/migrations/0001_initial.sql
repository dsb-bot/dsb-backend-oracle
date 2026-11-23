CREATE TABLE IF NOT EXISTS plans (
    date TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    html_content BLOB NOT NULL,
    content_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_successful_sync TEXT
);

INSERT OR IGNORE INTO sync_state (id, last_successful_sync) VALUES (1, NULL);
