"""Read-only casino projections. Caller supplies the authorized player scope.

None is the trusted staff scope for history and the public scope for summaries.
No card, dice, deck, or operation-token data crosses this boundary.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from psycopg import IsolationLevel

from casino_store import CasinoStore, Entry


T = TypeVar('T')


@dataclass(frozen=True)
class Page(Generic[T]):
    rows: tuple[T, ...]
    has_next: bool


@dataclass(frozen=True)
class Summary:
    game: str
    status: str
    count: int
    wins: int
    losses: int
    ties: int
    wager: int
    returned: int

    @property
    def net(self) -> int:
        return self.returned - self.wager


@dataclass(frozen=True)
class Record:
    id: UUID
    user_id: int
    game: str
    status: str
    outcome: str | None
    original_wager: int
    wager: int
    returned: int
    created_at: datetime
    finished_at: datetime | None
    reason: str | None
    entries: tuple[Entry, ...]

    @property
    def net(self) -> int:
        return self.returned - self.wager


def filters(user_id, game, game_id=None):
    clauses, params = [], []
    for column, value in (('g.user_id', user_id), ('g.game', game), ('g.id', game_id)):
        if value is not None:
            clauses.append(column + '=%s')
            params.append(value)
    return (' AND '.join(clauses) or 'TRUE'), params


class CasinoRecords:
    def __init__(self, store: CasinoStore):
        self.store = store

    async def summary(self, *, user_id: int | None = None, game: str | None = None,
                      page: int = 0) -> Page[Summary]:
        if page < 0:
            raise ValueError('Negative page')
        where, params = filters(user_id, game)
        async with self.store.crystals.connection(read_only=True) as conn:
            rows = await (await self.store.execute(conn, '''
                WITH amounts AS (
                    SELECT game_id,
                        -sum(amount) FILTER (WHERE kind IN ('stake','double')) AS wager,
                        coalesce(sum(amount) FILTER (WHERE kind IN ('payout','refund')),0) AS returned
                    FROM {ledger} GROUP BY game_id
                )
                SELECT g.game,g.status,count(*) AS count,
                    count(*) FILTER (WHERE g.status='settled' AND g.outcome='win') AS wins,
                    count(*) FILTER (WHERE g.status='settled' AND g.outcome='loss') AS losses,
                    count(*) FILTER (WHERE g.status='settled' AND g.outcome='tie') AS ties,
                    sum(a.wager) AS wager,sum(a.returned) AS returned
                FROM {games} g JOIN amounts a ON a.game_id=g.id WHERE ''' + where + '''
                GROUP BY g.game,g.status ORDER BY g.game,g.status LIMIT 4 OFFSET %s
                ''', (*params, page * 3))).fetchall()
        return Page(tuple(Summary(r['game'], r['status'], *(int(r[k]) for k in
                    ('count', 'wins', 'losses', 'ties', 'wager', 'returned'))) for r in rows[:3]), len(rows) > 3)

    async def history(self, *, user_id: int | None, game: str | None = None,
                      game_id: UUID | None = None, page: int = 0) -> Page[Record]:
        if page < 0:
            raise ValueError('Negative page')
        where, params = filters(user_id, game, game_id)
        async with self.store.crystals.connection(
                read_only=True, isolation_level=IsolationLevel.REPEATABLE_READ) as conn:
            # A settlement between the two reads must not mix active state with a payout.
            rows = await (await self.store.execute(conn, '''
                SELECT g.id,g.user_id,g.game,g.status,g.outcome,g.base*g.multiplier AS original_wager,
                    g.created_at,g.finished_at,g.reason
                FROM {games} g WHERE ''' + where + '''
                ORDER BY g.created_at DESC,g.id DESC LIMIT 2 OFFSET %s
                ''', (*params, page))).fetchall()
            records = []
            for row in rows[:1]:
                ledger = await (await self.store.execute(conn, '''SELECT kind,amount,balance_before,balance_after
                    FROM {ledger} WHERE game_id=%s ORDER BY id''', (row['id'],))).fetchall()
                entries = tuple(Entry(e['kind'], int(e['amount']), int(e['balance_before']), int(e['balance_after']))
                                for e in ledger)
                records.append(Record(row['id'], int(row['user_id']), row['game'], row['status'], row['outcome'],
                    int(row['original_wager']), -sum(e.amount for e in entries if e.kind in ('stake', 'double')),
                    sum(e.amount for e in entries if e.kind in ('payout', 'refund')),
                    row['created_at'], row['finished_at'], row['reason'], entries))
        return Page(tuple(records), len(rows) > 1)
