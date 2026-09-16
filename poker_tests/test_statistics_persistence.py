import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from poker import rules
from poker.management import Management
from poker.statistics import query
from poker.store import Store, Conflict


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_classification_void_replay_rebuild_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "poker.db"
            async with Store(path, initialize=True) as store:
                token = await store.login("111")
                await store.login("222")
                await store.command(
                    "buy", "buy_in", user_id="111", table_id="t", amount="2000"
                )
                await store.command(
                    "npc",
                    "npc_supply",
                    user_id="npc:1",
                    amount="2000",
                    actor="system",
                    reason="test",
                )
                hand = rules.create([("111", 2000), ("npc:1", 2000)], 0, "mixed")
                await store.command(
                    "start",
                    "start_hand",
                    hand_id="mixed",
                    table_id="t",
                    players=["111", "npc:1"],
                    snapshot=hand,
                )
                rules.act(hand, "111", "raise", 300)
                rules.act(hand, "npc:1", "fold")
                hand["settled_at"] = 1000
                for p in hand["players"]:
                    await store.command(
                        "bet" + p["id"],
                        "bet",
                        hand_id="mixed",
                        user_id=p["id"],
                        amount=str(p["paid"]),
                    )
                payload = dict(
                    hand_id="mixed",
                    snapshot=hand,
                    payouts={u: str(n) for u, n in hand["payouts"].items()},
                )
                first = await store.command("settle", "settle", **payload)
                self.assertEqual(
                    await store.command("settle", "settle", **payload), first
                )
                report = await store.run(lambda db: query(db, "111", now=1001))
                self.assertEqual(report["personal"]["hands"], 1)
                self.assertEqual(report["personal"]["metrics"]["vpip"]["numerator"], 1)
                mixed = await store.run(
                    lambda db: query(db, "111", opponents="mixed", now=1001)
                )
                human = await store.run(
                    lambda db: query(db, "111", opponents="human", now=1001)
                )
                self.assertEqual(mixed["personal"]["hands"], 1)
                self.assertEqual(human["personal"]["hands"], 0)
                self.assertEqual(len(report["leaderboard"]), 2)
                self.assertEqual((await store.account("111"))["settled"], "50100")
                # A dealt but void hand must leave both counters and time bank alone.
                void_hand = rules.create([("111", 2100), ("npc:1", 1900)], 0, "void")
                await store.command(
                    "void-start",
                    "start_hand",
                    hand_id="void",
                    table_id="t",
                    players=["111", "npc:1"],
                    snapshot=void_hand,
                )
                await store.command("void", "void", hand_id="void", snapshot=void_hand)
                self.assertEqual((await store.account("111"))["hand_progress"], 1)
                management = Management(
                    store, SimpleNamespace(table_admins=("111",), funds_admins=())
                )
                # Inject a corrupt derived projection, then repair via authorized API.
                await store.run(
                    lambda db: db.execute(
                        "DELETE FROM hand_statistics WHERE hand_id='mixed'"
                    )
                )
                await store.run(
                    lambda db: db.execute(
                        "UPDATE accounts SET hand_progress=8,time_bank=15 WHERE user_id='111'"
                    )
                )
                command = dict(
                    command_id="repair",
                    action="rebuild",
                    target="mixed",
                    reason="Repair derived projection",
                )
                result = await management.command(command, token=token)
                self.assertEqual(await management.command(command, token=token), result)
                self.assertEqual(
                    await store.run(lambda db: query(db, "111", now=1001)), report
                )
                self.assertEqual((await store.account("111"))["hand_progress"], 1)
                self.assertEqual((await store.account("111"))["time_bank"], 60)
                await management.command(
                    dict(command, command_id="void-repair", target="void"), token=token
                )
                self.assertEqual((await store.account("111"))["hand_progress"], 1)
            async with Store(path) as store:
                self.assertEqual(
                    await store.run(lambda db: query(db, "111", now=1001)), report
                )
                self.assertEqual(
                    await store.command("settle", "settle", **payload), first
                )

    async def test_schema_three_upgrade_backfills_completed_snapshots_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "poker.db"
            db = sqlite3.connect(path)
            for name in ("schema.sql", "game-schema.sql", "preferences-schema.sql"):
                db.executescript((Path("poker") / name).read_text(encoding="utf-8"))
            for user in ("111", "222"):
                db.execute(
                    "INSERT INTO accounts(user_id,available,settled) VALUES(?,50000,50000)",
                    (user,),
                )
            hand = rules.create([("111", 2000), ("222", 2000)], 0, "old")
            rules.act(hand, "111", "fold")
            hand["settled_at"] = 100
            db.execute(
                "INSERT INTO hands(hand_id,table_id,status,snapshot) VALUES('old','t','settled',?)",
                (json.dumps(hand),),
            )
            db.commit()
            db.close()
            with self.assertRaisesRegex(Conflict, "requires_migrate"):
                async with Store(path):
                    pass
            async with Store(path, initialize=True) as store:
                report = await store.run(lambda db: query(db, "111", now=101))
                self.assertEqual(report["personal"]["hands"], 1)
                self.assertEqual(
                    report["personal"]["metrics"]["net_win"]["numerator"], 0
                )
            async with Store(path, initialize=True) as store:
                self.assertEqual(
                    await store.run(lambda db: query(db, "111", now=101)), report
                )

    async def test_rebuild_replays_ten_hand_award_and_later_bank_debit(self):
        with tempfile.TemporaryDirectory() as directory:
            async with Store(Path(directory) / "poker.db", initialize=True) as store:
                token = await store.login("111")
                await store.command(
                    "buy", "buy_in", user_id="111", table_id="t", amount="10000"
                )
                await store.command(
                    "npc",
                    "npc_supply",
                    user_id="npc:1",
                    amount="10000",
                    actor="system",
                    reason="test",
                )
                for index in range(11):
                    hid = f"h{index}"
                    human = int((await store.account("111"))["table"])
                    npc = int((await store.account("npc:1"))["table"])
                    hand = rules.create([("111", human), ("npc:1", npc)], 0, hid)
                    await store.command(
                        "start" + hid,
                        "start_hand",
                        hand_id=hid,
                        table_id="t",
                        players=["111", "npc:1"],
                        snapshot=hand,
                    )
                    if index in (0, 10):
                        await store.command(
                            "clock" + hid,
                            "action",
                            hand_id=hid,
                            user_id="111",
                            opportunity_id="one",
                            now=index * 100,
                        )
                        await store.command(
                            "bank" + hid,
                            "time_bank",
                            hand_id=hid,
                            user_id="111",
                            opportunity_id="one",
                            now=index * 100 + 20,
                        )
                    rules.act(hand, "111", "fold", automatic=True)
                    hand["settled_at"] = index * 100 + 21
                    for player in hand["players"]:
                        await store.command(
                            "bet" + hid + player["id"],
                            "bet",
                            hand_id=hid,
                            user_id=player["id"],
                            amount=str(player["paid"]),
                        )
                    await store.command(
                        "settle" + hid,
                        "settle",
                        hand_id=hid,
                        snapshot=hand,
                        payouts={u: str(n) for u, n in hand["payouts"].items()},
                    )
                before = await store.account("111")
                self.assertEqual(
                    (before["time_bank"], before["hand_progress"]), (55, 1)
                )
                management = Management(
                    store, SimpleNamespace(table_admins=("111",), funds_admins=())
                )
                await management.command(
                    dict(
                        command_id="rebuild",
                        action="rebuild",
                        target="h0",
                        reason="Verify award replay",
                    ),
                    token=token,
                )
                self.assertEqual(await store.account("111"), before)
