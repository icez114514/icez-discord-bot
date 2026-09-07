import asyncio
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from casino_commands import CasinoFeature, RecordsView
from casino_records import Page
from test_casino_ui import interaction

class ResponseOptimizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_audit_acknowledges_before_http_and_checks_twice(self):
        feature = CasinoFeature(object())
        event = interaction()
        view = RecordsView(feature,123,audit=True,has_next=True)
        checks=[]
        async def authorized(i):
            self.assertTrue(i.response.defer.called)
            checks.append(True)
            return True
        feature.is_auditor=AsyncMock(side_effect=authorized)
        with patch('casino_commands.CasinoRecords') as records:
            records.return_value.summary=AsyncMock(return_value=Page((),False))
            self.assertTrue(await view.interaction_check(event))
            await feature.act(event,view,'next')
        self.assertEqual(len(checks),2)
        event.edit_original_response.assert_awaited_once()

    async def test_arrival_and_ack_have_separate_timings(self):
        from latency import record_received
        event=interaction()
        event.extras={}
        event.created_at=datetime.now(timezone.utc)-timedelta(seconds=4)
        record_received(event)
        await asyncio.sleep(.01)
        feature=CasinoFeature(None)
        feature._slash=AsyncMock()
        with self.assertLogs('bot.timing',level='INFO') as logs:
            await feature.slash(event)
        text=' '.join(logs.output)
        for field in ('interaction_age_ms=', 'dispatch_wait_ms=', 'ack_http_ms=', 'ack_start_age_ms=', 'ack_complete_age_ms='):
            self.assertIn(field,text)
        self.assertNotIn('user_id',text)

    async def test_monitor_detects_event_loop_stall_and_stops(self):
        from latency import LoopMonitor
        monitor=LoopMonitor(interval=.01)
        monitor.start()
        await asyncio.sleep(.02)
        time.sleep(.05)
        await asyncio.sleep(.02)
        self.assertGreater(monitor.max_lag_ms,25)
        await monitor.close()
        self.assertTrue(monitor.task.done())
