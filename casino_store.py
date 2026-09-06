"""Durable casino operations sharing CrystalStore's account lock and connection."""

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from casino_rules import Bet, CasinoError, outcome
from database import CrystalStore, DatabaseError


@dataclass(frozen=True)
class Preferences:
    bet: Bet
    custom_base: int | None
    custom_multiplier: int | None
    token: UUID | None


@dataclass(frozen=True)
class Game:
    id: UUID
    user_id: int
    bet: Bet
    wager: int
    dice: list
    status: str
    outcome: str | None
    returned: int
    balance_after: int
    version: int
    dismissed: bool

    @property
    def net(self) -> int:
        return self.returned - self.wager


@dataclass(frozen=True)
class Entry:
    kind: str
    amount: int
    before: int
    after: int


def read_game(row) -> Game:
    return Game(row['id'], int(row['user_id']), Bet(int(row['base']), int(row['multiplier'])),
                int(row['wager']), row['dice'], row['status'], row['outcome'],
                int(row['returned']), int(row['balance_after']), row['version'], row['dismissed'])


def read_preferences(row) -> Preferences:
    return Preferences(Bet(int(row['base']), int(row['multiplier'])),
                       None if row['custom_base'] is None else int(row['custom_base']),
                       None if row['custom_multiplier'] is None else int(row['custom_multiplier']), row['token'])


class CasinoStore:
    def __init__(self, crystals: CrystalStore, *, roll: Callable | None = None):
        self.crystals = crystals
        self.roll = roll or (lambda: tuple(secrets.randbelow(6) + 1 for _ in range(6)))
        self.tables = {name: sql.Identifier(crystals.schema, table) for name, table in {
            'accounts': 'crystal_accounts', 'preferences': 'casino_preferences',
            'games': 'casino_games', 'ledger': 'casino_ledger',
        }.items()}

    async def execute(self, conn, query: str, params=()):
        conn.row_factory = dict_row
        return await conn.execute(sql.SQL(query).format(**self.tables), params)

    async def initialize(self):
        async with self.crystals.connection() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(431483260468592641)")
            for statement in Path(__file__).with_name('casino_schema.sql').read_text(encoding='utf-8').split(';'):
                if statement.strip():
                    await self.execute(conn, statement)

    async def check(self):
        async with self.crystals.connection(read_only=True) as conn:
            for table in ('preferences', 'games', 'ledger'):
                await self.execute(conn, 'SELECT * FROM {' + table + '} LIMIT 0')

    async def balance(self, user_id: int) -> int | None:
        async with self.crystals.connection(read_only=True) as conn:
            row = await (await self.execute(conn, 'SELECT balance FROM {accounts} WHERE user_id=%s', (user_id,))).fetchone()
            return None if row is None else int(row['balance'])

    async def lock_account(self, conn, user_id):
        row = await (await self.execute(conn, 'SELECT balance FROM {accounts} WHERE user_id=%s FOR UPDATE', (user_id,))).fetchone()
        if row is None:
            raise CasinoError('尚無水晶帳戶，請先使用 /水晶 簽到。')
        return int(row['balance'])

    async def preferences(self, user_id: int) -> Preferences:
        async with self.crystals.connection(read_only=True) as conn:
            row = await (await self.execute(conn, 'SELECT * FROM {preferences} WHERE user_id=%s', (user_id,))).fetchone()
            return read_preferences(row) if row else Preferences(Bet(), None, None, None)

    async def settings(self, user_id: int) -> Preferences:
        async with self.crystals.connection() as conn:
            await self.lock_account(conn, user_id)
            await self.require_idle(conn, user_id)
            await self.execute(conn, 'INSERT INTO {preferences}(user_id) VALUES (%s) ON CONFLICT DO NOTHING', (user_id,))
            row = await (await self.execute(conn, 'UPDATE {preferences} SET token=%s WHERE user_id=%s RETURNING *', (uuid4(), user_id))).fetchone()
        return read_preferences(row)

    async def require_idle(self, conn, user_id):
        row = await (await self.execute(conn, "SELECT id FROM {games} WHERE user_id=%s AND status='active'", (user_id,))).fetchone()
        if row:
            raise CasinoError('已有進行中的牌局，請使用 /賭場 恢復。')

    async def choose(self, user_id: int, token: UUID | None, *, base=None, multiplier=None, custom=False) -> Preferences:
        async with self.crystals.connection() as conn:
            await self.lock_account(conn, user_id)
            row = await (await self.execute(conn, 'SELECT * FROM {preferences} WHERE user_id=%s', (user_id,))).fetchone()
            if row is None or token is None or row['token'] != token:
                raise CasinoError('此設定面板已失效，請使用 /賭場。')
            bet = Bet(int(row['base']) if base is None else base, int(row['multiplier']) if multiplier is None else multiplier)
            row = await (await self.execute(conn, '''UPDATE {preferences} SET base=%s, multiplier=%s,
                custom_base=%s, custom_multiplier=%s, token=%s WHERE user_id=%s RETURNING *''',
                (bet.base, bet.multiplier, base if custom and base is not None else row['custom_base'],
                 multiplier if custom and multiplier is not None else row['custom_multiplier'], uuid4(), user_id))).fetchone()
        return read_preferences(row)

    async def replay(self, user_id: int, game_id: UUID) -> Game:
        return await self.start(user_id, uuid5(NAMESPACE_URL, 'casino:replay:' + str(game_id)), parent_id=game_id)

    async def start(self, user_id: int, token: UUID | None, *, game='dice', parent_id=None) -> Game:
        if game != 'dice':
            raise CasinoError('21 點尚未開放，不會扣款。')
        try:
            async with self.crystals.connection() as conn:
                balance = await self.lock_account(conn, user_id)
                row = await (await self.execute(conn, 'SELECT * FROM {games} WHERE operation_id=%s AND user_id=%s', (token, user_id))).fetchone()
                if row is None:
                    await self.require_idle(conn, user_id)
                    if parent_id is None:
                        pref = await (await self.execute(conn, 'SELECT * FROM {preferences} WHERE user_id=%s', (user_id,))).fetchone()
                        if pref is None or token is None or pref['token'] != token:
                            raise CasinoError('此設定面板已失效，請使用 /賭場。')
                        bet = Bet(int(pref['base']), int(pref['multiplier']))
                    else:
                        parent = await (await self.execute(conn, 'SELECT * FROM {games} WHERE id=%s AND user_id=%s', (parent_id, user_id))).fetchone()
                        if parent is None or parent['status'] == 'active' or parent['dismissed']:
                            raise CasinoError('此結算面板已失效，請使用 /賭場。')
                        bet = Bet(int(parent['base']), int(parent['multiplier']))
                        await self.execute(conn, 'UPDATE {games} SET dismissed=TRUE WHERE id=%s', (parent_id,))
                    row = await self.create_game(conn, user_id, token, bet, balance, parent_id)
                    await self.execute(conn, 'UPDATE {preferences} SET token=NULL WHERE user_id=%s', (user_id,))
                game_id = row['id']
        except DatabaseError:
            # A lost COMMIT acknowledgement is neither a failure nor permission to retry a debit.
            async with self.crystals.connection(read_only=True) as conn:
                row = await (await self.execute(conn, 'SELECT id FROM {games} WHERE operation_id=%s AND user_id=%s', (token, user_id))).fetchone()
                if row is None:
                    raise
                game_id = row['id']
        return await self.settle(user_id, game_id)

    async def create_game(self, conn, user_id, operation_id, bet, balance, parent_id=None):
        if balance < bet.total:
            raise CasinoError('水晶餘額不足，無法開局。')
        dice = list(self.roll())
        if len(dice) != 6:
            raise ValueError('Expected six dice')
        outcome(dice[:3], dice[3:])
        game_id = uuid4()
        row = await (await self.execute(conn, '''INSERT INTO {games}
            (id,user_id,game,operation_id,parent_id,base,multiplier,wager,dice,status,balance_after)
            VALUES (%s,%s,'dice',%s,%s,%s,%s,%s,%s,'active',%s) RETURNING *''',
            (game_id, user_id, operation_id, parent_id, bet.base, bet.multiplier, bet.total, Jsonb(dice), balance - bet.total))).fetchone()
        await self.transfer(conn, user_id, game_id, 'stake', -bet.total, balance)
        return row

    async def transfer(self, conn, user_id, game_id, kind, amount, before):
        await self.execute(conn, 'UPDATE {accounts} SET balance=%s WHERE user_id=%s', (before + amount, user_id))
        await self.execute(conn, '''INSERT INTO {ledger}(game_id,user_id,kind,amount,balance_before,balance_after)
            VALUES (%s,%s,%s,%s,%s,%s)''', (game_id, user_id, kind, amount, before, before + amount))

    async def leave(self, user_id: int, *, game_id=None, token=None):
        async with self.crystals.connection() as conn:
            await self.lock_account(conn, user_id)
            await self.require_idle(conn, user_id)
            if game_id is not None:
                row = await (await self.execute(conn, 'SELECT dismissed FROM {games} WHERE id=%s AND user_id=%s', (game_id, user_id))).fetchone()
                if row is None or row['dismissed']:
                    raise CasinoError('此結算面板已失效，請使用 /賭場。')
                await self.execute(conn, 'UPDATE {games} SET dismissed=TRUE WHERE id=%s', (game_id,))
            if token is not None:
                row = await (await self.execute(conn, 'SELECT token FROM {preferences} WHERE user_id=%s', (user_id,))).fetchone()
                if row is None or row['token'] != token:
                    raise CasinoError('此設定面板已失效，請使用 /賭場。')
            await self.execute(conn, 'UPDATE {preferences} SET token=NULL WHERE user_id=%s', (user_id,))

    async def settle(self, user_id: int, game_id: UUID) -> Game:
        try:
            return await self.settle_transaction(user_id, game_id)
        except DatabaseError:
            async with self.crystals.connection(read_only=True) as conn:
                row = await (await self.execute(conn, 'SELECT * FROM {games} WHERE id=%s AND user_id=%s', (game_id, user_id))).fetchone()
                if row is None or row['status'] == 'active':
                    raise
                return read_game(row)

    async def settle_transaction(self, user_id: int, game_id: UUID) -> Game:
        async with self.crystals.connection() as conn:
            balance = await self.lock_account(conn, user_id)
            row = await (await self.execute(conn, 'SELECT * FROM {games} WHERE id=%s AND user_id=%s FOR UPDATE', (game_id, user_id))).fetchone()
            if row is None:
                raise CasinoError('找不到你的牌局。')
            if row['status'] == 'active':
                if row['game'] != 'dice':
                    raise CasinoError('此牌局需要對應遊戲的恢復功能，未執行退款。')
                try:
                    result = outcome(row['dice'][:3], row['dice'][3:])
                    returned = int(row['wager']) * {'win': 2, 'tie': 1, 'loss': 0}[result]
                    status, kind, reason = 'settled', 'payout', None
                except (ValueError, TypeError, KeyError):
                    result, returned = 'void', int(row['wager'])
                    status, kind, reason = 'void', 'refund', 'invalid_persisted_dice'
                await self.transfer(conn, user_id, game_id, kind, returned, balance)
                row = await (await self.execute(conn, '''UPDATE {games} SET status=%s,outcome=%s,
                    returned=%s,balance_after=%s,version=version+1,finished_at=clock_timestamp(),reason=%s
                    WHERE id=%s RETURNING *''', (status, result, returned, balance + returned, reason, game_id))).fetchone()
        return read_game(row)

    async def recover(self, user_id: int) -> Game | None:
        async with self.crystals.connection(read_only=True) as conn:
            row = await (await self.execute(conn, '''SELECT * FROM {games} WHERE user_id=%s
                AND (status='active' OR NOT dismissed) ORDER BY (status='active') DESC,created_at DESC LIMIT 1''', (user_id,))).fetchone()
        if row is None:
            return None
        return await self.settle(user_id, row['id']) if row['status'] == 'active' else read_game(row)

    async def ledger(self, user_id: int, game_id: UUID) -> list[Entry]:
        async with self.crystals.connection(read_only=True) as conn:
            rows = await (await self.execute(conn, 'SELECT * FROM {ledger} WHERE user_id=%s AND game_id=%s ORDER BY id', (user_id, game_id))).fetchall()
            return [Entry(r['kind'], int(r['amount']), int(r['balance_before']), int(r['balance_after'])) for r in rows]
