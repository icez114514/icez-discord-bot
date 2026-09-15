import tempfile
import unittest
from pathlib import Path
import httpx
from poker.store import Store, Unauthorized
from poker.discord_api import Discord
from poker.eligibility import Eligibility
from poker.config import Config


class DurableScanTests(unittest.IsolatedAsyncioTestCase):
    async def test_presence_grace_and_skipped_day_survive_restart(self):
        class Missing:
            async def member(self, user):
                return "absent"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "poker.db"
            async with Store(path, initialize=True) as store:
                token = await store.login("111")
                await store.presence(token, "tab", "enter", now=100)
                await store.presence(token, "tab", "disconnect", now=110)
                await Eligibility(store, Missing()).run(now=229)
            async with Store(path) as store:
                await Eligibility(store, Missing()).run(now=500)
                self.assertEqual(await store.authenticate(token), "111")
                await Eligibility(store, Missing()).run(now=86500)
                with self.assertRaises(Unauthorized):
                    await store.authenticate(token)

    async def test_real_discord_adapter_failures_retain_existing_sessions(self):
        for status, code, guild_status in (
            (401, 0, 200),
            (403, 0, 200),
            (429, 0, 200),
            (500, 0, 200),
            (404, 10004, 200),
            (404, 10007, 403),
            (0, 0, 200),
        ):
            with (
                self.subTest(status=status, code=code),
                tempfile.TemporaryDirectory() as directory,
            ):
                config = Config(
                    data_dir=Path(directory), guild_id="456", bot_token="fake"
                )

                def transport(request):
                    if status == 0:
                        raise httpx.ReadTimeout("simulated timeout", request=request)
                    if "/members/" in request.url.path:
                        return httpx.Response(status, json={"code": code})
                    return httpx.Response(guild_status, json={})

                async with (
                    Store(Path(directory) / "poker.db", initialize=True) as store,
                    httpx.AsyncClient(
                        transport=httpx.MockTransport(transport)
                    ) as client,
                ):
                    token = await store.login("111")
                    await Eligibility(store, Discord(config, client)).run(now=100)
                    self.assertEqual(await store.authenticate(token), "111")

    async def test_second_store_refused_until_owner_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "poker.db"
            async with Store(path, initialize=True):
                with self.assertRaisesRegex(RuntimeError, "already_running"):
                    async with Store(path):
                        self.fail("Second owner opened database")
            async with Store(path) as store:
                await store.login("111")
                self.assertEqual((await store.account("111"))["available"], "50000")
