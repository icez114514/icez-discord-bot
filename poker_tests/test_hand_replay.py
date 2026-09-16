import unittest

from poker_tests.test_table_web import TableWebTests, A, B, C


class HandReplayTests(unittest.TestCase):
    setUp = TableWebTests.setUp
    headers = TableWebTests.headers
    view = TableWebTests.view
    account = TableWebTests.account
    command = TableWebTests.command
    connect = TableWebTests.connect
    join = TableWebTests.join
    advance = TableWebTests.advance
    start_hand = TableWebTests.start_hand
    act = TableWebTests.act

    def history(self, user=A, suffix=""):
        return self.client.get("/api/hands" + suffix, headers=self.headers(user))

    def test_participant_can_replay_after_leaving_without_revealing_folded_cards(self):
        self.join(A)
        self.join(B)
        hand = self.start_hand()
        self.assertEqual(self.history(A, "/" + hand["id"]).status_code, 404)
        self.act(A, "fold")
        before = self.account()
        self.command(A, "leave")
        response = self.history(A, "/" + hand["id"])
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["complete"])
        self.assertEqual(data["frames"][-1]["settlement"]["refunds"], {B: "50"})
        self.assertEqual(
            data["frames"][-1]["settlement"]["pots"][0]["awards"], {B: "100"}
        )
        for frame in data["frames"]:
            self.assertEqual(frame["players"][1]["cards"], [])
            self.assertEqual(len(frame["players"][0]["cards"]), 2)
        other = self.history(B, "/" + hand["id"]).json()
        self.assertTrue(all(f["players"][0]["cards"] == [] for f in other["frames"]))
        self.assertEqual(self.history(C, "/" + hand["id"]).status_code, 404)
        self.assertEqual(self.history(C).json()["hands"], [])
        self.assertEqual(self.history().json()["hands"][0]["hand_id"], hand["id"])
        self.assertEqual(self.account()["settled"], before["settled"])

    def finish_checks(self):
        for _ in range(20):
            hand = self.view()["hand"]
            if hand["payouts"] is not None:
                return hand["id"]
            actor = hand["players"][hand["actor"]]["id"]
            own = self.view(actor)["hand"]
            self.act(actor, "check" if own["legal"]["check"] else "call")
        self.fail("hand did not finish")

    def test_showdown_is_hidden_until_reveal_and_reads_survive_restart(self):
        from fastapi.testclient import TestClient
        from poker.app import create_app

        self.join(A)
        self.join(B)
        self.start_hand()
        hand_id = self.finish_checks()
        self.sessions.close()
        self.app = create_app(self.config, transport=self.transport, initialize=True)
        self.client = self.sessions.enter_context(TestClient(self.app))
        data = self.history(A, "/" + hand_id).json()
        self.assertTrue(data["complete"])
        revealed = False
        for frame in data["frames"]:
            revealed |= frame["event"]["kind"] == "showdown"
            self.assertEqual(len(frame["players"][1]["cards"]), 2 if revealed else 0)
        self.assertTrue(revealed)
        self.assertEqual(
            {f["street"] for f in data["frames"]}, {"preflop", "flop", "turn", "river"}
        )
        self.assertEqual(self.history().json()["hands"][0]["hand_id"], hand_id)

    def test_pagination_and_session_revocation(self):
        self.join(A)
        self.join(B)
        ids = []
        for _ in range(3):
            hand = self.start_hand()
            ids.append(hand["id"])
            self.act(hand["players"][hand["actor"]]["id"], "fold")
        first = self.history(suffix="?limit=2").json()
        self.assertEqual([h["hand_id"] for h in first["hands"]], ids[:0:-1])
        second = self.history(suffix=f"?limit=2&before={first['next_cursor']}").json()
        self.assertEqual([h["hand_id"] for h in second["hands"]], ids[:1])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(self.history(suffix="?limit=51").status_code, 422)
        self.client.post("/auth/logout", headers=self.headers(A))
        self.assertEqual(self.history().status_code, 401)
        self.assertEqual(self.history(suffix="/" + ids[0]).status_code, 401)

    def test_incomplete_or_old_evidence_is_not_fabricated(self):
        import json

        self.join(A)
        self.join(B)
        hand_id = self.start_hand()["id"]
        self.act(A, "fold")

        original = []

        async def corrupt(mode):
            def change(db):
                row = db.execute(
                    "SELECT e.id,e.event FROM hand_events e JOIN settlements s ON s.command_id=e.command_id WHERE s.hand_id=?",
                    (hand_id,),
                ).fetchone()
                if not original:
                    original.append(row["event"])
                event = json.loads(original[0])
                if mode == "missing":
                    event["data"]["snapshot"]["presentation"].pop(1)
                elif mode == "collection":
                    hand = event["data"]["snapshot"]
                    hand["presentation"] = [
                        e for e in hand["presentation"] if e["kind"] != "collect"
                    ]
                else:
                    event["data"]["snapshot"].pop("replay_version", None)
                db.execute(
                    "UPDATE hand_events SET event=? WHERE id=?",
                    (json.dumps(event), row["id"]),
                )

            await self.app.state.store.run(change)

        for mode in ("missing", "old", "collection"):
            self.client.portal.call(corrupt, mode)
            data = self.history(suffix="/" + hand_id).json()
            self.assertFalse(data["complete"])
            self.assertEqual(data["frames"], [])
            self.assertTrue(data["reason"])

    def test_more_than_eighty_persisted_events_are_available_without_live_connection(
        self,
    ):
        from poker import rules

        hand = rules.create([(A, 10000), (B, 10000)], 0, "long-hand")
        for _ in range(85):
            actor = hand["players"][hand["actor"]]["id"]
            rules.act(hand, actor, "raise", rules.legal(hand)["min_raise_to"])
        while hand["payouts"] is None:
            actor = hand["players"][hand["actor"]]["id"]
            rules.act(hand, actor, "check" if rules.legal(hand)["check"] else "call")
        self.persist_fixture(hand)
        data = self.history(suffix="/long-hand").json()
        self.assertTrue(data["complete"])
        self.assertGreater(len(data["frames"]), 80)
        self.assertEqual(len(data["frames"]), len(hand["presentation"]))

    def persist_fixture(self, hand):
        async def persist():
            store = self.app.state.store
            for p in hand["players"]:
                await store.command(
                    "buy-" + p["id"],
                    "buy_in",
                    user_id=p["id"],
                    table_id="fixture",
                    amount=str(p["start"]),
                )
            await store.command(
                "fixture-start",
                "start_hand",
                hand_id=hand["id"],
                table_id="fixture",
                players=[p["id"] for p in hand["players"]],
                snapshot=hand,
            )
            for p in hand["players"]:
                await store.command(
                    "bet-" + p["id"],
                    "bet",
                    hand_id=hand["id"],
                    user_id=p["id"],
                    amount=str(p["paid"]),
                )
            await store.command(
                "fixture-settle",
                "settle",
                hand_id=hand["id"],
                payouts={u: str(n) for u, n in hand["payouts"].items()},
                snapshot=hand,
            )

        self.client.portal.call(persist)

    def test_split_main_side_pot_and_uncalled_refund_match_authority(self):
        from unittest.mock import patch
        from poker import rules

        draw = [
            "2c",
            "3c",
            "4c",
            "2d",
            "3d",
            "4d",
            "5c",
            "Ts",
            "Js",
            "Qs",
            "6c",
            "Ks",
            "7c",
            "As",
        ]

        def shuffle(deck):
            deck[:] = [c for c in rules.CARDS if c not in draw] + list(reversed(draw))

        with patch("secrets.SystemRandom.shuffle", side_effect=shuffle):
            hand = rules.create([(A, 5000), (B, 2000), (C, 3000)], 0, "split-hand")
        for user in (A, B, C):
            rules.act(hand, user, "all_in" if user == A else "call")
        self.persist_fixture(hand)
        data = self.history(suffix="/split-hand").json()
        self.assertTrue(data["complete"])
        settlement = data["frames"][-1]["settlement"]
        self.assertEqual(
            settlement["pots"][0]["awards"], {B: "2000", C: "2000", A: "2000"}
        )
        self.assertEqual(settlement["pots"][1]["awards"], {C: "1000", A: "1000"})
        self.assertEqual(settlement["refunds"], {A: "2000"})
        self.assertEqual(data["frames"][-1]["pot"], "0")
        self.assertEqual(
            [p["stack"] for p in data["frames"][-1]["players"]],
            ["5000", "2000", "3000"],
        )


del TableWebTests
