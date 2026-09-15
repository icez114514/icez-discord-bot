import asyncio
import tempfile
import unittest
from pathlib import Path

from poker.store import Store


class LedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_gift_is_once_across_concurrency_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'poker.db'
            async with Store(path, initialize=True) as store:
                await asyncio.gather(*(store.login('123456789012345678') for _ in range(8)))
                self.assertEqual((await store.account('123456789012345678'))['available'], '50000')
            async with Store(path) as store:
                await store.login('123456789012345678')
                self.assertEqual((await store.account('123456789012345678'))['settled'], '50000')
                self.assertEqual(len(await store.ledger('123456789012345678')), 1)
