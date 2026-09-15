"""Single writer, short SQLite transactions off the ASGI event loop."""
import asyncio
import hashlib
import json
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Conflict(ValueError):
    pass


class Unauthorized(ValueError):
    pass


from .sessions import Sessions, authenticate


class Store(Sessions):
    def __init__(self, path: Path, initialize: bool = False):
        self.path = path
        self.initialize = initialize
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='poker-writer')

    async def __aenter__(self):
        from .locking import ProcessLock
        self.process_lock = ProcessLock(self.path.with_suffix('.lock'))
        self.process_lock.acquire()
        try:
            await self.run(self._open, transaction=False)
        except BaseException:
            if hasattr(self, 'db'):
                await self.run(lambda db: db.close(), transaction=False)
            self.executor.shutdown(wait=True)
            self.process_lock.release()
            raise
        return self

    async def __aexit__(self, *args):
        await self.run(lambda db: db.close(), transaction=False)
        self.executor.shutdown(wait=True)

        self.process_lock.release()

    def _open(self, _):
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA foreign_keys=ON')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version == 0 and self.initialize:
            self.db.executescript((Path(__file__).with_name('schema.sql')).read_text(encoding='utf-8'))
        elif version != 1:
            raise Conflict('database_schema_requires_migrate')

    async def run(self, operation, transaction=True):
        def execute():
            db = getattr(self, 'db', None)
            if db is None or not transaction:
                return operation(db)
            db.execute('BEGIN IMMEDIATE')
            try:
                result = operation(db)
                db.execute('COMMIT')
                return result
            except BaseException:
                db.execute('ROLLBACK')
                raise
        return await asyncio.get_running_loop().run_in_executor(self.executor, execute)

    async def login(self, user_id: str):
        token = secrets.token_urlsafe(32)
        def operation(db):
            created = db.execute('INSERT OR IGNORE INTO accounts(user_id,available,settled) VALUES(?,50000,50000)', (user_id,)).rowcount
            if created:
                db.execute('INSERT INTO ledger(command_id,user_id,source,reason,available_delta,settled_delta) VALUES(?,?,?,?,50000,50000)', ('gift:' + user_id, user_id, 'initial_gift', 'First poker account'))
            db.execute('INSERT INTO sessions(token_hash,user_id,created_at) VALUES(?,?,?)', (digest(token), user_id, time.time()))
            db.execute('UPDATE accounts SET login_revision=login_revision+1 WHERE user_id=?', (user_id,))
            return token
        return await self.run(operation)

    async def command(self, command_id: str, kind: str, *, now=None, session=None, **data):
        from .money import execute
        if not isinstance(command_id, str) or not 1 <= len(command_id) <= 128:
            raise Conflict('invalid_command_id')
        fingerprint = json.dumps({'kind': kind, 'data': data}, sort_keys=True, separators=(',', ':'))
        def operation(db):
            if session is not None:
                session_user = authenticate(db, session)
                if session_user != data.get('user_id') or kind != 'subsidy':
                    raise Unauthorized('command_not_allowed')
            old = db.execute('SELECT * FROM commands WHERE command_id=?', (command_id,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise Conflict('command_id_reused')
                return json.loads(old['result'])
            db.execute('SAVEPOINT money_command')
            try:
                result = {'value': execute(db, command_id, kind, data, time.time() if now is None else now)}
                db.execute('RELEASE money_command')
            except (Conflict, sqlite3.IntegrityError) as error:
                db.execute('ROLLBACK TO money_command')
                db.execute('RELEASE money_command')
                result = {'error': str(error) if isinstance(error, Conflict) else 'funds_or_state_conflict'}
            db.execute('INSERT INTO commands VALUES(?,?,?)', (command_id, fingerprint, json.dumps(result)))
            return result
        outcome = await self.run(operation)
        if 'error' in outcome:
            raise Conflict(outcome['error'])
        return outcome['value']

    async def subsidy(self, user_id, now=None):
        from .money import subsidy_status
        return await self.run(lambda db: subsidy_status(db, user_id, time.time() if now is None else now))

    async def hand(self, hand_id):
        def operation(db):
            row = db.execute('SELECT * FROM hands WHERE hand_id=?', (hand_id,)).fetchone()
            return dict(row) if row else None
        return await self.run(operation)

    async def account(self, user_id: str):
        return await self.run(lambda db: account_view(db, user_id))

    async def ledger(self, user_id: str):
        return await self.run(lambda db: [dict(row) for row in db.execute('SELECT * FROM ledger WHERE user_id=? ORDER BY id', (user_id,))])


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def account_view(db, user_id):
    row = db.execute('SELECT * FROM accounts WHERE user_id=?', (user_id,)).fetchone()
    if row is None:
        raise Unauthorized('account_not_found')
    return {'user_id': user_id, 'available': str(row['available']), 'table': str(row['table_chips']), 'in_flight': str(row['in_flight']), 'settled': str(row['settled']), 'time_bank': row['time_bank'], 'hand_progress': row['hand_progress']}
