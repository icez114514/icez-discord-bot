import uuid

from poker_tests.test_table_web import TableWebTests, A, B, C


class LobbyWebTests(TableWebTests):
    def create_table(self, user, **extra):
        return self.client.post(
            "/api/tables",
            headers=self.headers(user),
            json={
                "command_id": uuid.uuid4().hex,
                "name": "Friends",
                "private": False,
                "amount": "2000",
                **extra,
            },
        )

    def test_two_table_capacity_and_account_membership(self):
        first = self.create_table(A)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.create_table(B)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertNotEqual(first.json()["state"]["id"], second.json()["state"]["id"])
        rejected = self.create_table(C)
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["result"]["error"], "table_capacity")
        self.assertEqual(self.account(C)["available"], "50000")
        duplicate = self.create_table(A)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["result"]["error"], "already_seated")
        lobby = self.client.get("/api/tables", headers=self.headers(A)).json()
        self.assertEqual(len(lobby["tables"]), 2)
        self.assertEqual(lobby["current_table"], first.json()["state"]["id"])

    def test_private_invitation_rotation_and_projection(self):
        created = self.create_table(A, private=True).json()
        table_id = created["state"]["id"]
        self.assertEqual(
            self.client.get("/api/tables", headers=self.headers(B)).json()["tables"], []
        )
        hidden = self.client.get(
            "/api/table", params={"table_id": table_id}, headers=self.headers(B)
        )
        self.assertEqual(hidden.status_code, 409)
        self.assertEqual(hidden.json(), {"error": "table_unavailable"})
        owner = self.connect(A)
        invitation = self.client.get(
            "/api/table/invitation", headers=self.headers(A)
        ).json()["invitation"]
        denied = self.client.get("/api/table/invitation", headers=self.headers(B))
        self.assertEqual(denied.status_code, 409)
        preview = self.client.get(
            "/api/table",
            params={"table_id": table_id},
            headers={**self.headers(B), "x-table-invitation": invitation},
        ).json()
        self.assertFalse(preview["joined"])
        self.assertNotIn("members", preview)
        rotated = self.client.post(
            "/api/table/invitation",
            headers=self.headers(A),
            json={"command_id": uuid.uuid4().hex, "control": self.controls[A]},
        ).json()["invitation"]
        self.assertNotEqual(invitation, rotated)
        payload = {
            "command_id": uuid.uuid4().hex,
            "table_id": table_id,
            "version": preview["version"],
            "kind": "join",
            "amount": "2000",
            "invitation": invitation,
        }
        rejected = self.client.post(
            "/api/table/commands", headers=self.headers(B), json=payload
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertNotIn("members", rejected.json()["state"])
        payload.update(command_id=uuid.uuid4().hex, invitation=rotated)
        joined = self.client.post(
            "/api/table/commands", headers=self.headers(B), json=payload
        )
        self.assertEqual(joined.status_code, 200, joined.text)
        peer = self.connect(B)
        self.start_hand()
        for user in (A, B):
            view = self.view(user)
            self.assertNotIn("invitation", view)
            for player in view["hand"]["players"]:
                self.assertEqual(len(player["cards"]), 2 if player["id"] == user else 0)
        owner.close()
        peer.close()

    def test_theme_is_account_preference_and_does_not_mutate_game(self):
        self.join(A)
        self.join(B)
        self.start_hand()
        before = self.view(A)
        account = self.account(A)
        prefs = self.client.get("/api/preferences", headers=self.headers(A))
        self.assertEqual(prefs.status_code, 200)
        self.assertEqual(prefs.json()["theme"], "classic_walnut")
        for theme in ("midnight_oak", "burgundy_leather", "classic_walnut"):
            saved = self.client.put(
                "/api/preferences", headers=self.headers(A), json={"theme": theme}
            )
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(
                self.client.get("/api/preferences", headers=self.headers(A)).json()[
                    "theme"
                ],
                theme,
            )
            self.assertEqual(
                self.client.get("/api/preferences", headers=self.headers(B)).json()[
                    "theme"
                ],
                "classic_walnut",
            )
            self.assertEqual(self.view(A), before)
            self.assertEqual(self.account(A), account)
        fallback = self.client.put(
            "/api/preferences", headers=self.headers(A), json={"theme": "retired"}
        )
        self.assertEqual(fallback.json()["theme"], "classic_walnut")
        self.assertEqual(self.client.get("/api/preferences").status_code, 401)

    def test_capacity_race_and_release_after_last_human_leaves(self):
        from concurrent.futures import ThreadPoolExecutor

        self.create_table(A)
        self.connect(A)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.create_table, (B, C)))
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        losing = C if results[0].status_code == 200 else B
        self.assertEqual(self.account(losing)["available"], "50000")
        for kind in ("add_npc", "leave"):
            response, _ = self.command(A, kind, table_id=self.view(A)["id"])
            self.assertEqual(response.status_code, 200, response.text)
        retry = self.create_table(losing)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(self.account(A)["available"], "50000")

    def test_two_active_hands_and_theme_survive_restart_without_duplicate_buyin(self):
        ids = {}
        for user in (A, B):
            payload = {
                "command_id": uuid.uuid4().hex,
                "name": "Recovery",
                "private": user == B,
                "amount": "2000",
            }
            created = self.client.post(
                "/api/tables", headers=self.headers(user), json=payload
            )
            ids[user] = created.json()["state"]["id"]
            replay = self.client.post(
                "/api/tables", headers=self.headers(user), json=payload
            )
            self.assertEqual(replay.json()["result"], created.json()["result"])
            self.assertEqual(self.account(user)["available"], "48000")
            self.connect(user)
            response, _ = self.command(user, "add_npc", table_id=ids[user])
            self.assertEqual(response.status_code, 200)
        self.start_hand()
        hands = {user: self.view(user)["hand"] for user in (A, B)}
        self.assertNotEqual(hands[A]["id"], hands[B]["id"])
        self.client.put(
            "/api/preferences", headers=self.headers(B), json={"theme": "midnight_oak"}
        )
        self.restart()
        for user in (A, B):
            restored = self.view(user)["hand"]
            self.assertEqual(restored, hands[user])
            self.assertEqual(self.account(user)["available"], "48000")
        self.assertEqual(
            self.client.get("/api/preferences", headers=self.headers(B)).json()[
                "theme"
            ],
            "midnight_oak",
        )


def load_tests(loader, tests, pattern):
    import unittest

    return unittest.TestSuite(
        LobbyWebTests(name)
        for name in LobbyWebTests.__dict__
        if name.startswith("test_")
    )
