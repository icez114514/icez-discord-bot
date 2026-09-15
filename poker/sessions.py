"""Durable local sessions and authenticated interface presence."""

from abc import ABC, abstractmethod
import secrets
import time
from .money import subsidy_status


def authenticate(db, token):
    from .store import Unauthorized, digest

    row = db.execute(
        "SELECT user_id FROM sessions WHERE token_hash=? AND revoked=0",
        (digest(token),),
    ).fetchone()
    if row is None:
        raise Unauthorized("login_required")
    return row["user_id"]


def present(db, user, now):
    return bool(
        db.execute(
            "SELECT 1 FROM presence p JOIN sessions s ON s.token_hash=p.session_hash WHERE s.user_id=? AND s.revoked=0 AND p.until_at>?",
            (user, now),
        ).fetchone()
    )


class Sessions(ABC):
    @abstractmethod
    async def run(self, operation, transaction=True):
        raise NotImplementedError

    async def authenticate(self, token):
        return await self.run(lambda db: authenticate(db, token))

    async def account_for_session(self, token, now=None):
        from .store import account_view

        def operation(db):
            user = authenticate(db, token)
            return {
                **account_view(db, user),
                "subsidy": subsidy_status(
                    db, user, time.time() if now is None else now
                ),
            }

        return await self.run(operation)

    async def logout(self, token):
        def operation(db):
            user = authenticate(db, token)
            db.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user,))

        await self.run(operation)

    async def presence(self, token, connection_id, action, now=None):
        from .store import Conflict, digest

        now = time.time() if now is None else now

        def operation(db):
            user = authenticate(db, token)
            existing = db.execute(
                "SELECT * FROM presence WHERE connection_id=?", (connection_id,)
            ).fetchone()
            if existing and existing["session_hash"] != digest(token):
                raise Conflict("connection_owner_mismatch")
            if action == "enter":
                db.execute(
                    "INSERT INTO presence(connection_id,session_hash,until_at) VALUES(?,?,?) ON CONFLICT(connection_id) DO UPDATE SET until_at=excluded.until_at",
                    (connection_id, digest(token), now + 150),
                )
                db.execute(
                    "UPDATE accounts SET presence_revision=presence_revision+1 WHERE user_id=?",
                    (user,),
                )
            elif action in ("heartbeat", "disconnect", "leave"):
                if not existing:
                    raise Conflict("connection_not_open")
                until = (
                    0
                    if action == "leave"
                    else now + (120 if action == "disconnect" else 150)
                )
                if action == "disconnect":
                    until = min(until, existing["until_at"])
                if action == "heartbeat" and existing["until_at"] <= now:
                    db.execute(
                        "UPDATE accounts SET presence_revision=presence_revision+1 WHERE user_id=?",
                        (user,),
                    )
                db.execute(
                    "UPDATE presence SET until_at=? WHERE connection_id=?",
                    (until, connection_id),
                )
            else:
                raise Conflict("unknown_presence_action")

        await self.run(operation)

    async def oauth_begin(self, now=None):
        from .store import digest

        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time() if now is None else now

        def operation(db):
            db.execute("DELETE FROM oauth_states WHERE expires_at<=?", (now,))
            db.execute(
                "INSERT INTO oauth_states VALUES(?,?,?)",
                (digest(state), digest(browser), now + 600),
            )

        await self.run(operation)
        return state, browser

    async def oauth_consume(self, state, browser, now=None):
        from .store import Unauthorized, digest

        now = time.time() if now is None else now

        def operation(db):
            row = db.execute(
                "SELECT * FROM oauth_states WHERE state_hash=? AND browser_hash=? AND expires_at>?",
                (digest(state), digest(browser), now),
            ).fetchone()
            if not row:
                raise Unauthorized("invalid_oauth_state")
            db.execute("DELETE FROM oauth_states WHERE state_hash=?", (digest(state),))

        await self.run(operation)
