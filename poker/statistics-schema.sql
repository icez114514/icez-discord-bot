BEGIN IMMEDIATE;
ALTER TABLE accounts ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0;
CREATE TABLE hand_statistics (
    hand_id TEXT NOT NULL REFERENCES hands,
    user_id TEXT NOT NULL REFERENCES accounts,
    settled_at REAL NOT NULL,
    classification TEXT NOT NULL CHECK(classification IN ('human','mixed')),
    formula_version INTEGER NOT NULL,
    net INTEGER NOT NULL,
    counts TEXT NOT NULL,
    PRIMARY KEY(hand_id,user_id)
);
CREATE INDEX statistics_period ON hand_statistics(settled_at,classification);
CREATE TABLE management_commands(command_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE management_audit(
    id INTEGER PRIMARY KEY, command_id TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, target TEXT NOT NULL, reason TEXT NOT NULL,
    created_at REAL NOT NULL, before_state TEXT NOT NULL, after_state TEXT NOT NULL
);
CREATE TRIGGER management_no_update BEFORE UPDATE ON management_audit BEGIN SELECT RAISE(ABORT, 'immutable_audit'); END;
CREATE TRIGGER management_no_delete BEFORE DELETE ON management_audit BEGIN SELECT RAISE(ABORT, 'immutable_audit'); END;
COMMIT;
