CREATE TABLE IF NOT EXISTS {preferences} (
    user_id NUMERIC(20,0) PRIMARY KEY REFERENCES {accounts}(user_id),
    base NUMERIC NOT NULL DEFAULT 10 CHECK (base >= 2 AND base < 'Infinity'::numeric AND mod(base, 2) = 0),
    multiplier NUMERIC NOT NULL DEFAULT 1 CHECK (multiplier >= 1 AND multiplier < 'Infinity'::numeric AND multiplier = trunc(multiplier)),
    custom_base NUMERIC CHECK (custom_base >= 2 AND custom_base < 'Infinity'::numeric AND mod(custom_base, 2) = 0),
    custom_multiplier NUMERIC CHECK (custom_multiplier >= 1 AND custom_multiplier < 'Infinity'::numeric AND custom_multiplier = trunc(custom_multiplier)),
    token UUID
);
CREATE TABLE IF NOT EXISTS {games} (
    id UUID PRIMARY KEY,
    user_id NUMERIC(20,0) NOT NULL REFERENCES {accounts}(user_id),
    game TEXT NOT NULL,
    operation_id UUID NOT NULL UNIQUE,
    parent_id UUID UNIQUE REFERENCES {games}(id),
    base NUMERIC NOT NULL CHECK (base >= 2 AND base < 'Infinity'::numeric AND mod(base, 2) = 0),
    multiplier NUMERIC NOT NULL CHECK (multiplier >= 1 AND multiplier < 'Infinity'::numeric AND multiplier = trunc(multiplier)),
    wager NUMERIC NOT NULL CHECK (wager = base * multiplier),
    dice JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'settled', 'void')),
    outcome TEXT CHECK (outcome IN ('win', 'loss', 'tie', 'void')),
    returned NUMERIC NOT NULL DEFAULT 0 CHECK (returned >= 0 AND returned < 'Infinity'::numeric AND returned = trunc(returned)),
    balance_after NUMERIC NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    dismissed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    reason TEXT,
    CHECK ((status = 'active' AND outcome IS NULL AND finished_at IS NULL) OR
           (status <> 'active' AND outcome IS NOT NULL AND finished_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS casino_one_active ON {games}(user_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS casino_recent ON {games}(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS {ledger} (
    id BIGSERIAL PRIMARY KEY,
    game_id UUID NOT NULL REFERENCES {games}(id),
    user_id NUMERIC(20,0) NOT NULL REFERENCES {accounts}(user_id),
    kind TEXT NOT NULL CHECK (kind IN ('stake', 'payout', 'refund')),
    amount NUMERIC NOT NULL CHECK (amount < 'Infinity'::numeric AND amount > '-Infinity'::numeric AND amount = trunc(amount)),
    balance_before NUMERIC NOT NULL CHECK (balance_before >= 0),
    balance_after NUMERIC NOT NULL CHECK (balance_after >= 0 AND balance_after = balance_before + amount),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(game_id, kind)
);
CREATE UNIQUE INDEX IF NOT EXISTS casino_one_return ON {ledger}(game_id) WHERE kind IN ('payout', 'refund');
ALTER TABLE {games} ADD COLUMN IF NOT EXISTS cards JSONB;
ALTER TABLE {games} ADD COLUMN IF NOT EXISTS deadline TIMESTAMPTZ;
ALTER TABLE {ledger} DROP CONSTRAINT IF EXISTS casino_ledger_kind_check;
ALTER TABLE {ledger} ADD CONSTRAINT casino_ledger_kind_check CHECK (kind IN ('stake', 'double', 'payout', 'refund'));
