BEGIN IMMEDIATE;
CREATE TABLE accounts (
    user_id TEXT PRIMARY KEY, presence_revision INTEGER NOT NULL DEFAULT 0, login_revision INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 0 CHECK(available BETWEEN 0 AND 9000000000000000),
    table_chips INTEGER NOT NULL DEFAULT 0 CHECK(table_chips BETWEEN 0 AND 9000000000000000),
    in_flight INTEGER NOT NULL DEFAULT 0 CHECK(in_flight BETWEEN 0 AND 9000000000000000),
    settled INTEGER NOT NULL DEFAULT 0 CHECK(settled BETWEEN 0 AND 9000000000000000),
    time_bank INTEGER NOT NULL DEFAULT 60 CHECK(time_bank BETWEEN 0 AND 60),
    hand_progress INTEGER NOT NULL DEFAULT 0 CHECK(hand_progress BETWEEN 0 AND 9)
);
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES accounts, created_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE TABLE ledger (
    id INTEGER PRIMARY KEY,
    command_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES accounts,
    source TEXT NOT NULL,
    reason TEXT NOT NULL,
    available_delta INTEGER NOT NULL DEFAULT 0,
    table_delta INTEGER NOT NULL DEFAULT 0,
    flight_delta INTEGER NOT NULL DEFAULT 0,
    settled_delta INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER ledger_no_update BEFORE UPDATE ON ledger BEGIN SELECT RAISE(ABORT, 'immutable_ledger'); END;
CREATE TRIGGER ledger_no_delete BEFORE DELETE ON ledger BEGIN SELECT RAISE(ABORT, 'immutable_ledger'); END;
CREATE TABLE commands(command_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE seats(user_id TEXT PRIMARY KEY REFERENCES accounts, table_id TEXT NOT NULL);
CREATE TABLE subsidies(user_id TEXT REFERENCES accounts, day TEXT, command_id TEXT UNIQUE NOT NULL, PRIMARY KEY(user_id,day));
CREATE TABLE hands(hand_id TEXT PRIMARY KEY, table_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','settled','void')), snapshot TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX table_active_hand ON hands(table_id) WHERE status='active';
CREATE TABLE participants(hand_id TEXT REFERENCES hands, user_id TEXT REFERENCES accounts, contribution INTEGER NOT NULL DEFAULT 0 CHECK(contribution BETWEEN 0 AND 9000000000000000), PRIMARY KEY(hand_id,user_id));
CREATE TABLE settlements(hand_id TEXT PRIMARY KEY REFERENCES hands, command_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL);
CREATE TABLE hand_events(id INTEGER PRIMARY KEY, hand_id TEXT REFERENCES hands, command_id TEXT UNIQUE NOT NULL, event TEXT NOT NULL);
CREATE TABLE statistics(hand_id TEXT REFERENCES hands, user_id TEXT REFERENCES accounts, net INTEGER NOT NULL, opportunities TEXT NOT NULL, PRIMARY KEY(hand_id,user_id));
CREATE TABLE invitations(table_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, version INTEGER NOT NULL DEFAULT 0, owner_id TEXT REFERENCES accounts);
CREATE TABLE admin_audit(id INTEGER PRIMARY KEY, command_id TEXT UNIQUE NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE presence(connection_id TEXT PRIMARY KEY, session_hash TEXT NOT NULL REFERENCES sessions(token_hash), until_at REAL NOT NULL);
CREATE TABLE oauth_states(state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE scans(day TEXT PRIMARY KEY, started_at REAL NOT NULL);
CREATE TABLE scan_members(day TEXT REFERENCES scans, user_id TEXT REFERENCES accounts, status TEXT NOT NULL, presence_revision INTEGER NOT NULL, login_revision INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, PRIMARY KEY(day,user_id));
CREATE TABLE action_clocks(hand_id TEXT REFERENCES hands, user_id TEXT REFERENCES accounts, opportunity_id TEXT NOT NULL, deadline REAL NOT NULL, extensions INTEGER NOT NULL DEFAULT 0 CHECK(extensions BETWEEN 0 AND 4), active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(hand_id,opportunity_id));
PRAGMA user_version=1;
COMMIT;
