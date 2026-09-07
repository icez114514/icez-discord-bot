import asyncio
import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import discord
from casino_commands import CasinoFeature, LobbyView
from test_casino_ui import interaction

class RuntimeLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_ack_stops_before_database_or_followup(self):
        for button in (False, True):
            event = interaction()
            event.response.defer.side_effect = discord.NotFound(
                SimpleNamespace(status=404, reason='Not Found'), {'code': 10062, 'message': 'Unknown interaction'})
            store = AsyncMock()
            feature = CasinoFeature(store)
            with self.assertLogs(level='WARNING'):
                if button:
                    await feature.act(event, LobbyView(feature, 123), 'settings')
                else:
                    await feature.slash(event)
            self.assertEqual(store.mock_calls, [])
            event.followup.send.assert_not_awaited()
            event.response.defer.assert_awaited_once()

    async def test_timing_goes_to_rotating_file_not_console(self):
        from latency import configure_timing_logging, timing_logger, operation
        with tempfile.TemporaryDirectory() as directory:
            handler = configure_timing_logging(Path(directory))
            try:
                @operation('test')
                async def sample():
                    await asyncio.sleep(0)
                with self.assertNoLogs(logging.getLogger(), level='INFO'):
                    await sample()
                handler.flush()
                self.assertIn('Operation timing', (Path(directory)/'latency.log').read_text(encoding='utf-8'))
                self.assertGreater(handler.maxBytes, 0)
                self.assertEqual(handler.backupCount, 3)
            finally:
                timing_logger.removeHandler(handler)
                handler.close()
