import asyncio
import copy
import random
import time
import unittest

from poker.npc_timing import think_seconds
from poker.table_api import run_tables


class ThinkingTests(unittest.TestCase):
    def test_harder_public_decisions_shift_delays_within_one_to_five_seconds(self):
        easy = {"actor": 0, "street": "preflop", "current_bet": 100,
                "players": [{"id": "npc:1", "bet": 100, "paid": 100, "folded": False},
                            {"id": "u", "bet": 100, "paid": 100, "folded": False}]}
        hard = copy.deepcopy(easy)
        hard.update(street="river", current_bet=1000)
        a, b = random.Random(42), random.Random(42)
        quick = [think_seconds(easy, a) for _ in range(500)]
        slow = [think_seconds(hard, b) for _ in range(500)]
        self.assertTrue(all(1 <= n <= 5 for n in quick + slow))
        self.assertGreater(sum(slow) / len(slow), sum(quick) / len(quick) + 0.5)
        self.assertGreater(len(set(quick)), 490)
        # Private strength must not turn timing into a deterministic tell.
        hard["players"][0]["cards"] = ["Ac", "Ad"]
        first = think_seconds(hard, random.Random(8))
        hard["players"][0]["cards"] = ["2c", "7d"]
        self.assertEqual(first, think_seconds(hard, random.Random(8)))


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_tables_think_concurrently_and_each_turn_applies_once(self):
        start = time.time()
        completed, calls = {}, []
        class Tables:
            async def tick(self, exclude_npcs=()):
                for name, delay in (("slow", 1.5), ("fast", 1.0)):
                    if name not in completed and (name, 1) not in exclude_npcs:
                        return {"id": name, "turn": 1, "deadline": start + 5,
                                "npc_not_before": start + delay}
            async def npc_result(self, name, turn, result, error):
                self_test.assertNotIn(name, completed)
                completed[name] = time.time() - start
        class NPC:
            async def decide(self, hand):
                calls.append(hand["id"])
                return {"action": "check"}, None
        self_test = self
        task = asyncio.create_task(run_tables(Tables(), NPC()))
        try:
            async def wait_complete():
                while len(completed) < 2:
                    await asyncio.sleep(0.02)
            await asyncio.wait_for(wait_complete(), timeout=4)
            self.assertEqual(calls, ["slow", "fast"])
            self.assertEqual(list(completed), ["fast", "slow"])
            self.assertTrue(all(1 <= n < 5 for n in completed.values()), completed)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
