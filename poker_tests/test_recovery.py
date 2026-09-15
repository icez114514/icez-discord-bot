import asyncio
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from poker.store import Store, Conflict


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_kill_and_replay_preserve_all_money(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'poker.db'
            async with Store(path, initialize=True) as store:
                await store.login('111')
            script = """
import asyncio, sys
from pathlib import Path
from poker.store import Store
async def work():
    async with Store(Path(sys.argv[1])) as store:
        for n in range(300):
            await store.command('debit'+str(n), 'adjust', user_id='111', amount='-1', reason='Crash exercise', actor='999')
            print(n, flush=True)
asyncio.run(work())
"""
            process = subprocess.Popen([sys.executable, '-c', script, str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                for _ in range(10):
                    line = await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 10)
                    self.assertTrue(line, 'child exited before committing transactions')
                process.kill()
                await asyncio.to_thread(process.wait, 10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(10)
                process.stdout.close()
                process.stderr.close()
            async with Store(path) as store:
                for n in range(300):
                    await store.command('debit'+str(n), 'adjust', user_id='111', amount='-1', reason='Crash exercise', actor='999')
                self.assertEqual((await store.account('111'))['available'], '49700')
                self.assertEqual(len(await store.ledger('111')), 301)

    async def test_buyin_refund_and_taipei_boundary_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'poker.db'
            async with Store(path, initialize=True) as store:
                for user in ('111', '222'):
                    await store.login(user)
                    await store.command('buy'+user, 'buy_in', user_id=user, table_id='t', amount='2000')
                await store.command('start', 'start_hand', hand_id='h', table_id='t', players=['111','222'], snapshot={'phase':'preflop'})
                await store.command('bet', 'bet', hand_id='h', user_id='111', amount='100')
            async with Store(path) as store:
                self.assertEqual((await store.hand('h'))['status'], 'active')
                await store.command('refund', 'void', hand_id='h')
                await store.command('refund', 'void', hand_id='h')
                self.assertEqual((await store.account('111'))['table'], '2000')
                self.assertEqual((await store.account('111'))['hand_progress'], 0)
                with self.assertRaises(Conflict):
                    await store.command('settle-after-void', 'settle', hand_id='h', payouts={'111':'100'})
                await store.command('leave', 'leave', user_id='111')
                await store.command('debit', 'adjust', user_id='111', amount='-49000', reason='Boundary setup', actor='999')
                boundary = datetime(2026,9,15,20,0,tzinfo=timezone.utc).timestamp()
                await store.command('help-before', 'subsidy', user_id='111', now=boundary-1)
                await store.command('spend', 'adjust', user_id='111', amount='-1', reason='Boundary setup', actor='999')
                with self.assertRaises(Conflict):
                    await store.command('help-same', 'subsidy', user_id='111', now=boundary-0.5)
                await store.command('help-after', 'subsidy', user_id='111', now=boundary)
                self.assertEqual((await store.account('111'))['available'], '5000')