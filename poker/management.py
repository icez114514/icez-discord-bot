"""Allowlisted administration within the same writer as table settlements."""

import json
import sqlite3
import time

from . import money, tables
from .sessions import authenticate
from .statistics import persist
from .store import Conflict, Unauthorized, account_view


def roles(config, actor):
    return {
        "tables": actor in config.table_admins,
        "funds": actor in config.funds_admins,
    }


def require_role(config, actor, role):
    if not roles(config, actor)[role]:
        raise Unauthorized("management_role_required")


def table_status(table):
    return {
        "table_id": table["id"],
        "name": table.get("name", "50 / 100"),
        "status": "frozen"
        if table["frozen"]
        else "closing"
        if table["closed"] and table["hand"]
        else "closed"
        if table["closed"]
        else "open",
        "hand_id": table["hand"]["id"] if table["hand"] else None,
        "members": [
            {"user_id": m["id"], "leaving": m.get("leaving", False)}
            for m in table["members"]
        ],
    }


def audit(db, cid, actor, action, target, reason, now, before, after):
    db.execute(
        "INSERT INTO management_audit(command_id,actor,action,target,reason,created_at,before_state,after_state) VALUES(?,?,?,?,?,?,?,?)",
        (
            cid,
            actor,
            action,
            target,
            reason,
            now,
            json.dumps(before),
            json.dumps(after),
        ),
    )


def rebuild(db, hand_id):
    row = db.execute("SELECT * FROM hands WHERE hand_id=?", (hand_id,)).fetchone()
    if not row or row["status"] == "active":
        raise Conflict("completed_hand_required")
    # Rebuild from the settlement event, not editable client-supplied counters.
    event = db.execute(
        "SELECT e.event FROM hand_events e JOIN settlements s ON s.command_id=e.command_id WHERE s.hand_id=?",
        (hand_id,),
    ).fetchone()
    if not event:
        raise Conflict("settlement_evidence_required")
    evidence = json.loads(event[0])
    snapshot = evidence["data"].get("snapshot", {})
    before = [
        dict(r)
        for r in db.execute("SELECT * FROM hand_statistics WHERE hand_id=?", (hand_id,))
    ]
    db.execute("DELETE FROM hand_statistics WHERE hand_id=?", (hand_id,))
    if evidence["kind"] == "settle":
        if not snapshot.get("players") or "settled_at" not in snapshot:
            raise Conflict("complete_settlement_snapshot_required")
        persist(db, hand_id, snapshot, snapshot["settled_at"])
    # Replay the authoritative award/debit timeline, respecting the 60-second cap.
    affected = [
        r[0]
        for r in db.execute(
            "SELECT user_id FROM participants WHERE hand_id=? AND user_id NOT LIKE 'npc:%'",
            (hand_id,),
        )
    ]
    progress = {}
    for user in affected:
        bank, hands = 60, 0
        for record in db.execute(
            "SELECT e.event FROM hand_events e JOIN participants p ON p.hand_id=e.hand_id WHERE p.user_id=? ORDER BY e.id",
            (user,),
        ):
            saved = json.loads(record[0])
            if saved["kind"] == "time_bank" and saved["data"].get("user_id") == user:
                bank -= 5
            elif saved["kind"] == "settle":
                hands += 1
                if hands % 10 == 0:
                    bank = min(60, bank + 5)
        if not 0 <= bank <= 60:
            raise Conflict("time_bank_evidence_inconsistent")
        progress[user] = {
            "before": dict(
                db.execute(
                    "SELECT time_bank,hand_progress FROM accounts WHERE user_id=?",
                    (user,),
                ).fetchone()
            ),
            "after": {"time_bank": bank, "hand_progress": hands % 10},
        }
        db.execute(
            "UPDATE accounts SET time_bank=?,hand_progress=? WHERE user_id=?",
            (bank, hands % 10, user),
        )
    after = [
        dict(r)
        for r in db.execute("SELECT * FROM hand_statistics WHERE hand_id=?", (hand_id,))
    ]
    return {"statistics": before}, {"statistics": after, "progress": progress}


class Management:
    def __init__(self, store, config):
        self.store, self.config = store, config

    async def view(self, token):
        def operation(db):
            actor = authenticate(db, token)
            allowed = roles(self.config, actor)
            if not any(allowed.values()):
                raise Unauthorized("management_role_required")
            return {
                "roles": allowed,
                "tables": [table_status(t) for t in tables.all_tables(db)]
                if allowed["tables"]
                else [],
                "accounts": [
                    {
                        "user_id": r["user_id"],
                        "disabled": bool(r["disabled"]),
                        "available": str(r["available"]),
                        "settled": str(r["settled"]),
                    }
                    for r in db.execute(
                        "SELECT user_id,disabled,available,settled FROM accounts WHERE user_id NOT LIKE 'npc:%' ORDER BY user_id"
                    )
                ],
            }

        return await self.store.run(operation)

    async def history(self, token, user=None, after=0):
        def operation(db):
            actor = authenticate(db, token)
            if not any(roles(self.config, actor).values()):
                raise Unauthorized("management_role_required")
            # Never expose rebuild's private metric evidence through management.
            audit_rows = []
            for row in db.execute(
                "SELECT * FROM management_audit WHERE id>? AND (? IS NULL OR target=?) ORDER BY id LIMIT 100",
                (after, user, user),
            ):
                record = dict(row)
                for key in ("before_state", "after_state"):
                    record[key] = (
                        json.loads(record[key])
                        if record["action"] != "rebuild"
                        else {"redacted": True}
                    )
                audit_rows.append(record)
            return {
                "audit": audit_rows,
                "next": audit_rows[-1]["id"] if audit_rows else after,
            }

        return await self.store.run(operation)

    async def ledger(self, token, user, after=0):
        def operation(db):
            actor = authenticate(db, token)
            require_role(self.config, actor, "funds")
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM ledger WHERE user_id=? AND id>? ORDER BY id LIMIT 100",
                    (user, after),
                )
            ]
            for row in rows:
                for key in (
                    "available_delta",
                    "table_delta",
                    "flight_delta",
                    "settled_delta",
                ):
                    row[key] = str(row[key])
            return {"entries": rows, "next": rows[-1]["id"] if rows else after}

        return await self.store.run(operation)

    async def command(self, data, token=None, trusted_actor=None, now=None):
        now = time.time() if now is None else now

        def operation(db):
            actor = authenticate(db, token) if token is not None else trusted_actor
            disabled = db.execute(
                "SELECT disabled FROM accounts WHERE user_id=?", (actor,)
            ).fetchone()
            if disabled and disabled[0]:
                raise Unauthorized("account_disabled")
            action, target, reason = data["action"], data["target"], data["reason"]
            if action not in ("adjust", "disable", "close", "remove", "rebuild"):
                raise Conflict("unknown_management_action")
            require_role(
                self.config, actor, "funds" if action == "adjust" else "tables"
            )
            if not reason.strip():
                raise Conflict("audit_reason_required")
            cid = "manage:" + actor + ":" + data["command_id"]
            fingerprint = json.dumps(data, sort_keys=True)
            old = db.execute(
                "SELECT * FROM management_commands WHERE command_id=?", (cid,)
            ).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise Conflict("command_id_reused")
                return json.loads(old["result"])
            db.execute("SAVEPOINT management")
            try:
                before, after = self.apply(
                    db, cid, actor, action, target, reason, data, now
                )
                audit(db, cid, actor, action, target, reason, now, before, after)
                result = {
                    "value": {
                        "command_id": data["command_id"],
                        "action": action,
                        "target": target,
                        "result": after
                        if action != "rebuild"
                        else {"status": "rebuilt"},
                    }
                }
                db.execute("RELEASE management")
            except (Conflict, sqlite3.IntegrityError) as error:
                db.execute("ROLLBACK TO management")
                db.execute("RELEASE management")
                result = {
                    "error": str(error)
                    if isinstance(error, Conflict)
                    else "funds_or_state_conflict"
                }
            db.execute(
                "INSERT INTO management_commands VALUES(?,?,?)",
                (cid, fingerprint, json.dumps(result)),
            )
            return result

        result = await self.store.run(operation)
        if "error" in result:
            raise Conflict(result["error"])
        return result["value"]

    def apply(self, db, cid, actor, action, target, reason, data, now):
        if action == "adjust":
            if target.startswith("npc:"):
                raise Conflict("human_account_required")
            before = account_view(db, target)
            after = money.execute(
                db,
                cid,
                "adjust",
                {
                    "user_id": target,
                    "amount": data.get("amount"),
                    "actor": actor,
                    "reason": reason,
                },
                now,
            )
            return before, after
        if action == "rebuild":
            return rebuild(db, target)
        if action == "close":
            table = tables.load(db, target)
            before = table_status(table)
            table["closed"], table["countdown"] = True, None
        else:
            account = db.execute(
                "SELECT disabled FROM accounts WHERE user_id=? AND user_id NOT LIKE 'npc:%'",
                (target,),
            ).fetchone()
            if account is None:
                raise Conflict("human_account_required")
            before = {"disabled": bool(account[0])}
            if action == "disable":
                db.execute("UPDATE accounts SET disabled=1 WHERE user_id=?", (target,))
                db.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (target,))
            table = tables.current_table(db, target)
            if table:
                tables.member(table, target)["leaving"] = True
        if table:
            # Never mutate the current hand. Existing timers finish it normally.
            tables.Transaction(db, table, cid, now).between()
            table["version"] += 1
            tables.save(db, table)
        after = (
            table_status(table)
            if action == "close"
            else {
                "disabled": action == "disable" or before["disabled"],
                "status": "pending_settlement"
                if table and table["hand"]
                else "complete",
            }
        )
        return before, after
