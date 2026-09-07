import asyncio
import os
import re
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4
from psycopg import sql
from database import CrystalStore, Account, DatabaseError, read_database_url
from reward_store import RewardStore
from casino_store import CasinoStore
from runtime import configure_event_loop


@unittest.skipUnless(os.getenv('RUN_DB_TESTS')=='1','Set RUN_DB_TESTS=1')
class RewardDatabaseTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls): configure_event_loop()

    async def asyncSetUp(self):
        self.schema='reward_test_'+uuid4().hex
        self.store=CrystalStore(read_database_url(),schema=self.schema)
        self.addAsyncCleanup(self.store.close)
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addAsyncCleanup(self.drop)
        await self.store.initialize()
        self.reward=RewardStore(self.store)
        await self.reward.initialize()

    async def drop(self):
        assert re.fullmatch(r'reward_test_[0-9a-f]{32}',self.schema)
        async with self.store.connection() as conn:
            await conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    async def balances(self):
        async with self.store.connection(read_only=True) as conn:
            return await (await conn.execute(sql.SQL('SELECT user_id,balance,last_claim_date FROM {} ORDER BY user_id').format(self.store.table))).fetchall()

    async def grant(self,mid=100,recipients=None,mode='single'):
        return await self.reward.grant(mid,1,10,20,mode,100,recipients or {2:'two'})

    async def test_new_account_duplicate_distinct_and_schema(self):
        results=await asyncio.gather(self.grant(),self.grant())
        self.assertEqual(results[0],results[1])
        self.assertEqual(await self.balances(),[(2,100,None)])
        await self.grant(101)
        self.assertEqual(await self.balances(),[(2,200,None)])
        await self.reward.initialize(); await self.reward.check()
        async with self.store.connection(read_only=True) as conn:
            rows=await (await conn.execute(sql.SQL('SELECT amount,balance_before,balance_after FROM {} ORDER BY message_id').format(self.reward.entries))).fetchall()
        self.assertEqual(rows,[(100,0,100),(100,100,200)])

    async def test_batch_rollback_and_cancellation(self):
        await self.store.import_accounts([Account(2,10)],dry_run=False)
        with self.assertRaises(DatabaseError): await self.grant(recipients={2:'two',3:'missing'},mode='all')
        self.assertEqual(await self.balances(),[(2,10,None)])
        self.assertIsNone(await self.reward.find(100))
        original=self.store.connection
        @asynccontextmanager
        async def cancelled(**kwargs):
            async with original(**kwargs) as conn:
                yield conn
                raise asyncio.CancelledError()
        with patch.object(self.store,'connection',cancelled),self.assertRaises(asyncio.CancelledError):
            await self.grant()
        self.assertEqual(await self.balances(),[(2,10,None)])
        self.assertIsNone(await self.reward.find(100))
        await self.grant()
        self.assertEqual(await self.balances(),[(2,110,None)])

    async def test_after_commit_readback_and_batch_audit(self):
        await self.store.import_accounts([Account(2,10),Account(3,20)],dry_run=False)
        original=self.store.connection
        @asynccontextmanager
        async def uncertain(**kwargs):
            async with original(**kwargs) as conn: yield conn
            if not kwargs.get('read_only'): raise DatabaseError('injected after commit')
        with patch.object(self.store,'connection',uncertain):
            result=await self.grant(recipients={3:'three',2:'two'},mode='all')
        self.assertEqual(result.count,2)
        self.assertEqual(await self.balances(),[(2,110,None),(3,120,None)])
        await self.grant(recipients={2:'two',3:'three'},mode='all')
        self.assertEqual(await self.balances(),[(2,110,None),(3,120,None)])

    async def test_concurrent_claim_and_casino(self):
        await self.store.import_accounts([Account(2,1000)],dry_run=False)
        casino=CasinoStore(self.store); await casino.initialize()
        casino.roll=lambda:(6,6,6,1,2,3)
        panel=await casino.settings(2)
        await asyncio.gather(self.grant(),self.store.claim(2,'two',lambda:7),casino.start(2,panel.token))
        rows=await self.balances()
        self.assertEqual(int(rows[0][1]),1117)
        self.assertIsNotNone(rows[0][2])
