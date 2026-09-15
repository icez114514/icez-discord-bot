import asyncio
import tempfile
import unittest
from pathlib import Path
from poker.store import Store, Conflict


class AccountingEdgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_subsidy_races_open_hand_without_ever_observing_partial_state(self):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                for user in ("111", "222"):
                    await store.login(user)
                    await store.command(
                        "buy" + user,
                        "buy_in",
                        user_id=user,
                        table_id="t",
                        amount="2000",
                    )
                await store.command(
                    "debit",
                    "adjust",
                    user_id="111",
                    amount="-48000",
                    actor="999",
                    reason="Concurrent subsidy setup",
                )
                results = await asyncio.gather(
                    store.command(
                        "start",
                        "start_hand",
                        hand_id="h",
                        table_id="t",
                        players=["111", "222"],
                        snapshot={},
                    ),
                    store.command("help", "subsidy", user_id="111"),
                    return_exceptions=True,
                )
                self.assertEqual((await store.hand("h"))["status"], "active")
                account = await store.account("111")
                self.assertEqual(
                    account["available"],
                    "0" if isinstance(results[1], Conflict) else "3000",
                )
                self.assertEqual(account["table"], "2000")
                with self.assertRaises(Conflict):
                    await store.command("folded-help", "subsidy", user_id="111")

    async def test_npc_supply_payout_and_valid_hand_rewards_are_auditable(self):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                await store.login("111")
                await store.command(
                    "buy", "buy_in", user_id="111", table_id="t", amount="2000"
                )
                await store.command(
                    "supply",
                    "npc_supply",
                    user_id="npc:one",
                    amount="10000",
                    actor="system",
                    reason="NPC initial stack",
                )
                for hand in range(10):
                    hid = "h" + str(hand)
                    await store.command(
                        "start" + hid,
                        "start_hand",
                        hand_id=hid,
                        table_id="t",
                        players=["111", "npc:one"],
                        snapshot={},
                    )
                    if hand == 0:
                        await store.command(
                            "clock",
                            "action",
                            hand_id=hid,
                            user_id="111",
                            opportunity_id="a",
                            now=100,
                        )
                        await store.command(
                            "bank",
                            "time_bank",
                            hand_id=hid,
                            user_id="111",
                            opportunity_id="a",
                            now=120,
                        )
                    await store.command(
                        "bet" + hid, "bet", hand_id=hid, user_id="npc:one", amount="100"
                    )
                    await store.command(
                        "settle" + hid,
                        "settle",
                        hand_id=hid,
                        payouts={"111": "100"},
                        opportunities={"111": {"dealt": True}},
                    )
                self.assertEqual((await store.account("111"))["settled"], "51000")
                self.assertEqual((await store.account("npc:one"))["settled"], "9000")
                self.assertEqual((await store.account("111"))["time_bank"], 60)
                self.assertEqual((await store.account("111"))["hand_progress"], 0)
                await store.command(
                    "reclaim",
                    "npc_reclaim",
                    user_id="npc:one",
                    amount="9000",
                    actor="system",
                    reason="NPC removal",
                )
                self.assertEqual((await store.account("npc:one"))["table"], "0")
                sources = {entry["source"] for entry in await store.ledger("npc:one")}
                self.assertTrue(
                    {"npc_supply", "npc_reclaim", "hand_settlement"} <= sources
                )

    async def test_partial_bet_and_settlement_overflow_roll_back_all_sides(self):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                for user in ("111", "222"):
                    await store.login(user)
                    await store.command(
                        "buy" + user,
                        "buy_in",
                        user_id=user,
                        table_id="t",
                        amount="2000",
                    )
                await store.command(
                    "ceiling",
                    "adjust",
                    user_id="222",
                    amount="8999999999950000",
                    actor="999",
                    reason="Overflow test",
                )
                await store.command(
                    "start",
                    "start_hand",
                    hand_id="h",
                    table_id="t",
                    players=["111", "222"],
                    snapshot={},
                )
                with self.assertRaises(Conflict):
                    await store.command(
                        "bad-bet", "bet", hand_id="h", user_id="111", amount="2001"
                    )
                await store.command(
                    "bet", "bet", hand_id="h", user_id="111", amount="100"
                )
                with self.assertRaises(Conflict):
                    await store.command(
                        "overflow", "settle", hand_id="h", payouts={"222": "100"}
                    )
                self.assertEqual((await store.account("111"))["in_flight"], "100")
                self.assertEqual((await store.account("111"))["settled"], "50000")
                self.assertEqual((await store.hand("h"))["status"], "active")
                await store.command("void", "void", hand_id="h")
                self.assertEqual((await store.account("111"))["table"], "2000")
