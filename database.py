"""Neon storage and explicit schema/import commands. Never log connection strings."""

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from crystal_rules import can_claim
from legacy_merge import load_exact, merge_files
from runtime import configure_event_loop

MAX_ID = 2**64 - 1


class DatabaseError(RuntimeError):
    """A safe error suitable for a terminal or user response."""


@dataclass(frozen=True)
class Account:
    user_id: int
    balance: int
    display_name: str | None = None


@dataclass(frozen=True)
class ClaimResult:
    balance: int
    reward: int | None


def read_database_url() -> str:
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise DatabaseError("DATABASE_URL is missing. Set it locally in .env.")
    return value


def connection_parameters(dsn: str) -> dict:
    try:
        params = conninfo_to_dict(dsn)
    except (psycopg.Error, ValueError):
        raise DatabaseError("DATABASE_URL is not a valid PostgreSQL connection string.") from None
    if not params.get("host") or not params.get("dbname"):
        raise DatabaseError("DATABASE_URL must specify a host and database.")
    if params.get("sslmode", "require") not in ("require", "verify-ca", "verify-full"):
        raise DatabaseError("DATABASE_URL must use sslmode=require, verify-ca or verify-full.")
    params.setdefault("sslmode", "require")
    params["connect_timeout"] = 15
    # Avoid persistent prepared statements across transaction-pooled connections.
    params["prepare_threshold"] = None
    return params


class CrystalStore:
    def __init__(self, dsn: str, *, schema: str = "public") -> None:
        self._params = connection_parameters(dsn)
        self.schema = schema
        self.table = sql.Identifier(schema, "crystal_accounts")

    @asynccontextmanager
    async def connection(self, *, read_only: bool = False):
        try:
            async with await psycopg.AsyncConnection.connect(**self._params) as conn:
                await conn.set_read_only(read_only)
                await conn.execute("SET LOCAL statement_timeout = '10s'")
                await conn.execute("SET LOCAL lock_timeout = '5s'")
                yield conn
        except psycopg.errors.UndefinedTable:
            raise DatabaseError("Crystal tables are missing. Run: python -m database init") from None
        except psycopg.errors.UniqueViolation:
            raise DatabaseError("Import conflict: an account already exists. No accounts were imported.") from None
        except psycopg.Error:
            raise DatabaseError("Database operation failed. Check the connection and retry; credentials are not logged.") from None

    async def initialize(self) -> None:
        async with self.connection() as conn:
            # Serialize simultaneous explicit initializations, including CREATE TABLE.
            await conn.execute("SELECT pg_advisory_xact_lock(431483260468592641)")
            await conn.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    user_id NUMERIC(20, 0) PRIMARY KEY
                        CHECK (user_id > 0 AND user_id <= 18446744073709551615),
                    balance NUMERIC NOT NULL CONSTRAINT crystal_balance_valid CHECK (
                        balance >= 0 AND balance < 'Infinity'::numeric AND balance = trunc(balance)
                    ),
                    last_claim_date DATE,
                    display_name TEXT CHECK (char_length(display_name) <= 128)
                )
            """).format(self.table))

    async def migrate(self) -> None:
        async with self.connection() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(431483260468592641)")
            await conn.execute(sql.SQL(
                "ALTER TABLE {} ALTER COLUMN balance TYPE NUMERIC USING balance::numeric"
            ).format(self.table))
            await conn.execute(sql.SQL(
                "ALTER TABLE {} DROP CONSTRAINT IF EXISTS crystal_balance_valid"
            ).format(self.table))
            await conn.execute(sql.SQL("""
                ALTER TABLE {} ADD CONSTRAINT crystal_balance_valid CHECK (
                    balance >= 0 AND balance < 'Infinity'::numeric AND balance = trunc(balance)
                )
            """).format(self.table))

    async def check(self) -> bool:
        async with self.connection(read_only=True) as conn:
            await conn.execute(sql.SQL(
                "SELECT user_id, balance, last_claim_date, display_name FROM {} LIMIT 0"
            ).format(self.table))
            cursor = await conn.execute("""
                SELECT data_type, numeric_precision FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'crystal_accounts' AND column_name = 'balance'
            """, (self.schema,))
            if await cursor.fetchone() != ("numeric", None):
                raise DatabaseError("Crystal balance schema is outdated. Run: python -m database migrate")
            return bool(conn.pgconn.ssl_in_use)

    async def claim(self, user_id: int, display_name: str, reward: Callable[[], int]) -> ClaimResult:
        async with self.connection() as conn:
            await conn.execute(sql.SQL("""
                INSERT INTO {} (user_id, balance, display_name)
                VALUES (%s, 10, %s) ON CONFLICT (user_id) DO NOTHING
            """).format(self.table), (user_id, display_name[:128]))
            cursor = await conn.execute(sql.SQL(
                "SELECT balance, last_claim_date FROM {} WHERE user_id = %s FOR UPDATE"
            ).format(self.table), (user_id,))
            balance, last_date = await cursor.fetchone()
            balance = int(balance)
            # Read the clock AFTER the row lock; transaction start can be yesterday.
            cursor = await conn.execute(
                "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Taipei')::date"
            )
            today = (await cursor.fetchone())[0]
            amount = reward() if can_claim(last_date, today) else None
            if amount is not None:
                if type(amount) is not int or amount < 0:
                    raise ValueError("Reward must be a non-negative integer.")
                balance += amount
                last_date = today
            await conn.execute(sql.SQL("""
                UPDATE {} SET balance = %s, last_claim_date = %s, display_name = %s
                WHERE user_id = %s
            """).format(self.table), (balance, last_date, display_name[:128], user_id))
            result = ClaimResult(balance, amount)
        # Return only after COMMIT succeeded. Never retry an uncertain commit here.
        return result

    async def leaderboard(self) -> list[Account]:
        async with self.connection(read_only=True) as conn:
            cursor = await conn.execute(sql.SQL("""
                SELECT user_id, balance, display_name FROM {}
                ORDER BY balance DESC, user_id ASC LIMIT 5
            """).format(self.table))
            return [Account(int(uid), int(balance), name) for uid, balance, name in await cursor.fetchall()]

    async def import_accounts(self, accounts: list[Account], *, dry_run: bool) -> int:
        if any(type(a.balance) is not int or a.balance < 0 for a in accounts):
            raise DatabaseError("Balances must be non-negative integers.")
        async with self.connection(read_only=dry_run) as conn:
            if dry_run:
                cursor = await conn.execute(sql.SQL(
                    "SELECT user_id FROM {} WHERE user_id = ANY(%s::numeric[]) ORDER BY user_id LIMIT 20"
                ).format(self.table), ([a.user_id for a in accounts],))
                conflicts = await cursor.fetchall()
                if conflicts:
                    ids = ", ".join(str(int(row[0])) for row in conflicts)
                    raise DatabaseError(f"Import conflict (first 20 IDs): {ids}. Nothing was changed.")
            else:
                async with conn.cursor() as cursor:
                    await cursor.executemany(sql.SQL("""
                        INSERT INTO {} (user_id, balance, display_name)
                        VALUES (%s, %s, %s)
                    """).format(self.table), [(a.user_id, a.balance, a.display_name) for a in accounts])
        return len(accounts)


def parse_import(path: Path) -> list[Account]:
    try:
        data, _ = load_exact(path)
    except ValueError:
        raise DatabaseError("Cannot read import file: provide a UTF-8 JSON array.") from None
    if not isinstance(data, list) or not data:
        raise DatabaseError("Import must be a non-empty JSON array.")
    result = []
    seen = set()
    for row_number, row in enumerate(data, 1):
        if not isinstance(row, dict) or set(row) - {"user_id", "balance", "display_name"}:
            raise DatabaseError(f"Invalid columns at import row {row_number}.")
        uid = row.get("user_id")
        if type(uid) is not str or not uid.isascii() or not uid.isdecimal() or not 0 < int(uid) <= MAX_ID:
            raise DatabaseError(f"Invalid user_id at import row {row_number}; use a decimal string.")
        user_id = int(uid)
        if user_id in seen:
            raise DatabaseError(f"Duplicate user_id at import row {row_number}.")
        balance = row.get("balance")
        if type(balance) is str and balance.isascii() and balance.isdecimal():
            balance = int(balance)
        if type(balance) is not int or balance < 0:
            raise DatabaseError(f"Invalid non-negative integer balance at import row {row_number}.")
        name = row.get("display_name")
        if name is not None and (not isinstance(name, str) or len(name) > 128 or "\x00" in name):
            raise DatabaseError(f"Invalid display_name at import row {row_number}.")
        seen.add(user_id)
        result.append(Account(user_id, balance, name))
    return result


async def run_cli(args: argparse.Namespace) -> None:
    if args.command == "merge-legacy":
        report = merge_files(args.crystals, args.bank, args.output)
        print(json.dumps(report, ensure_ascii=True))
        return
    accounts = parse_import(args.file) if args.command == "import" else None
    store = CrystalStore(read_database_url())
    if args.command == "init":
        await store.initialize()
        print("Crystal schema initialized. Existing accounts were preserved.")
    elif args.command == "migrate":
        await store.migrate()
        print("Crystal balance schema migrated to exact non-negative NUMERIC.")
    elif args.command == "check":
        encrypted = await store.check()
        print(f"Database and crystal schema OK; SSL: {encrypted}. Read-only check.")
    else:
        count = await store.import_accounts(accounts, dry_run=not args.apply)
        print(f"{'Imported' if args.apply else 'Dry-run OK:'} {count} account(s).")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Crystal database administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Explicitly initialize the crystal schema")
    commands.add_parser("migrate", help="Migrate existing balance storage to exact NUMERIC")
    commands.add_parser("check", help="Read-only connection and schema check")
    merger = commands.add_parser("merge-legacy", help="Offline merge of crystal and bank JSON snapshots")
    merger.add_argument("--crystals", type=Path, required=True)
    merger.add_argument("--bank", type=Path, required=True)
    merger.add_argument("--output", type=Path, required=True)
    importer = commands.add_parser("import", help="Validate an import without writing by default")
    importer.add_argument("file", type=Path)
    mode = importer.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate without writing (default)")
    mode.add_argument("--apply", action="store_true", help="Import the entire batch atomically")
    args = parser.parse_args()
    configure_event_loop()
    try:
        asyncio.run(run_cli(args))
    except (DatabaseError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    except KeyboardInterrupt:
        raise SystemExit("Cancelled.") from None


if __name__ == "__main__":
    cli()
