BEGIN IMMEDIATE;
CREATE TABLE game_tables(table_id TEXT PRIMARY KEY, state TEXT NOT NULL);
CREATE TABLE game_commands(command_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE game_audit(id INTEGER PRIMARY KEY, table_id TEXT NOT NULL, event TEXT NOT NULL, created_at REAL NOT NULL);
PRAGMA user_version=2;
COMMIT;