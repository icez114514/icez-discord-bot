import asyncio
import uuid
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from poker.internal import create_internal
from poker.management import Management
from poker_tests import test_table_web as table_web
from poker_tests.test_table_web import A, B, C


class StatisticsWebTests(unittest.TestCase):
    # Use the established HTTP/OAuth/real-table seam without inheriting its tests.
    headers = table_web.TableWebTests.headers
    view = table_web.TableWebTests.view
    account = table_web.TableWebTests.account
    command = table_web.TableWebTests.command
    connect = table_web.TableWebTests.connect
    join = table_web.TableWebTests.join
    advance = table_web.TableWebTests.advance
    start_hand = table_web.TableWebTests.start_hand
    act = table_web.TableWebTests.act

    def setUp(self):
        from poker.config import Config

        with patch(
            "poker_tests.test_table_web.Config",
            side_effect=lambda **kw: Config(**kw, table_admins=(C,), funds_admins=(B,)),
        ):
            table_web.TableWebTests.setUp(self)

    def report(self, user=A, **filters):
        response = self.client.get(
            "/api/statistics", headers=self.headers(user), params=filters
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def manage(self, actor, action, target, **extra):
        data = {
            "command_id": uuid.uuid4().hex,
            "action": action,
            "target": target,
            "reason": "Acceptance verification",
            **extra,
        }
        return self.client.post(
            "/api/management/commands", headers=self.headers(actor), json=data
        ), data

    def walk(self):
        hand = self.start_hand()
        actor = hand["players"][hand["actor"]]["id"]
        result, payload = self.act(actor, "fold")
        return hand["id"], payload

    def test_settlement_filters_stable_assets_and_private_authorization(self):
        self.join(A)
        self.join(B)
        before = self.report()
        self.assertEqual([r["rank"] for r in before["leaderboard"]], [1, 1, 1])
        hand_id, payload = self.walk()
        # Query end is exclusive: this settlement happened exactly at self.now.
        self.assertEqual(self.report()["personal"]["hands"], 0)
        self.now += 1
        report = self.report()
        self.assertEqual(report["personal"]["hands"], 1)
        self.assertEqual(report["personal"]["metrics"]["vpip"]["numerator"], 0)
        replay = self.client.post(
            "/api/table/commands", headers=self.headers(A), json=payload
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(self.report()["personal"]["hands"], 1)
        self.assertEqual(self.report(opponents="mixed")["personal"]["hands"], 0)
        self.assertEqual(self.report(opponents="human")["personal"]["hands"], 1)
        self.assertEqual(
            [r["settled"] for r in self.report(opponents="mixed")["leaderboard"]],
            [r["settled"] for r in report["leaderboard"]],
        )
        for user in (B, C):
            self.assertEqual(
                self.client.get(
                    "/api/statistics", headers=self.headers(user), params={"user_id": A}
                ).status_code,
                401,
            )
        for row in report["leaderboard"]:
            self.assertEqual(list(row["metrics"]), ["net_win"])
        self.assertNotIn("cards", str(report))
        self.assertNotIn("deck", str(report))
        self.assertEqual(
            self.client.get(
                "/api/statistics", headers=self.headers(A), params={"period": "day"}
            ).status_code,
            409,
        )
        # Start inclusive, one instant later excluded, independent of 04:00.
        self.now += 7 * 86400 - 1
        self.assertEqual(self.report(period="7")["personal"]["hands"], 1)
        self.now += 0.001
        self.assertEqual(self.report(period="7")["personal"]["hands"], 0)
        self.assertEqual(self.report(period="30")["personal"]["hands"], 1)

    def test_real_settlement_matches_authenticated_discord_query(self):
        self.join(A)
        self.join(B)
        self.walk()
        self.now += 1
        internal = create_internal(self.config, self.app)
        with TestClient(internal, client=("127.0.0.1", 12345)) as bot:
            headers = {
                "Authorization": "Bearer " + self.config.reader_token,
                "X-Actor-ID": A,
                "X-Guild-ID": self.config.guild_id,
            }
            response = bot.get("/statistics", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), self.report())
            self.assertEqual(
                bot.get(
                    "/statistics", headers=headers, params={"user_id": B}
                ).status_code,
                404,
            )
            self.assertEqual(bot.get("/statistics").status_code, 403)
            self.assertEqual(
                bot.get(
                    "/statistics", headers={**headers, "X-Guild-ID": "wrong"}
                ).status_code,
                404,
            )

    def test_roles_adjustment_replay_audit_and_forgery(self):
        for actor in (A, C):
            response, _ = self.manage(actor, "adjust", A, amount="100")
            self.assertEqual(response.status_code, 401)
        response, data = self.manage(B, "adjust", A, amount="100")
        self.assertEqual(response.status_code, 200, response.text)
        replay = self.client.post(
            "/api/management/commands", headers=self.headers(B), json=data
        )
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(self.account()["settled"], "50100")
        self.assertEqual(
            self.client.post(
                "/api/management/commands",
                headers=self.headers(B),
                json={**data, "amount": "200"},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.manage(B, "adjust", A, amount="-999999")[0].status_code, 409
        )
        self.assertEqual(self.account()["settled"], "50100")
        self.assertEqual(
            self.manage(B, "adjust", A, amount="1", reason="  ")[0].status_code, 409
        )
        forged = self.client.post(
            "/api/management/commands",
            headers={**self.headers(A), "X-Actor-ID": B},
            json={**data, "actor": B, "role": "funds"},
        )
        self.assertEqual(forged.status_code, 422)
        self.assertEqual(self.manage(B, "disable", A)[0].status_code, 401)
        history = self.client.get(
            "/api/management/audit", headers=self.headers(B)
        ).json()["audit"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["actor"], B)
        self.assertEqual(history[0]["before_state"]["settled"], "50000")
        self.assertEqual(history[0]["after_state"]["settled"], "50100")
        self.assertEqual(
            self.client.get(
                f"/api/management/ledger/{A}", headers=self.headers(C)
            ).status_code,
            401,
        )
        self.assertEqual(
            len(
                self.client.get(
                    f"/api/management/ledger/{A}", headers=self.headers(B)
                ).json()["entries"]
            ),
            2,
        )

    def test_admin_closes_active_hand_without_changing_all_in_entitlement(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.act(A, "all_in")
        before = self.view(B)["hand"]
        self.assertEqual(self.manage(A, "close", "main")[0].status_code, 401)
        response, _ = self.manage(C, "close", "main")
        self.assertEqual(response.json()["result"]["status"], "closing")
        self.assertEqual(self.view(B)["hand"]["players"], before["players"])
        self.act(B, "call")
        self.now += 1
        for user in (A, B):
            account = self.account(user)
            self.assertEqual(account["table"], "0")
            self.assertEqual(account["in_flight"], "0")
            self.assertEqual(self.report(user)["personal"]["hands"], 1)
        state = self.client.get("/api/management", headers=self.headers(C)).json()
        self.assertEqual(state["tables"][0]["status"], "closed")
        self.assertNotIn("cards", str(state))
        self.assertNotIn("deck", str(state))
        self.advance(20)
        self.assertEqual(self.report()["personal"]["hands"], 1)

    def test_disable_rejects_login_and_operations_but_preserves_all_in(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        self.act(A, "all_in")
        response, _ = self.manage(C, "disable", A)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            self.client.get("/api/account", headers=self.headers(A)).status_code, 401
        )
        from poker.store import Unauthorized

        with self.assertRaisesRegex(Unauthorized, "disabled"):
            self.client.portal.call(self.app.state.store.login, A)
        self.act(B, "call")
        account = self.client.portal.call(self.app.state.store.account, A)
        self.assertEqual(account["table"], "0")
        self.assertEqual(account["in_flight"], "0")
        self.assertEqual(account["hand_progress"], 1)

    def test_audited_rebuild_is_idempotent_and_keeps_timebank_progress(self):
        self.join(A)
        self.join(B)
        hand_id, _ = self.walk()
        self.now += 1
        before = self.report()
        bank = self.account()["hand_progress"]
        response, data = self.manage(C, "rebuild", hand_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.report(), before)
        self.assertEqual(self.account()["hand_progress"], bank)
        self.assertEqual(
            self.client.post(
                "/api/management/commands", headers=self.headers(C), json=data
            ).json(),
            response.json(),
        )
        history = self.client.get(
            "/api/management/audit", headers=self.headers(C)
        ).json()["audit"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["after_state"], {"redacted": True})

    def test_adjustment_and_buyin_share_one_writer(self):
        management = Management(self.app.state.store, self.config)

        async def compete():
            return await asyncio.gather(
                management.command(
                    {
                        "command_id": "race",
                        "action": "adjust",
                        "target": A,
                        "amount": "-49000",
                        "reason": "race",
                    },
                    token=self.tokens[B],
                ),
                self.app.state.store.command(
                    "race-buyin", "buy_in", user_id=A, table_id="main", amount="2000"
                ),
                return_exceptions=True,
            )

        results = self.client.portal.call(compete)
        self.assertEqual(sum(isinstance(r, Exception) for r in results), 1)
        account = self.account()
        self.assertGreaterEqual(int(account["available"]), 0)
        self.assertEqual(
            int(account["available"]) + int(account["table"]), int(account["settled"])
        )

    def test_asset_ties_share_rank_and_rejected_adjustment_stays_rejected(self):
        response, _ = self.manage(B, "adjust", C, amount="-1")
        self.assertEqual(response.status_code, 200)
        board = self.report()["leaderboard"]
        self.assertEqual(
            [(r["user_id"], r["rank"]) for r in board], [(A, 1), (B, 1), (C, 3)]
        )
        rejected, command = self.manage(B, "adjust", A, amount="-60000")
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(
            self.manage(B, "adjust", A, amount="20000")[0].status_code, 200
        )
        replay = self.client.post(
            "/api/management/commands", headers=self.headers(B), json=command
        )
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(self.account()["settled"], "70000")

    def test_host_cannot_use_legacy_close_command(self):
        self.join(A)
        response, _ = self.command(A, "close")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["result"]["error"], "use_authorized_management"
        )
        self.assertFalse(self.view()["closed"])

    def test_guild_member_without_account_can_read_public_rankings(self):
        outsider = "444444444444444444"
        internal = create_internal(self.config, self.app)
        with TestClient(internal, client=("127.0.0.1", 12345)) as bot:
            headers = {
                "Authorization": "Bearer " + self.config.reader_token,
                "X-Actor-ID": outsider,
                "X-Guild-ID": self.config.guild_id,
            }
            response = bot.get("/statistics", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["leaderboard"], self.report()["leaderboard"]
            )
            self.assertEqual(response.json()["personal"]["hands"], 0)
            self.assertEqual(response.json()["personal"]["user_id"], outsider)
            self.assertEqual(
                bot.get(
                    "/statistics", headers=headers, params={"user_id": A}
                ).status_code,
                404,
            )
            self.assertEqual(self.manage(C, "disable", A)[0].status_code, 200)
            self.assertEqual(
                bot.get(
                    "/statistics", headers={**headers, "X-Actor-ID": A}
                ).status_code,
                404,
            )
        self.assertEqual(len(self.report(B)["leaderboard"]), 3)
