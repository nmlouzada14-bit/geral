-- Production schema before multi-channel migration.
PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, role TEXT NOT NULL, password TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, color TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS formats(id INTEGER PRIMARY KEY, name TEXT NOT NULL, channel_id INTEGER NOT NULL REFERENCES channels(id), responsible_id INTEGER REFERENCES users(id), color TEXT NOT NULL, frequency TEXT NOT NULL, active_from TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', deadline TEXT NOT NULL, responsible_id INTEGER REFERENCES users(id), channel_id INTEGER REFERENCES channels(id), format_id INTEGER REFERENCES formats(id), status TEXT NOT NULL, frequency TEXT NOT NULL DEFAULT '{}', batch TEXT, slot TEXT UNIQUE, version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id), name TEXT NOT NULL, disk TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at REAL NOT NULL);
