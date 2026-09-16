BEGIN IMMEDIATE;
CREATE TABLE account_voices(
    user_id TEXT PRIMARY KEY REFERENCES accounts(user_id),
    voice_pack TEXT NOT NULL CHECK(voice_pack IN ('oneesan','shoujo','nekomimi'))
);
PRAGMA user_version=5;
COMMIT;
