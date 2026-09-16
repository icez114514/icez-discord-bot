import contextlib
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from poker.app import create_app
from poker.config import Config


A, B, C = "111111111111111111", "222222222222222222", "333333333333333333"


class TableWebTests(unittest.TestCase):
    def setUp(self):
        self.resources = contextlib.ExitStack()
        self.addCleanup(self.resources.close)
        self.directory = Path(
            self.resources.enter_context(tempfile.TemporaryDirectory())
        )
        self.now = time.time()
        self.resources.enter_context(patch("time.time", side_effect=lambda: self.now))
        self.config = Config(
            data_dir=self.directory,
            environment="test",
            origin="http://testserver",
            client_id="123",
            client_secret="s" * 32,
            bot_token="b" * 32,
            guild_id="456",
            reader_token="r" * 32,
            funds_token="f" * 32,
        )

        def discord(request):
            if request.url.path.endswith("/oauth2/token"):
                return httpx.Response(
                    200,
                    json={
                        "access_token": parse_qs(request.content.decode())["code"][0]
                    },
                )
            if request.url.path.endswith("/users/@me"):
                return httpx.Response(
                    200, json={"id": request.headers["authorization"].split()[-1]}
                )
            return httpx.Response(200, json={})

        self.transport = httpx.MockTransport(discord)
        self.app = create_app(self.config, transport=self.transport, initialize=True)
        self.drop_ack = False

        @self.app.middleware("http")
        async def lost_delivery(request, call_next):
            response = await call_next(request)
            if self.drop_ack and request.url.path == "/api/table/commands":
                self.drop_ack = False
                raise ConnectionResetError("simulated delivery loss after commit")
            return response

        self.sessions = self.resources.enter_context(contextlib.ExitStack())
        self.client = self.sessions.enter_context(TestClient(self.app))
        self.tokens, self.controls = {}, {}
        for user in (A, B, C):
            response = self.client.get("/auth/login", follow_redirects=False)
            state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
            response = self.client.get(
                "/auth/callback",
                params={"code": user, "state": state},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            self.tokens[user] = self.client.cookies.get("poker_session")
            self.client.cookies.clear()

    def headers(self, user):
        return {
            "origin": self.config.origin,
            "cookie": "poker_session=" + self.tokens[user],
        }

    def view(self, user=A):
        response = self.client.get("/api/table", headers=self.headers(user))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def account(self, user=A):
        return self.client.get("/api/account", headers=self.headers(user)).json()

    def command(self, user, kind, **extra):
        payload = {
            "command_id": uuid.uuid4().hex,
            "table_id": "main",
            "version": self.view(user)["version"],
            "kind": kind,
            "control": self.controls.get(user),
            **extra,
        }
        for _ in range(3):
            response = self.client.post(
                "/api/table/commands", headers=self.headers(user), json=payload
            )
            if (
                response.status_code != 409
                or response.json().get("result", {}).get("error")
                != "stale_table_version"
            ):
                return response, payload
            payload.update(
                command_id=uuid.uuid4().hex, version=response.json()["state"]["version"]
            )
        self.fail("table version kept changing")

    def connect(self, user):
        socket = self.sessions.enter_context(
            self.client.websocket_connect("/ws/table", headers=self.headers(user))
        )
        ready = socket.receive_json()
        self.assertEqual(ready["type"], "ready")
        self.controls[user] = ready["connection"]
        return socket

    def join(self, user, amount="2000"):
        response, _ = self.command(user, "join", amount=amount)
        self.assertEqual(response.status_code, 200, response.text)
        return self.connect(user)

    def advance(self, seconds):
        self.now += seconds
        self.client.portal.call(self.app.state.tables.tick, self.now)

    def start_hand(self):
        self.advance(0)
        self.advance(5)
        hand = self.view()["hand"]
        self.assertIsNotNone(hand)
        return hand

    def act(self, user, action, amount=None):
        hand = self.view(user)["hand"]
        extra = {"hand_id": hand["id"], "turn": hand["turn"], "action": action}
        if amount is not None:
            extra["amount"] = amount
        response, payload = self.command(user, "act", **extra)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), payload

    def test_public_events_preserve_actions_collection_and_replay_identity(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        actor = hand["players"][hand["actor"]]["id"]
        outcome, payload = self.act(actor, "call")
        events = outcome["state"]["events"]
        self.assertEqual(
            [e["amount"] for e in events if e["kind"] == "action"], ["50", "100", "50"]
        )
        self.assertEqual(events[-2]["action"], "call")
        self.assertEqual(events[-2]["raise_to"], "100")
        again = self.client.post(
            "/api/table/commands", headers=self.headers(actor), json=payload
        ).json()
        self.assertEqual(again["state"]["events"], events)
        hand = self.view()["hand"]
        self.act(hand["players"][hand["actor"]]["id"], "check")
        state = self.view()
        collection = next(e for e in state["events"] if e["kind"] == "collect")
        self.assertEqual(collection["amounts"], {A: "100", B: "100"})
        self.assertEqual(state["hand"]["pot"], "200")
        self.assertEqual(
            [e["seq"] for e in state["events"]], list(range(1, state["event_seq"] + 1))
        )
        self.assertEqual(len({e["id"] for e in state["events"]}), len(state["events"]))
        import json

        serialized = json.dumps(state["events"])
        for private in ("deck", "snapshot", "control", "cards"):
            self.assertNotIn(private, serialized)

    def test_invalid_websocket_command_returns_latest_state_without_disconnect(self):
        socket = self.join(A)
        socket.send_json(
            {
                "type": "command",
                "command": {
                    "command_id": "bad",
                    "table_id": "main",
                    "version": self.view()["version"],
                    "kind": "topup",
                    "amount": "not-an-amount",
                    "control": self.controls[A],
                },
            }
        )
        while True:
            message = socket.receive_json()
            if message["type"] == "result":
                break
        self.assertIn("error", message["result"])
        self.assertTrue(message["state"]["joined"])
        self.assertEqual(self.account()["table"], "2000")

    def test_two_identities_play_a_real_hand_with_private_cards_and_replay(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        own = self.view(A)["hand"]
        other = self.view(B)["hand"]
        self.assertEqual([len(p["cards"]) for p in own["players"]], [2, 0])
        self.assertEqual([len(p["cards"]) for p in other["players"]], [0, 2])
        self.assertNotIn("deck", str(own))
        self.assertEqual(hand["actor"], 0)
        outcome, payload = self.act(A, "call")
        replay = self.client.post(
            "/api/table/commands", headers=self.headers(A), json=payload
        )
        self.assertEqual(replay.json()["result"], outcome["result"])
        self.assertEqual(self.account(A)["in_flight"], "100")
        for _ in range(16):
            state = self.view(A)["hand"]
            if state["payouts"] is not None:
                break
            actor = state["players"][state["actor"]]["id"]
            view = self.view(actor)["hand"]
            self.act(actor, "check" if view["legal"]["check"] else "call")
        else:
            self.fail("hand did not settle")
        self.assertEqual(len(state["board"]), 5)
        self.assertEqual(sum(int(self.account(u)["table"]) for u in (A, B)), 4000)
        self.assertEqual([self.account(u)["in_flight"] for u in (A, B)], ["0", "0"])
        self.assertEqual([len(p["cards"]) for p in state["players"]], [2, 2])
        self.advance(0)
        self.advance(5)
        self.assertNotEqual(self.view()["hand"]["id"], hand["id"])

    def test_maintenance_finishes_current_hand_and_prevents_new_admission(self):
        from poker.operations import maintenance

        self.join(A)
        self.join(B)
        self.start_hand()
        maintenance(self.config, True)
        rejected, _ = self.command(C, "join", amount="2000")
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["result"]["error"], "service_maintenance")
        created = self.client.post(
            "/api/tables",
            headers=self.headers(C),
            json={"command_id": uuid.uuid4().hex, "name": "Blocked", "amount": "2000"},
        )
        self.assertEqual(created.status_code, 409)
        self.act(A, "fold")
        self.advance(0)
        self.advance(10)
        self.assertIsNotNone(self.view()["hand"]["payouts"])
        self.assertEqual(self.account(A)["in_flight"], "0")
        maintenance(self.config, False)
        self.start_hand()

    def test_full_snapshot_restore_preserves_game_preferences_and_statistics(self):
        from dataclasses import replace
        from poker.backups import take_backup, restore

        self.join(A)
        self.join(B)
        self.start_hand()
        self.act(A, "fold")
        self.client.put(
            "/api/preferences",
            headers=self.headers(A),
            json={"theme": "burgundy_leather"},
        )
        routes = ("/api/account", "/api/preferences", "/api/statistics")
        before = {
            route: self.client.get(route, headers=self.headers(A)).json()
            for route in routes
        }
        result = self.client.portal.call(
            take_backup, self.app.state.store, self.directory / "snapshots"
        )
        restored = self.directory / "restored"
        restore(
            self.directory / "snapshots" / result["file"], restored, result["sha256"]
        )
        self.sessions.close()
        self.config = replace(self.config, data_dir=restored)
        self.sessions = self.resources.enter_context(contextlib.ExitStack())
        self.app = create_app(self.config, transport=self.transport)
        self.client = self.sessions.enter_context(TestClient(self.app))
        for route in routes:
            self.assertEqual(
                self.client.get(route, headers=self.headers(A)).json(), before[route]
            )
        self.assertTrue(self.client.get("/health").json()["maintenance"])

    def restart(self, corrupt=None):
        self.sessions.close()
        if corrupt:
            import sqlite3

            with contextlib.closing(sqlite3.connect(self.directory / "poker.db")) as db:
                with db:
                    db.execute(corrupt)
        self.sessions = self.resources.enter_context(contextlib.ExitStack())
        self.app = create_app(self.config, transport=self.transport)
        self.client = self.sessions.enter_context(TestClient(self.app))
        self.controls.clear()

    def test_restart_preserves_cards_deadline_and_original_command_outcome(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        _, payload = self.act(A, "call")
        before = self.view(B)["hand"]
        self.restart()
        after = self.view(B)["hand"]
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["players"], before["players"])
        self.assertEqual(after["deadline"], before["deadline"])
        replay = self.client.post(
            "/api/table/commands", headers=self.headers(A), json=payload
        )
        self.assertTrue(replay.json()["result"]["accepted"])
        self.assertEqual(self.account(A)["in_flight"], "100")
        self.assertEqual(self.account(B)["in_flight"], "100")
        self.assertEqual(hand["id"], after["id"])

    def test_unrecoverable_hand_refunds_folded_blind_once_without_rewards(self):
        for user in (A, B, C):
            self.join(user)
        self.start_hand()
        self.act(A, "raise", "300")
        self.act(B, "fold")
        self.act(C, "call")
        self.restart("UPDATE hands SET snapshot='{}' WHERE status='active'")
        state = self.view()
        self.assertTrue(state["hand"]["settlement"]["void"])
        self.assertEqual(state["hand"]["settlement"]["pots"], [])
        self.assertEqual(
            state["hand"]["settlement"]["refunds"], {A: "300", B: "50", C: "300"}
        )
        refund_events = [e for e in state["events"] if e.get("reason") == "void"]
        self.assertEqual(len(refund_events), 3)
        self.assertFalse(any(e["kind"] == "payout" for e in state["events"]))
        for user in (A, B, C):
            self.assertEqual(self.account(user)["table"], "2000")
            self.assertEqual(self.account(user)["in_flight"], "0")
            self.assertEqual(self.account(user)["hand_progress"], 0)
        self.restart()
        self.assertEqual([self.account(u)["table"] for u in (A, B, C)], ["2000"] * 3)

    def test_unverifiable_contribution_freezes_funds_instead_of_guessing_refund(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.restart("UPDATE participants SET contribution=contribution+1")
        self.assertTrue(self.view()["frozen"])
        self.assertEqual(self.account(A)["in_flight"], "50")
        self.assertEqual(self.account(B)["in_flight"], "100")
        self.connect(A)
        response, _ = self.command(A, "leave")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["result"]["error"], "table_frozen_for_recovery"
        )

    def test_four_time_bank_segments_are_spent_only_at_each_deadline(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        deadline = hand["deadline"]
        self.advance(19)
        self.assertEqual(self.account(A)["time_bank"], 60)
        self.advance(1)
        self.assertEqual(self.account(A)["time_bank"], 55)
        self.assertEqual(self.view()["hand"]["deadline"], deadline + 5)
        self.advance(4)
        self.assertEqual(self.account(A)["time_bank"], 55)
        self.advance(1)
        self.assertEqual(self.account(A)["time_bank"], 50)
        self.advance(5)
        self.assertEqual(self.account(A)["time_bank"], 45)
        self.advance(5)
        self.assertEqual(self.account(A)["time_bank"], 40)
        self.advance(5)
        self.assertIsNotNone(self.view()["hand"]["payouts"])
        self.assertEqual(self.view()["members"][0]["mode"], "sitout")
        self.assertEqual(self.account(A)["hand_progress"], 1)
        self.assertEqual(self.account(A)["time_bank"], 40)

    def wait_hand(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            hand = self.view()["hand"]
            if predicate(hand):
                return hand
            time.sleep(0.02)
        self.fail("expected hand transition did not arrive")

    def test_fixed_npc_responds_and_settles_on_the_real_ledger(self):
        self.join(A, "10000")
        response, _ = self.command(A, "add_npc")
        self.assertEqual(response.status_code, 200, response.text)
        self.start_hand()
        for _ in range(30):
            hand = self.wait_hand(
                lambda h: h["payouts"] is not None
                or h["players"][h["actor"]]["id"] == A
            )
            if hand["payouts"] is not None:
                break
            own = self.view()["hand"]
            self.act(A, "check" if own["legal"]["check"] else "call")
        else:
            self.fail("NPC hand did not settle")
        members = self.view()["members"]
        self.assertEqual(sum(int(m["stack"]) for m in members), 20000)
        npc = next(m for m in members if m["id"].startswith("npc:"))
        self.assertIsNone(npc["notice"])
        self.assertEqual(npc["npc_failures"], 0)
        self.assertEqual(self.account()["in_flight"], "0")

    def test_npc_failure_checks_or_folds_then_sits_out_after_three_failures(self):
        self.join(A)
        self.command(A, "add_npc")
        self.client.portal.call(self.app.state.npc.close)
        self.start_hand()
        self.act(A, "call")
        self.wait_hand(
            lambda h: h["street"] == "flop" and h["players"][h["actor"]]["id"] == A
        )
        self.act(A, "raise", "100")
        self.wait_hand(lambda h: h["payouts"] is not None)
        npc = next(m for m in self.view()["members"] if m["id"].startswith("npc:"))
        self.assertEqual(npc["npc_failures"], 3)
        self.assertEqual(npc["mode"], "sitout")
        self.assertEqual(npc["notice"], "npc_unavailable")
        self.assertEqual(self.account()["time_bank"], 60)

    def test_single_control_and_invalid_raise_do_not_change_hand_or_clock(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        primary = self.controls[A]
        self.connect(A)
        response, _ = self.command(
            A, "act", hand_id=hand["id"], turn=hand["turn"], action="call"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["result"]["error"], "not_control_endpoint")
        self.controls[A] = primary
        response, _ = self.command(
            A,
            "act",
            hand_id=hand["id"],
            turn=hand["turn"],
            action="raise",
            amount="2001",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.account()["in_flight"], "50")
        self.assertEqual(self.view()["hand"]["deadline"], hand["deadline"])

    def test_all_in_player_leaves_only_after_showdown_and_receives_entitlement(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.act(A, "all_in")
        response, _ = self.command(A, "leave")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.account(A)["in_flight"], "2000")
        self.assertTrue(self.view(A)["joined"])
        self.act(B, "call")
        self.assertFalse(self.view(A)["joined"])
        self.assertEqual(self.account(A)["table"], "0")
        self.assertEqual(self.account(A)["in_flight"], "0")
        self.assertIn(self.account(A)["available"], ("48000", "50000", "52000"))
        self.assertEqual(self.view(B)["owner"], B)

    def test_ten_dealt_settlements_reward_once_across_restarts(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.advance(20)
        self.act(A, "call")
        self.act(B, "fold")
        self.assertEqual(self.account(A)["time_bank"], 55)
        for _ in range(9):
            self.restart()
            self.connect(A)
            self.connect(B)
            hand = self.start_hand()
            actor = hand["players"][hand["actor"]]["id"]
            _, payload = self.act(actor, "fold")
        self.assertEqual(self.account(A)["time_bank"], 60)
        self.assertEqual(self.account(B)["time_bank"], 60)
        self.assertEqual(self.account(A)["hand_progress"], 0)
        self.restart()
        replay = self.client.post(
            "/api/table/commands", headers=self.headers(actor), json=payload
        )
        self.assertTrue(replay.json()["result"]["accepted"])
        self.assertEqual(self.account(A)["hand_progress"], 0)

    def test_leaving_during_countdown_cancels_deal_without_blinds(self):
        self.join(A)
        self.join(B)
        self.advance(0)
        self.assertIsNotNone(self.view()["countdown"])
        response, _ = self.command(B, "leave")
        self.assertEqual(response.status_code, 200)
        self.advance(5)
        self.assertIsNone(self.view()["hand"])
        self.assertEqual(self.account(A)["table"], "2000")
        self.assertEqual(self.account(B)["available"], "50000")

    def test_queued_topup_rechecks_balance_atomically_after_settlement(self):
        from functools import partial

        self.join(A)
        self.join(B)
        self.start_hand()
        response, _ = self.command(A, "topup", amount="1000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.account(A)["table"], "1950")
        self.client.portal.call(
            partial(
                self.app.state.store.command,
                "concurrent-debit",
                "adjust",
                user_id=A,
                amount="-48000",
                actor="999",
                reason="Concurrent debit for queued topup scenario",
            )
        )
        self.act(A, "fold")
        me = next(m for m in self.view()["members"] if m["id"] == A)
        self.assertEqual(me["notice"], "topup_rejected")
        self.assertIsNone(me["topup"])
        self.assertEqual(self.account(A)["available"], "0")
        self.assertEqual(self.account(A)["table"], "1950")
        self.start_hand()
        self.assertIn(A, [p["id"] for p in self.view()["hand"]["players"]])

    def test_sitout_seat_expires_after_two_minutes_and_returns_remaining_stack(self):
        self.join(A)
        response, _ = self.command(A, "sitout")
        self.assertEqual(response.status_code, 200)
        self.advance(119)
        self.assertTrue(self.view()["joined"])
        self.advance(1)
        self.assertFalse(self.view()["joined"])
        self.assertEqual(self.account()["available"], "50000")

    def test_human_replaces_npc_next_hand_with_own_money(self):
        self.join(A)
        for _ in range(5):
            response, _ = self.command(A, "add_npc")
            self.assertEqual(response.status_code, 200)
        self.client.portal.call(self.app.state.npc.close)
        original = self.start_hand()
        self.join(B)
        self.assertNotIn(B, [p["id"] for p in self.view(B)["hand"]["players"]])
        for _ in range(25):
            hand = self.wait_hand(
                lambda h: h["payouts"] is not None
                or h["players"][h["actor"]]["id"] == A
            )
            if hand["payouts"] is not None:
                break
            legal = self.view()["hand"]["legal"]
            self.act(A, "check" if legal["check"] else "call")
        else:
            self.fail("hand did not settle with failed NPCs")
        state = self.view(B)
        human = next(m for m in state["members"] if m["id"] == B)
        self.assertEqual(human["stack"], "2000")
        self.assertEqual(self.account(B)["available"], "48000")
        self.assertEqual(len(state["members"]), 6)
        self.start_hand()
        self.assertNotEqual(self.view()["hand"]["id"], original["id"])
        self.assertIn(B, [p["id"] for p in self.view()["hand"]["players"]])

    def test_committed_action_survives_lost_ack_and_restart_without_double_bet(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        payload = {
            "command_id": "lost-ack",
            "table_id": "main",
            "version": self.view()["version"],
            "kind": "act",
            "control": self.controls[A],
            "hand_id": hand["id"],
            "turn": hand["turn"],
            "action": "call",
        }
        self.drop_ack = True
        with self.assertRaises(ConnectionResetError):
            self.client.post(
                "/api/table/commands", headers=self.headers(A), json=payload
            )
        self.restart()
        response = self.client.post(
            "/api/table/commands", headers=self.headers(A), json=payload
        )
        self.assertTrue(response.json()["result"]["accepted"])
        self.assertEqual(self.account(A)["in_flight"], "100")
        self.assertEqual(self.account(A)["table"], "1900")

    def test_another_turn_in_same_street_gets_new_base_clock_not_new_bank(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.advance(20)
        self.act(A, "call")
        self.act(B, "raise", "300")
        hand = self.view()["hand"]
        self.assertEqual(hand["street"], "preflop")
        self.assertEqual(hand["deadline"], self.now + 20)
        self.assertEqual(hand["extensions"], 0)
        self.assertEqual(self.account(A)["time_bank"], 55)

    def test_inconsistent_clock_snapshot_is_not_silently_restored(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.restart("UPDATE action_clocks SET deadline=deadline+500 WHERE active=1")
        self.assertEqual(self.account(A)["in_flight"], "0")
        self.assertEqual(self.account(B)["in_flight"], "0")
        self.assertEqual(self.account(A)["hand_progress"], 0)

    def test_required_command_fields_are_shared_by_http_and_websocket(self):
        socket = self.join(A)
        payload = {
            "command_id": "missing-amount",
            "table_id": "main",
            "version": self.view()["version"],
            "kind": "topup",
            "control": self.controls[A],
        }
        response = self.client.post(
            "/api/table/commands", headers=self.headers(A), json=payload
        )
        self.assertEqual(response.status_code, 422)
        socket.send_json({"type": "command", "command": payload})
        while True:
            message = socket.receive_json()
            if message["type"] == "result":
                break
        self.assertEqual(message["result"]["error"], "invalid_command")
        self.assertEqual(self.account()["table"], "2000")

    def test_late_legal_npc_raise_falls_back_to_check(self):
        import asyncio

        async def stop_scheduler():
            for task in asyncio.all_tasks():
                if task.get_coro().__name__ == "run_tables":
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

        self.client.portal.call(stop_scheduler)
        self.join(A)
        self.command(A, "add_npc")
        self.start_hand()
        self.act(A, "call")
        hand = self.view()["hand"]
        self.assertTrue(hand["players"][hand["actor"]]["id"].startswith("npc:"))
        self.client.portal.call(
            self.app.state.tables.npc_result,
            hand["id"],
            hand["turn"],
            {"action": "raise", "amount": 200},
            None,
            self.now + 3,
        )
        state = self.view()
        npc = next(m for m in state["members"] if m["id"].startswith("npc:"))
        self.assertEqual(npc["npc_failures"], 1)
        self.assertEqual(npc["notice"], "npc_timeout")
        self.assertEqual(state["hand"]["street"], "flop")
