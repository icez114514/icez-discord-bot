"""Durable table authority sharing the account writer and money transaction."""

import copy
import json
import math
import secrets
import sqlite3
import time

from . import money, rules
from .presentation import emit, publish_hand, next_hand_delay
from .sessions import authenticate
from .store import Conflict
from .voices import VOICE_PACKS, voice_for


def initial(table_id="main"):
    return {
        "id": table_id,
        "game_mode": "standard",
        "version": 0,
        "owner": None,
        "members": [],
        "hand": None,
        "last": None,
        "countdown": None,
        "button_seat": -1,
        "closed": False,
        "frozen": False,
        "sequence": 0,
    }


def load(db, table_id="main"):
    row = db.execute(
        "SELECT state FROM game_tables WHERE table_id=?", (table_id,)
    ).fetchone()
    if row:
        return json.loads(row[0])
    if table_id == "main":
        return initial()
    raise Conflict("table_unavailable")


def all_tables(db):
    return [json.loads(row[0]) for row in db.execute("SELECT state FROM game_tables")]


def current_table(db, user):
    return next((t for t in all_tables(db) if member(t, user)), None)


def accessible(table, user, invitation=None, spectator=False):
    if spectator and user in table.get("watchers", []):
        return
    if table.get("private") and not member(table, user):
        if not invitation or not secrets.compare_digest(
            table.get("invitation", "").encode(), invitation.encode()
        ):
            raise Conflict("table_unavailable")


def save(db, table):
    if table["closed"]:
        table.pop("chat", None)
        table.pop("chat_rates", None)
    db.execute(
        "INSERT INTO game_tables VALUES(?,?) ON CONFLICT(table_id) DO UPDATE SET state=excluded.state",
        (table["id"], json.dumps(table)),
    )


def member(table, user):
    return next((m for m in table["members"] if m["id"] == user), None)


def stack(db, user):
    row = db.execute(
        "SELECT table_chips FROM accounts WHERE user_id=?", (user,)
    ).fetchone()
    return row[0] if row else 0


def public(db, table, user, connection=None):
    me = member(table, user)
    if table["closed"] and not me and user in table.get("watchers", []):
        return {"id": table["id"], "version": table["version"], "joined": False, "role": "spectator", "closed": True, "control": False, "departure": table.get("departures", {}).get(user)}
    if table.get("private") and not me and user not in table.get("watchers", []):
        return {"id": table["id"], "version": table["version"], "joined": False, "closed": table["closed"]}
    return {
        "id": table["id"],
        "version": table["version"],
        "joined": me is not None,
        "role": "player" if me else "spectator",
        "departure": table.get("departures", {}).get(user),
        "rules": {"small_blind": str(rules.SMALL_BLIND), "big_blind": str(rules.BIG_BLIND)},
        "event_seq": table.get("event_seq", 0),
        "server_time": time.time(),
        "events": table.get("events", []),
        "name": table.get("name", "50 / 100"),
        "game_mode": table.get("game_mode", "standard"),
        "private": table.get("private", False),
        "owner": table["owner"],
        "countdown": table["countdown"],
        "closed": table["closed"],
        "frozen": table["frozen"],
        "control": bool(me and connection and me.get("control") == connection),
        "members": [
            {
                "id": m["id"],
                "seat": m["seat"],
                "mode": m["mode"],
                "stack": str(stack(db, m["id"])),
                "leaving": m.get("leaving", False),
                "sitout": m.get("sitout", False),
                "autoplay": m.get("autoplay", False),
                "topup": m.get("topup"),
                "notice": m.get("notice"),
                "expires": m.get("expires"),
                "npc_failures": m.get("failures", 0),
                "voice_pack": voice_for(db, m),
                "connected": bool(m.get("control")),
            }
            for m in table["members"]
        ],
        "hand": rules.project(table["hand"] or table["last"], user if me else "spectator"),
        "time_bank": db.execute(
            "SELECT time_bank FROM accounts WHERE user_id=?", (user,)
        ).fetchone()[0],
    }


class Transaction:
    def __init__(self, db, table, cid, now, maintenance=False):
        self.db, self.table, self.cid, self.now = db, table, cid, now
        self.index = 0
        self.maintenance = maintenance

    def funds(self, kind, **data):
        self.index += 1
        return money.execute(self.db, f"{self.cid}:{self.index}", kind, data, self.now)

    def hand_funds(self, kind, **data):
        return self.funds(kind, hand_id=self.table["hand"]["id"], **data)

    def clock(self):
        hand = self.table["hand"]
        if hand["actor"] is None:
            return
        user = hand["players"][hand["actor"]]["id"]
        hand["autoplay_at"] = self.now + 1
        hand["extensions"] = 0
        hand["deadline"] = self.now + (5 if user.startswith("npc:") else 20)
        if user.startswith("npc:"):
            from .npc_timing import think_seconds
            hand["npc_not_before"] = self.now + think_seconds(hand)
        else:
            hand.pop("npc_not_before", None)
        emit(
            self.table,
            self.now,
            "turn",
            hand_id=hand["id"],
            user=user,
            turn=hand["turn"],
        )
        if not user.startswith("npc:"):
            self.hand_funds("action", user_id=user, opportunity_id=str(hand["turn"]))
        else:
            self.db.execute(
                "UPDATE action_clocks SET active=0 WHERE hand_id=?", (hand["id"],)
            )

    def persist_hand(self):
        hand = self.table["hand"]
        version = self.db.execute(
            "SELECT version FROM hands WHERE hand_id=?", (hand["id"],)
        ).fetchone()[0]
        self.hand_funds("event", expected_version=version, snapshot=hand)

    def finish_action(self, before):
        hand = self.table["hand"]
        publish_hand(self.table, self.now, self.db)
        for p in hand["players"]:
            chips = p["paid"] - before.get(p["id"], 0)
            if chips:
                self.hand_funds("bet", user_id=p["id"], amount=str(chips))
        if hand["payouts"] is None:
            self.clock()
            self.persist_hand()
            return
        hand["settled_at"] = self.now
        hand["classification"] = (
            "mixed"
            if any(p["id"].startswith("npc:") for p in hand["players"])
            else "human"
        )
        opportunities = {}
        for i, p in enumerate(hand["players"]):
            actions = [a for a in hand["history"] if a["seat"] == i]
            opportunities[p["id"]] = {
                "dealt": True,
                "classification": hand["classification"],
                "settled_at": self.now,
                "actions": actions,
                "showdown": hand["showdown"] and not p["folded"],
                "payout": hand["payouts"][p["id"]],
                "refund": hand["refunds"].get(p["id"], 0),
            }
        self.hand_funds(
            "settle",
            payouts={u: str(v) for u, v in hand["payouts"].items()},
            snapshot=hand,
            opportunities=opportunities,
        )
        self.table["departures"] = {}
        for departing in self.table["members"]:
            if departing.get("leaving") and not departing["id"].startswith("npc:"):
                terminal = public(self.db, self.table, departing["id"])
                terminal.pop("departure", None)
                self.table["departures"][departing["id"]] = terminal
        self.table["last"], self.table["hand"] = hand, None
        self.between()

    def between(self):
        table = self.table
        if table["hand"]:
            return
        for m in list(table["members"]):
            user = m["id"]
            npc = user.startswith("npc:")
            if m.get("leaving") or table["closed"]:
                m["autoplay"] = False
                if not npc and user not in table.setdefault("watchers", []):
                    table["watchers"].append(user)
                chips = stack(self.db, user)
                if npc:
                    if chips:
                        self.funds(
                            "npc_reclaim",
                            user_id=user,
                            amount=str(chips),
                            actor="system",
                            reason="NPC leaves table",
                        )
                else:
                    self.funds("leave", user_id=user)
                table["members"].remove(m)
                continue
            if m.get("topup"):
                self.db.execute("SAVEPOINT queued_topup")
                try:
                    self.funds(
                        "buy_in", user_id=user, table_id=table["id"], amount=m["topup"]
                    )
                    m["notice"] = "topup_complete"
                    emit(table, self.now, "topup", user=user, amount=m["topup"])
                    m["mode"], m["expires"] = "active", None
                except (Conflict, sqlite3.IntegrityError):
                    self.db.execute("ROLLBACK TO queued_topup")
                    m["notice"] = "topup_rejected"
                finally:
                    self.db.execute("RELEASE queued_topup")
                m["topup"] = None
            if npc and stack(self.db, user) == 0:
                self.funds(
                    "npc_supply",
                    user_id=user,
                    amount="10000",
                    actor="system",
                    reason="Bankrupt fixed NPC refill",
                )
            if m["mode"] == "pending":
                m["mode"] = "active"
            if (
                m.get("sitout")
                or (not npc and stack(self.db, user) == 0)
                or (npc and m.get("failures", 0) >= 3)
            ):
                m["autoplay"] = False
                m["mode"], m["sitout"] = "sitout", False
                if not npc and m.get("expires") is None:
                    m["expires"] = self.now + 120
        humans = [m for m in table["members"] if not m["id"].startswith("npc:")]
        if not any(m["id"] == table["owner"] for m in humans):
            table["owner"] = humans[0]["id"] if humans else None
        if not humans:
            for npc in table["members"]:
                chips = stack(self.db, npc["id"])
                if chips:
                    self.funds(
                        "npc_reclaim",
                        user_id=npc["id"],
                        amount=str(chips),
                        actor="system",
                        reason="Last human left table",
                    )
            table["members"] = []
            table["countdown"] = None
            if table["id"] != "main":
                table["closed"] = True

    def available(self):
        return [
            m
            for m in self.table["members"]
            if m["mode"] == "active"
            and not m.get("leaving")
            and not m.get("sitout")
            and stack(self.db, m["id"]) > 0
            and (
                m["id"].startswith("npc:")
                or self.db.execute(
                    "SELECT 1 FROM sessions WHERE user_id=? AND revoked=0", (m["id"],)
                ).fetchone()
            )
        ]

    def tick(self):
        table = self.table
        if table["frozen"]:
            return
        for m in table["members"]:
            if m["id"].startswith("npc:"):
                continue
            if m.get("control") and m.get("heartbeat", 0) + 30 <= self.now:
                m["control"] = None
                m["disconnected"] = m["heartbeat"] + 150
            if (m.get("expires") is not None and m["expires"] <= self.now) or (
                not m.get("autoplay") and m.get("disconnected") is not None and m["disconnected"] <= self.now
            ):
                m["leaving"] = True
            if not self.db.execute(
                "SELECT 1 FROM sessions WHERE user_id=? AND revoked=0", (m["id"],)
            ).fetchone():
                m["leaving"] = True
            if m.get("leaving"):
                m["autoplay"] = False
        hand = table["hand"]
        if hand:
            user = hand["players"][hand["actor"]]["id"]
            actor = member(table, user)
            if actor and actor.get("autoplay") and not actor.get("leaving") and not actor.get("sitout"):
                if hand.get("autoplay_at", self.now) <= self.now:
                    self.action(user, "check" if rules.legal(hand)["check"] else "fold", automatic=True)
                return
            if user.startswith("npc:") or hand["deadline"] > self.now:
                return
            bank = self.db.execute(
                "SELECT time_bank FROM accounts WHERE user_id=?", (user,)
            ).fetchone()[0]
            if hand["extensions"] < 4 and bank >= 5:
                result = self.hand_funds(
                    "time_bank", user_id=user, opportunity_id=str(hand["turn"])
                )
                hand["deadline"] = result["deadline"]
                hand["extensions"] += 1
                emit(
                    table,
                    self.now,
                    "bank",
                    hand_id=hand["id"],
                    user=user,
                    turn=hand["turn"],
                )
                self.persist_hand()
            else:
                member(table, user)["sitout"] = True
                self.action(
                    user,
                    "check" if rules.legal(hand)["check"] else "fold",
                    automatic=True,
                )
            return
        self.between()
        eligible = self.available()
        if (
            table["closed"]
            or self.maintenance
            or len(eligible) < 2
            or all(m["id"].startswith("npc:") for m in eligible)
        ):
            table["countdown"] = None
            return
        if table["countdown"] is None:
            table["countdown"] = next_hand_delay(table, self.now)
            return
        if table["countdown"] > self.now:
            return
        eligible.sort(key=lambda m: m["seat"])
        next_button = next(
            (m for m in eligible if m["seat"] > table["button_seat"]), eligible[0]
        )
        table["button_seat"] = next_button["seat"]
        hand = rules.create(
            [(m["id"], stack(self.db, m["id"])) for m in eligible],
            eligible.index(next_button),
            secrets.token_hex(16),
            table.get("game_mode", "standard"),
        )
        table["hand"], table["countdown"] = hand, None
        self.funds(
            "start_hand",
            hand_id=hand["id"],
            table_id=table["id"],
            players=[p["id"] for p in hand["players"]],
            snapshot=hand,
        )
        self.finish_action({})

    def action(self, user, action, target=None, automatic=False):
        hand = self.table["hand"]
        if not hand:
            raise Conflict("hand_not_active")
        before = {p["id"]: p["paid"] for p in hand["players"]}
        rules.act(hand, user, action, target, automatic)
        self.finish_action(before)

    def command(self, user, data):
        table = self.table
        kind = data["kind"]
        m = member(table, user)
        if table["frozen"]:
            raise Conflict("table_frozen_for_recovery")
        if kind in ("join", "add_npc") and self.maintenance:
            raise Conflict("service_maintenance")
        if kind == "join":
            if m or table["closed"]:
                raise Conflict("cannot_join")
            if current_table(self.db, user):
                raise Conflict("already_seated")
            if (
                not table["members"]
                and sum(bool(t["members"] or t["hand"]) for t in all_tables(self.db))
                >= 2
            ):
                raise Conflict("table_capacity")
            occupied = {m["seat"] for m in table["members"]}
            seat = next((i for i in range(6) if i not in occupied), None)
            if seat is None:
                replacement = next(
                    (
                        m
                        for m in table["members"]
                        if m["id"].startswith("npc:") and not m.get("leaving")
                    ),
                    None,
                )
                if replacement is None:
                    raise Conflict("table_full")
                seat = replacement["seat"]
                replacement["leaving"] = True
            self.funds(
                "buy_in", user_id=user, table_id=table["id"], amount=data["amount"]
            )
            table.get("departures", {}).pop(user, None)
            table["sequence"] += 1
            table["members"].append(
                {
                    "id": user,
                    "seat": seat,
                    "mode": "pending",
                    "joined": table["sequence"],
                    "control": None,
                    "disconnected": self.now + 120,
                }
            )
            if table["owner"] is None:
                table["owner"] = user
        elif m is None:
            raise Conflict("not_seated")
        elif kind == "set_autoplay":
            enabled = data["enabled"]
            if enabled and (m.get("leaving") or m.get("sitout") or m["mode"] != "active"):
                raise Conflict("autoplay_unavailable")
            m["autoplay"] = enabled
            if table["hand"] and table["hand"]["actor"] is not None and table["hand"]["players"][table["hand"]["actor"]]["id"] == user:
                table["hand"]["autoplay_at"] = self.now + 1
        elif kind == "act":
            if m.get("autoplay"):
                raise Conflict("autoplay_enabled")
            hand = table["hand"]
            if (
                not hand
                or data.get("hand_id") != hand["id"]
                or data.get("turn") != hand["turn"]
            ):
                raise Conflict("stale_turn")
            if hand["deadline"] <= self.now:
                raise Conflict("action_deadline_passed")
            target = (
                money.amount(data["amount"]) if data.get("amount") is not None else None
            )
            self.action(user, data["action"], target)
        elif kind == "topup":
            if money.amount(data["amount"]) <= 0:
                raise Conflict("topup_must_be_positive")
            if m.get("topup"):
                raise Conflict("topup_already_queued")
            m["topup"] = data["amount"]
        elif kind == "leave":
            m["autoplay"] = False
            m["leaving"] = True
        elif kind == "sitout":
            m["autoplay"] = False
            m["sitout"] = True
        elif kind == "sit_in":
            if stack(self.db, user) <= 0 or m.get("leaving"):
                raise Conflict("topup_required")
            m["mode"] = "pending" if table["hand"] else "active"
            m["expires"], m["sitout"] = None, False
        elif kind == "close":
            raise Conflict("use_authorized_management")
        elif kind in ("add_npc", "remove_npc"):
            if table["owner"] != user:
                raise Conflict("host_required")
            if kind == "remove_npc":
                npc = member(table, data.get("npc_id"))
                if not npc or not npc["id"].startswith("npc:"):
                    raise Conflict("npc_not_found")
                npc["leaving"] = True
            else:
                occupied = {m["seat"] for m in table["members"]}
                seat = data.get("seat")
                if seat is not None:
                    if type(seat) is not int or not 0 <= seat < 6:
                        raise Conflict("invalid_seat")
                    if seat in occupied:
                        raise Conflict("seat_occupied")
                else:
                    seat = next((i for i in range(6) if i not in occupied), None)
                if seat is None:
                    raise Conflict("table_full")
                npc = "npc:" + secrets.token_hex(12)
                self.funds(
                    "npc_supply",
                    user_id=npc,
                    amount="10000",
                    actor="system",
                    reason="Fixed NPC table entry",
                )
                table["members"].append(
                    {"id": npc, "seat": seat, "mode": "pending", "failures": 0, "voice_pack": secrets.choice(VOICE_PACKS)}
                )
        else:
            raise Conflict("unknown_table_command")
        self.between()


class Tables:
    def __init__(self, store):
        self.store = store

    async def view(self, token, connection=None, table_id=None, invitation=None):
        def operation(db):
            user = authenticate(db, token)
            table = (
                load(db, table_id) if table_id else current_table(db, user) or load(db)
            )
            accessible(table, user, invitation, spectator=True)
            state = public(db, table, user, connection)
            # This read passed invitation authorization; command errors do not expose private metadata.
            state.update(name=table.get("name", "50 / 100"), game_mode=table.get("game_mode", "standard"))
            return state

        return await self.store.run(operation)

    async def command(self, token, data, now=None):
        now = time.time() if now is None else now

        def operation(db):
            user = authenticate(db, token)
            table = load(db, data["table_id"])
            cid = "game:" + user + ":" + data["command_id"]
            fingerprint = json.dumps(data, sort_keys=True)
            old = db.execute(
                "SELECT * FROM game_commands WHERE command_id=?", (cid,)
            ).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    return {
                        "result": {"error": "command_id_reused"},
                        "state": public(db, table, user, data.get("control")),
                    }
                return {
                    "result": json.loads(old["result"]),
                    "state": public(db, table, user, data.get("control")),
                }
            db.execute("SAVEPOINT table_command")
            try:
                accessible(table, user, data.get("invitation"))
                if data.get("version") != table["version"]:
                    raise Conflict("stale_table_version")
                m = member(table, user)
                if data["kind"] != "join" and (
                    m is None
                    or not m.get("control")
                    or m["control"] != data.get("control")
                    or m.get("heartbeat", 0) + 30 <= now
                ):
                    raise Conflict("not_control_endpoint")
                Transaction(db, table, cid, now, self.store.maintenance).command(
                    user, data
                )
                table["version"] += 1
                save(db, table)
                result = {"accepted": True, "version": table["version"]}
                db.execute("RELEASE table_command")
            except (Conflict, sqlite3.IntegrityError) as error:
                db.execute("ROLLBACK TO table_command")
                db.execute("RELEASE table_command")
                table = load(db, data["table_id"])
                result = {
                    "error": str(error)
                    if isinstance(error, Conflict)
                    else "funds_or_state_conflict"
                }
            db.execute(
                "INSERT INTO game_commands VALUES(?,?,?)",
                (cid, fingerprint, json.dumps(result)),
            )
            return {
                "result": result,
                "state": public(db, table, user, data.get("control")),
            }

        return await self.store.run_command(operation)

    async def connection(self, token, connection, action, now=None, table_id=None):
        now = time.time() if now is None else now

        def operation(db):
            user = authenticate(db, token)
            table = load(db, table_id) if table_id else current_table(db, user) or load(db)
            accessible(table, user, spectator=True)
            m = member(table, user)
            if m:
                if action in ("enter", "heartbeat"):
                    if not m.get("control") or m.get("heartbeat", 0) + 30 <= now:
                        m["control"] = connection
                    if m["control"] == connection:
                        m["heartbeat"], m["disconnected"] = now, None
                elif m.get("control") == connection:
                    m["control"] = None
                    m["disconnected"] = now + 120
                save(db, table)
            return public(db, table, user, connection)

        return await self.store.run(operation)

    async def tick(self, now=None, exclude_npcs=()):
        now = time.time() if now is None else now

        def operation(db):
            candidates = []
            for table in all_tables(db):
                before = copy.deepcopy(table)
                Transaction(
                    db,
                    table,
                    "tick:" + secrets.token_hex(16),
                    now,
                    self.store.maintenance,
                ).tick()
                if table != before:
                    table["version"] += 1
                    save(db, table)
                hand = table["hand"]
                if hand and hand["actor"] is not None and not table["frozen"]:
                    if hand["players"][hand["actor"]]["id"].startswith("npc:"):
                        if (hand["id"], hand["turn"]) not in exclude_npcs:
                            candidates.append(hand)
            return (
                copy.deepcopy(min(candidates, key=lambda h: h["deadline"]))
                if candidates
                else None
            )

        return await self.store.run(operation)

    async def npc_result(self, hand_id, turn, decision, error=None, now=None):
        def operation(db, decision=decision, error=error):
            # Check after the single-writer queue, at the authority boundary.
            current_time = time.time() if now is None else now
            table = next(
                (t for t in all_tables(db) if t["hand"] and t["hand"]["id"] == hand_id),
                None,
            )
            if table is None:
                return
            hand = table["hand"]
            if (
                not hand
                or hand["id"] != hand_id
                or hand["turn"] != turn
                or table["frozen"]
            ):
                return
            user = hand["players"][hand["actor"]]["id"]
            if not user.startswith("npc:"):
                raise Conflict("npc_actor_required")
            m = member(table, user)
            if current_time >= hand["deadline"]:
                error = "npc_timeout"
            if error is None:
                try:
                    rules.act(
                        copy.deepcopy(hand),
                        user,
                        decision["action"],
                        decision.get("amount"),
                        True,
                    )
                except (Conflict, KeyError, TypeError):
                    error = "illegal_npc_output"
            if error:
                m["failures"] = m.get("failures", 0) + 1
                m["notice"] = error
                decision = {"action": "check" if rules.legal(hand)["check"] else "fold"}
            else:
                m["failures"], m["notice"] = 0, None
            Transaction(db, table, "npc:" + secrets.token_hex(16), current_time).action(
                user, decision["action"], decision.get("amount"), True
            )
            table["version"] += 1
            save(db, table)

        await self.store.run(operation)

    async def recover(self, now=None):
        now = time.time() if now is None else now

        def operation(db):
            for table in all_tables(db) or [initial()]:
                for m in table["members"]:
                    if not m["id"].startswith("npc:") and m.get("control"):
                        m["control"] = None
                        m["disconnected"] = min(
                            now + 120, m.get("heartbeat", now) + 150
                        )
                for row in db.execute(
                    "SELECT * FROM hands WHERE status='active' AND table_id=?",
                    (table["id"],),
                ).fetchall():
                    paid = {
                        p["user_id"]: p["contribution"]
                        for p in db.execute(
                            "SELECT * FROM participants WHERE hand_id=?",
                            (row["hand_id"],),
                        )
                    }
                    ledger = {
                        r["user_id"]: r["paid"]
                        for r in db.execute(
                            "SELECT user_id,SUM(flight_delta) AS paid FROM ledger WHERE reason=? AND source='pot_transfer' GROUP BY user_id",
                            (row["hand_id"],),
                        )
                    }
                    reliable = all(
                        ledger.get(u, 0) == value for u, value in paid.items()
                    ) and set(ledger) <= set(paid)
                    reliable = reliable and all(
                        db.execute(
                            "SELECT in_flight FROM accounts WHERE user_id=?", (u,)
                        ).fetchone()[0]
                        == value
                        for u, value in paid.items()
                    )
                    if not reliable:
                        table["frozen"] = True
                        db.execute(
                            "INSERT INTO game_audit(table_id,event,created_at) VALUES(?,?,?)",
                            (row["table_id"], "unverifiable_contributions_frozen", now),
                        )
                        continue
                    try:
                        hand = json.loads(row["snapshot"])
                        valid = (
                            table["hand"] == hand
                            and hand["id"] == row["hand_id"]
                            and {p["id"]: p["paid"] for p in hand["players"]} == paid
                            and hand["payouts"] is None
                        )
                        cards = (
                            hand["deck"]
                            + hand["board"]
                            + [c for p in hand["players"] for c in p["cards"]]
                        )
                        valid = (
                            valid
                            and len(cards) == len(set(cards))
                            and hand.get("game_mode", "standard") == table.get("game_mode", "standard")
                            and set(cards) <= set(rules.deck_for(hand.get("game_mode", "standard")))
                            and 0 <= hand["actor"] < len(hand["players"])
                            and isinstance(hand["deadline"], (int, float))
                        )
                        valid = valid and all(
                            stack(db, p["id"]) == p["stack"]
                            and p["start"] == p["stack"] + p["paid"]
                            for p in hand["players"]
                        )
                        street = rules.STREETS.index(hand["street"])
                        valid = (
                            valid
                            and len(cards) == len(rules.deck_for(hand.get("game_mode", "standard"))) - street
                            and len(hand["board"]) == (0, 3, 4, 5)[street]
                        )
                        valid = (
                            valid
                            and all(len(p["cards"]) == 2 for p in hand["players"])
                            and math.isfinite(hand["deadline"])
                        )
                        actor = hand["players"][hand["actor"]]
                        valid = valid and not actor["folded"] and actor["stack"] > 0
                        event_row = db.execute(
                            "SELECT event FROM hand_events WHERE hand_id=? ORDER BY id DESC LIMIT 1",
                            (row["hand_id"],),
                        ).fetchone()
                        last_event = json.loads(event_row[0]) if event_row else {}
                        valid = (
                            valid
                            and last_event.get("data", {}).get("snapshot") == hand
                            and last_event.get("result", {}).get("version")
                            == row["version"]
                        )
                        clocks = db.execute(
                            "SELECT * FROM action_clocks WHERE hand_id=? AND active=1",
                            (row["hand_id"],),
                        ).fetchall()
                        if actor["id"].startswith("npc:"):
                            valid = valid and not clocks
                        else:
                            valid = (
                                valid
                                and len(clocks) == 1
                                and clocks[0]["user_id"] == actor["id"]
                                and clocks[0]["opportunity_id"] == str(hand["turn"])
                                and clocks[0]["deadline"] == hand["deadline"]
                                and clocks[0]["extensions"] == hand["extensions"]
                            )
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        IndexError,
                        AttributeError,
                    ):
                        valid = False
                    if not valid:
                        refunds = {
                            p["user_id"]: p["contribution"]
                            for p in db.execute(
                                "SELECT user_id,contribution FROM participants WHERE hand_id=?",
                                (row["hand_id"],),
                            )
                        }
                        money.execute(
                            db,
                            "recovery:void:" + row["hand_id"],
                            "void",
                            {"hand_id": row["hand_id"]},
                            now,
                        )
                        if table["hand"] and table["hand"].get("id") == row["hand_id"]:
                            table["hand"] = None
                        # Reconstruct only the refund display from the authoritative ledger;
                        # the damaged private snapshot is never used for presentation.
                        table["last"] = {
                            "id": row["hand_id"],
                            "button": 0,
                            "board": [],
                            "street": "preflop",
                            "actor": None,
                            "turn": 0,
                            "showdown": False,
                            "pots": [],
                            "void": True,
                            "payouts": refunds,
                            "refunds": refunds,
                            "players": [
                                {
                                    "id": u,
                                    "stack": stack(db, u),
                                    "bet": 0,
                                    "paid": n,
                                    "cards": [],
                                    "folded": True,
                                }
                                for u, n in refunds.items()
                            ],
                        }
                        for user, amount in refunds.items():
                            if amount:
                                emit(
                                    table,
                                    now,
                                    "refund",
                                    hand_id=row["hand_id"],
                                    user=user,
                                    amount=str(amount),
                                    reason="void",
                                )
                        event = "unrecoverable_hand_voided"
                    else:
                        event = "hand_restored_with_original_deadline"
                    db.execute(
                        "INSERT INTO game_audit(table_id,event,created_at) VALUES(?,?,?)",
                        (row["table_id"], event, now),
                    )
                table["version"] += 1
                save(db, table)

        await self.store.run(operation)
