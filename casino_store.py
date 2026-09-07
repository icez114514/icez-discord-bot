"""Durable casino operations sharing CrystalStore's account lock and connection."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from casino_rules import Bet, CasinoError, outcome
import blackjack
from database import CrystalStore, DatabaseError


@dataclass(frozen=True)
class Preferences:
    bet: Bet
    custom_base: int | None
    custom_multiplier: int | None
    token: UUID | None


@dataclass(frozen=True)
class LobbySnapshot:
    balance: int | None


@dataclass(frozen=True)
class SettingsSnapshot:
    preferences: Preferences
    balance: int


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
    game: str = 'dice'
    player: tuple = ()
    dealer: tuple = ()
    deadline: datetime | None = None

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
    state = row.get('cards') if isinstance(row.get('cards'), dict) else {}
    player = tuple(state.get('player', ())) if row['status'] != 'void' else ()
    dealer = tuple(state.get('dealer', ())) if row['status'] != 'void' else ()
    if row['status'] == 'active' and row['game'] == 'blackjack':
        dealer = dealer[:1] + (None,)
    return Game(row['id'], int(row['user_id']), Bet(int(row['base']), int(row['multiplier'])),
                int(row['wager']), row['dice'], row['status'], row['outcome'],
                int(row['returned']), int(row['balance_after']), row['version'], row['dismissed'],
                row['game'], player, dealer, row.get('deadline'))


def read_preferences(row) -> Preferences:
    return Preferences(Bet(int(row['base']), int(row['multiplier'])),
                       None if row['custom_base'] is None else int(row['custom_base']),
                       None if row['custom_multiplier'] is None else int(row['custom_multiplier']), row['token'])


class CasinoStore:
    def __init__(self, crystals: CrystalStore, *, roll: Callable | None = None,
                 deck: Callable | None = None, clock: Callable | None = None):
        self.crystals = crystals
        self.deck = deck or blackjack.shuffled_deck
        self.clock = clock or (lambda: datetime.now(timezone.utc))
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
            # PostgreSQL may derive the old cross-column CHECK name differently.
            constraints = await (await conn.execute('''SELECT conname, pg_get_constraintdef(oid) AS definition
                FROM pg_constraint WHERE conrelid=%s::regclass AND contype='c' ''',
                (self.tables['games'].as_string(conn),))).fetchall()
            for constraint in constraints:
                if constraint['definition'] == 'CHECK ((wager = (base * multiplier)))':
                    await conn.execute(sql.SQL('ALTER TABLE {} DROP CONSTRAINT {}').format(
                        self.tables['games'], sql.Identifier(constraint['conname'])))
            await self.execute(conn, 'ALTER TABLE {games} DROP CONSTRAINT IF EXISTS casino_wager_valid')
            await self.execute(conn, '''ALTER TABLE {games} ADD CONSTRAINT casino_wager_valid CHECK (
                wager = base * multiplier OR (game='blackjack' AND wager = 2 * base * multiplier))''')

    async def check(self):
        async with self.crystals.connection(read_only=True) as conn:
            for table in ('preferences', 'games', 'ledger'):
                await self.execute(conn, 'SELECT * FROM {' + table + '} LIMIT 0')
            await self.execute(conn, 'SELECT cards,deadline FROM {games} LIMIT 0')
            migrated = await (await conn.execute('''SELECT count(*) AS count FROM pg_constraint
                WHERE (conrelid=%s::regclass AND conname='casino_wager_valid')
                   OR (conrelid=%s::regclass AND conname='casino_ledger_kind_check'
                       AND position('double' in pg_get_constraintdef(oid)) > 0)''',
                (self.tables['games'].as_string(conn), self.tables['ledger'].as_string(conn)))).fetchone()
            if migrated['count'] != 2:
                raise DatabaseError('Casino schema is outdated. Run: python -m database migrate')

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

    async def open_panel(self, user_id: int, *, settings=False, game_id=None, token=None):
        """Validate the source and return a committed panel snapshot in one checkout."""
        async with self.crystals.connection() as conn:
            account = await (await self.execute(conn,
                'SELECT balance FROM {accounts} WHERE user_id=%s FOR UPDATE', (user_id,))).fetchone()
            if account is None:
                if settings or game_id is not None or token is not None:
                    raise CasinoError('尚無水晶帳戶，請先使用 /水晶 簽到。')
                return LobbySnapshot(None)
            balance = int(account['balance'])
            if game_id is not None or token is not None:
                await self.validate_departure(conn, user_id, game_id=game_id, token=token)
            else:
                row = await (await self.execute(conn, """SELECT * FROM {games} WHERE user_id=%s
                    AND (status='active' OR NOT dismissed)
                    ORDER BY (status='active') DESC,created_at DESC LIMIT 1 FOR UPDATE""", (user_id,))).fetchone()
                if row is not None:
                    return await self.resolve_game(conn, row, balance)
            if settings:
                prefs = await self.new_settings(conn, user_id)
                return SettingsSnapshot(prefs, balance)
            await self.execute(conn, 'UPDATE {preferences} SET token=NULL WHERE user_id=%s', (user_id,))
            return LobbySnapshot(balance)

    async def new_settings(self, conn, user_id):
        row = await (await self.execute(conn, """INSERT INTO {preferences}(user_id,token)
            VALUES (%s,%s) ON CONFLICT (user_id) DO UPDATE SET token=EXCLUDED.token
            RETURNING *""", (user_id, uuid4()))).fetchone()
        return read_preferences(row)

    async def settings(self, user_id: int) -> Preferences:
        async with self.crystals.connection() as conn:
            await self.lock_account(conn, user_id)
            await self.require_idle(conn, user_id)
            return await self.new_settings(conn, user_id)

    async def require_idle(self, conn, user_id):
        row = await (await self.execute(conn, "SELECT id FROM {games} WHERE user_id=%s AND status='active'", (user_id,))).fetchone()
        if row:
            raise CasinoError('已有進行中的牌局，請使用 /賭場 恢復。')

    async def choose(self, user_id: int, token: UUID | None, *, base=None, multiplier=None, custom=False) -> Preferences:
        snapshot = await self.choose_settings(user_id, token, base=base, multiplier=multiplier, custom=custom)
        return snapshot.preferences

    async def choose_settings(self, user_id: int, token: UUID | None, *, base=None, multiplier=None, custom=False) -> SettingsSnapshot:
        async with self.crystals.connection() as conn:
            balance = await self.lock_account(conn, user_id)
            row = await (await self.execute(conn, 'SELECT * FROM {preferences} WHERE user_id=%s', (user_id,))).fetchone()
            if row is None or token is None or row['token'] != token:
                raise CasinoError('此設定面板已失效，請使用 /賭場。')
            bet = Bet(int(row['base']) if base is None else base, int(row['multiplier']) if multiplier is None else multiplier)
            row = await (await self.execute(conn, '''UPDATE {preferences} SET base=%s, multiplier=%s,
                custom_base=%s, custom_multiplier=%s, token=%s WHERE user_id=%s RETURNING *''',
                (bet.base, bet.multiplier, base if custom and base is not None else row['custom_base'],
                 multiplier if custom and multiplier is not None else row['custom_multiplier'], uuid4(), user_id))).fetchone()
        return SettingsSnapshot(read_preferences(row), balance)

    async def replay(self, user_id: int, game_id: UUID) -> Game:
        return await self.start(user_id, uuid5(NAMESPACE_URL, 'casino:replay:' + str(game_id)), parent_id=game_id)

    async def start(self, user_id: int, token: UUID | None, *, game='dice', parent_id=None) -> Game:
        if game not in ('dice', 'blackjack'):
            raise CasinoError('未知遊戲。')
        try:
            async with self.crystals.connection() as conn:
                balance = await self.lock_account(conn, user_id)
                # Account lock is acquired before batching reads: every writer uses this lock.
                async with conn.pipeline():
                    existing = await self.execute(conn, 'SELECT * FROM {games} WHERE operation_id=%s AND user_id=%s', (token, user_id))
                    active = await self.execute(conn, "SELECT id FROM {games} WHERE user_id=%s AND status='active'", (user_id,))
                    origin = await self.execute(conn,
                        'SELECT * FROM {preferences} WHERE user_id=%s' if parent_id is None else
                        'SELECT * FROM {games} WHERE id=%s AND user_id=%s',
                        (user_id,) if parent_id is None else (parent_id, user_id))
                row = await existing.fetchone()
                if row is None:
                    if await active.fetchone():
                        raise CasinoError('已有進行中的牌局，請使用 /賭場 恢復。')
                    if parent_id is None:
                        pref = await origin.fetchone()
                        if pref is None or token is None or pref['token'] != token:
                            raise CasinoError('此設定面板已失效，請使用 /賭場。')
                        bet = Bet(int(pref['base']), int(pref['multiplier']))
                    else:
                        parent = await origin.fetchone()
                        if parent is None or parent['status'] == 'active' or parent['dismissed']:
                            raise CasinoError('此結算面板已失效，請使用 /賭場。')
                        bet = Bet(int(parent['base']), int(parent['multiplier']))
                        game = parent['game']
                    row = await self.create_game(conn, user_id, token, bet, balance, parent_id, game)
                game_id = row['id']
        except DatabaseError:
            # A lost COMMIT acknowledgement is neither a failure nor permission to retry a debit.
            async with self.crystals.connection(read_only=True) as conn:
                row = await (await self.execute(conn, 'SELECT id FROM {games} WHERE operation_id=%s AND user_id=%s', (token, user_id))).fetchone()
                if row is None:
                    raise
                game_id = row['id']
        return await self.settle(user_id, game_id)

    async def create_game(self, conn, user_id, operation_id, bet, balance, parent_id=None, game='dice'):
        if balance < bet.total:
            raise CasinoError('水晶餘額不足，無法開局。')
        dice, cards, deadline = [], None, None
        if game == 'dice':
            dice = list(self.roll())
            if len(dice) != 6:
                raise ValueError('Expected six dice')
            outcome(dice[:3], dice[3:])
        else:
            cards = blackjack.deal(list(self.deck()))
            deadline = self.clock() + timedelta(seconds=120)
        game_id = uuid4()
        # Ordered writes share one protocol flush but remain inside the original debit transaction.
        async with conn.pipeline():
            inserted = await self.execute(conn, """INSERT INTO {games}
                (id,user_id,game,operation_id,parent_id,base,multiplier,wager,dice,status,balance_after,cards,deadline)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s,%s) RETURNING *""",
                (game_id, user_id, game, operation_id, parent_id, bet.base, bet.multiplier, bet.total,
                 Jsonb(dice), balance - bet.total, Jsonb(cards), deadline))
            await self.transfer(conn, user_id, game_id, 'stake', -bet.total, balance)
            await self.execute(conn, 'UPDATE {preferences} SET token=NULL WHERE user_id=%s', (user_id,))
            if parent_id is not None:
                await self.execute(conn, 'UPDATE {games} SET dismissed=TRUE WHERE id=%s', (parent_id,))
        return await inserted.fetchone()

    async def transfer(self, conn, user_id, game_id, kind, amount, before):
        await self.execute(conn, """WITH updated AS (
            UPDATE {accounts} SET balance=%s WHERE user_id=%s RETURNING user_id,balance
        ) INSERT INTO {ledger}(game_id,user_id,kind,amount,balance_before,balance_after)
          SELECT %s,user_id,%s,%s,%s,balance FROM updated""",
            (before + amount, user_id, game_id, kind, amount, before))

    async def leave(self, user_id: int, *, game_id=None, token=None):
        async with self.crystals.connection() as conn:
            await self.lock_account(conn, user_id)
            await self.validate_departure(conn, user_id, game_id=game_id, token=token)
            await self.execute(conn, 'UPDATE {preferences} SET token=NULL WHERE user_id=%s', (user_id,))

    async def validate_departure(self, conn, user_id, *, game_id=None, token=None):
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
            return await self.resolve_game(conn, row, balance)

    async def resolve_game(self, conn, row, balance):
        user_id, game_id = int(row['user_id']), row['id']
        if row['status'] == 'active':
            if row['game'] == 'blackjack':
                return await self.resolve_blackjack(conn, row, balance)
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


    async def play(self, user_id: int, game_id: UUID, version: int, action: str) -> Game:
        try:
            async with self.crystals.connection() as conn:
                balance = await self.lock_account(conn, user_id)
                row = await (await self.execute(conn, 'SELECT * FROM {games} WHERE id=%s AND user_id=%s FOR UPDATE',
                                               (game_id, user_id))).fetchone()
                if row is None or row['game'] != 'blackjack':
                    raise CasinoError('找不到你的 21 點牌局。')
                if row['status'] == 'active' and (row['deadline'] is None or row['deadline'] <= self.clock()):
                    return await self.resolve_blackjack(conn, row, balance)
                if row['status'] != 'active' or row['version'] != version:
                    return read_game(row)
                if action not in ('hit', 'stand', 'double'):
                    raise CasinoError('無效的牌局操作。')
                state = row['cards']
                try:
                    blackjack.validate(state)
                except (ValueError, TypeError, KeyError):
                    return await self.resolve_blackjack(conn, row, balance)
                if action == 'double':
                    if len(state['player']) != 2 or state['actions']:
                        raise CasinoError('只能在首兩張牌時加倍。')
                    amount = int(row['base']) * int(row['multiplier'])
                    if balance < amount:
                        raise CasinoError('水晶餘額不足，無法加倍。')
                    await self.transfer(conn, user_id, game_id, 'double', -amount, balance)
                    balance -= amount
                    row['wager'] += amount
                blackjack.act(state, action)
                row = await (await self.execute(conn, '''UPDATE {games} SET cards=%s,wager=%s,
                    balance_after=%s,version=version+1,deadline=%s WHERE id=%s RETURNING *''',
                    (Jsonb(state), row['wager'], balance, self.clock() + timedelta(seconds=120), game_id))).fetchone()
                return await self.resolve_blackjack(conn, row, balance)
        except DatabaseError:
            async with self.crystals.connection(read_only=True) as conn:
                row = await (await self.execute(conn, 'SELECT * FROM {games} WHERE id=%s AND user_id=%s',
                                               (game_id, user_id))).fetchone()
                if row is None or row['version'] <= version:
                    raise
                return read_game(row)

    async def resolve_blackjack(self, conn, row, balance):
        state = row['cards']
        try:
            blackjack.validate(state)
            if row['deadline'] is None:
                raise ValueError('Missing blackjack deadline')
            if row['deadline'] <= self.clock() and not state['standing']:
                blackjack.act(state, 'stand')
            result = blackjack.result(state)
            if result is None:
                return read_game(row)
            wager = int(row['wager'])
            returned = wager * {'win': 2, 'tie': 1, 'loss': 0}[result]
            if result == 'win' and blackjack.natural(state['player']):
                returned = wager * 5 // 2
            status, kind, reason = 'settled', 'payout', None
        except (ValueError, TypeError, KeyError):
            result, returned = 'void', int(row['wager'])
            status, kind, reason = 'void', 'refund', 'invalid_persisted_blackjack'
        await self.transfer(conn, int(row['user_id']), row['id'], kind, returned, balance)
        row = await (await self.execute(conn, '''UPDATE {games} SET status=%s,outcome=%s,
            returned=%s,balance_after=%s,version=version+1,finished_at=clock_timestamp(),reason=%s,
            cards=%s,deadline=NULL WHERE id=%s RETURNING *''',
            (status, result, returned, balance + returned, reason, Jsonb(state), row['id']))).fetchone()
        return read_game(row)

    async def recover(self, user_id: int) -> Game | None:
        async with self.crystals.connection(read_only=True) as conn:
            row = await (await self.execute(conn, '''SELECT * FROM {games} WHERE user_id=%s
                AND (status='active' OR NOT dismissed) ORDER BY (status='active') DESC,created_at DESC LIMIT 1''', (user_id,))).fetchone()
        if row is None:
            return None
        return await self.settle(user_id, row['id']) if row['status'] == 'active' else read_game(row)

    async def expire_pending(self) -> list[Game]:
        # A bounded batch also recovers committed dice and malformed deadlines after restart.
        async with self.crystals.connection(read_only=True) as conn:
            rows = await (await self.execute(conn, '''SELECT id,user_id FROM {games}
                WHERE status='active' AND (deadline IS NULL OR deadline<=%s)
                ORDER BY created_at LIMIT 100''', (self.clock(),))).fetchall()
        return [await self.settle(int(row['user_id']), row['id']) for row in rows]

    async def ledger(self, user_id: int, game_id: UUID) -> list[Entry]:
        async with self.crystals.connection(read_only=True) as conn:
            rows = await (await self.execute(conn, 'SELECT * FROM {ledger} WHERE user_id=%s AND game_id=%s ORDER BY id', (user_id, game_id))).fetchall()
            return [Entry(r['kind'], int(r['amount']), int(r['balance_before']), int(r['balance_after'])) for r in rows]
