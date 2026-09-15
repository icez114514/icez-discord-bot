import tempfile
import unittest
from pathlib import Path
from poker.store import Store, Conflict


class CommandContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_command_replays_original_rejection_after_balance_changes(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                await store.login("111")
                with self.assertRaises(Conflict):
                    await store.command("help", "subsidy", user_id="111")
                await store.command(
                    "debit",
                    "adjust",
                    user_id="111",
                    amount="-49000",
                    actor="999",
                    reason="Test debit",
                )
                with self.assertRaises(Conflict):
                    await store.command("help", "subsidy", user_id="111")
                self.assertEqual((await store.account("111"))["available"], "1000")
