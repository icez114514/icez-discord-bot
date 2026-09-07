"""Atomic administrative grants, separate from casino revenue."""
from dataclasses import dataclass
from psycopg import sql
from database import DatabaseError, MAX_ID


@dataclass(frozen=True)
class Grant:
    message_id: int
    count: int
    amount: int


class RewardStore:
    def __init__(self, crystals):
        self.crystals = crystals
        self.operations = sql.Identifier(crystals.schema, 'reward_operations')
        self.entries = sql.Identifier(crystals.schema, 'reward_entries')

    async def initialize(self):
        async with self.crystals.connection() as conn:
            await conn.execute('SELECT pg_advisory_xact_lock(431483260468592641)')
            await conn.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                message_id NUMERIC(20,0) PRIMARY KEY,
                actor_id NUMERIC(20,0) NOT NULL,
                guild_id NUMERIC(20,0) NOT NULL,
                channel_id NUMERIC(20,0) NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('single','all')),
                amount NUMERIC NOT NULL CHECK (amount > 0 AND amount < 'Infinity'::numeric AND amount=trunc(amount)),
                recipient_count INTEGER NOT NULL CHECK (recipient_count > 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
            )""").format(self.operations))
            await conn.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                message_id NUMERIC(20,0) NOT NULL REFERENCES {}(message_id),
                user_id NUMERIC(20,0) NOT NULL REFERENCES {}(user_id),
                amount NUMERIC NOT NULL CHECK (amount > 0 AND amount < 'Infinity'::numeric AND amount=trunc(amount)),
                balance_before NUMERIC NOT NULL CHECK (balance_before >= 0 AND balance_before < 'Infinity'::numeric AND balance_before=trunc(balance_before)),
                balance_after NUMERIC NOT NULL CHECK (balance_after=balance_before+amount),
                created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                PRIMARY KEY(message_id,user_id)
            )""").format(self.entries, self.operations, self.crystals.table))

    async def check(self):
        async with self.crystals.connection(read_only=True) as conn:
            await conn.execute(sql.SQL('SELECT message_id,actor_id,guild_id,channel_id,mode,amount,recipient_count,created_at FROM {} LIMIT 0').format(self.operations))
            await conn.execute(sql.SQL('SELECT message_id,user_id,amount,balance_before,balance_after,created_at FROM {} LIMIT 0').format(self.entries))

    async def account_ids(self):
        async with self.crystals.connection(read_only=True) as conn:
            rows = await (await conn.execute(sql.SQL('SELECT user_id FROM {} ORDER BY user_id').format(self.crystals.table))).fetchall()
        return [int(row[0]) for row in rows]

    async def find(self, message_id):
        async with self.crystals.connection(read_only=True) as conn:
            row = await (await conn.execute(sql.SQL('SELECT recipient_count,amount FROM {} WHERE message_id=%s').format(self.operations), (message_id,))).fetchone()
        return Grant(message_id, int(row[0]), int(row[1])) if row else None

    async def grant(self, message_id, actor_id, guild_id, channel_id, mode, amount, recipients):
        recipients = dict(recipients)
        if mode not in ('single', 'all') or not recipients or (mode == 'single' and len(recipients) != 1):
            raise ValueError('Invalid grant recipients')
        if type(amount) is not int or amount <= 0:
            raise ValueError('Invalid grant amount')
        if any(type(uid) is not int or not 0 < uid <= MAX_ID for uid in (message_id,actor_id,guild_id,channel_id,*recipients)):
            raise ValueError('Invalid grant ID')
        try:
            async with self.crystals.connection() as conn:
                inserted = await (await conn.execute(sql.SQL("""INSERT INTO {} (message_id,actor_id,guild_id,channel_id,mode,amount,recipient_count)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (message_id) DO NOTHING RETURNING message_id""").format(self.operations),
                    (message_id,actor_id,guild_id,channel_id,mode,amount,len(recipients)))).fetchone()
                if inserted is None:
                    row = await (await conn.execute(sql.SQL('SELECT recipient_count,amount FROM {} WHERE message_id=%s').format(self.operations),(message_id,))).fetchone()
                    result = Grant(message_id,int(row[0]),int(row[1]))
                else:
                    for uid,name in sorted(recipients.items()):
                        if mode == 'single':
                            await conn.execute(sql.SQL('INSERT INTO {} (user_id,balance,display_name) VALUES (%s,0,%s) ON CONFLICT (user_id) DO NOTHING').format(self.crystals.table),(uid,name[:128]))
                        row = await (await conn.execute(sql.SQL('SELECT balance FROM {} WHERE user_id=%s FOR UPDATE').format(self.crystals.table),(uid,))).fetchone()
                        if row is None:
                            raise DatabaseError('Grant recipient account disappeared; no rewards applied.')
                        before = int(row[0])
                        await conn.execute(sql.SQL("""WITH updated AS (
                            UPDATE {} SET balance=balance+%s WHERE user_id=%s RETURNING balance
                        ) INSERT INTO {} (message_id,user_id,amount,balance_before,balance_after)
                        SELECT %s,%s,%s,%s,balance FROM updated""").format(self.crystals.table,self.entries),(amount,uid,message_id,uid,amount,before))
                    result = Grant(message_id,len(recipients),amount)
            return result
        except DatabaseError:
            # Resolve an uncertain commit by reading only; never repeat the writes.
            existing = await self.find(message_id)
            if existing is not None:
                return existing
            raise
