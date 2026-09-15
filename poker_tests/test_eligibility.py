import tempfile
import unittest
from pathlib import Path
from poker.store import Store, Unauthorized
from poker.eligibility import Eligibility


class Membership:
    def __init__(self, result):
        self.result = result
        self.before_reply = None

    async def member(self, user):
        if self.before_reply:
            await self.before_reply(user)
        return self.result


class EligibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_rechecks_presence_and_revokes_all_sessions_only_on_confirmed_absence(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                first = await store.login("111")
                second = await store.login("111")
                membership = Membership("absent")

                async def enter(user):
                    await store.presence(first, "connection1", "enter", now=100)

                membership.before_reply = enter
                scan = Eligibility(store, membership)
                await scan.run(now=100)
                self.assertEqual(await store.authenticate(second), "111")
                await store.presence(first, "connection1", "leave", now=101)
                membership.before_reply = None
                await scan.run(now=102)
                self.assertEqual(await store.authenticate(second), "111")
                membership.result = "retry"
                await scan.run(now=100 + 86400)
                self.assertEqual(await store.authenticate(second), "111")
                membership.result = "absent"
                await scan.run(now=100 + 2 * 86400)
                for token in (first, second):
                    with self.assertRaises(Unauthorized):
                        await store.authenticate(token)
                self.assertEqual((await store.account("111"))["available"], "50000")
