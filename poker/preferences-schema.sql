BEGIN IMMEDIATE;
CREATE TABLE account_preferences(
    user_id TEXT PRIMARY KEY REFERENCES accounts(user_id),
    theme TEXT NOT NULL DEFAULT 'classic_walnut'
);
PRAGMA user_version=3;
COMMIT;
