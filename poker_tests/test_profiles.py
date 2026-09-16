import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
from fastapi.testclient import TestClient

from poker.app import create_app
from poker.config import Config
from poker.profiles import Profiles, presentation

A = "111111111111111111"
B = "222222222222222222"
HASH = "a" * 32


def member(**extra):
    return {"nick": "Table nickname", "user": {"id": A, "username": "account_name", "avatar": HASH}, **extra}


class PresentationTests(unittest.TestCase):
    def test_nickname_and_guild_avatar_win(self):
        data = presentation(A, "456", member(avatar="b" * 32))
        self.assertEqual(data["display_name"], "Table nickname")
        self.assertIn(f"guilds/456/users/{A}/avatars/", data["avatar_url"])
        self.assertEqual(set(data), {"id", "display_name", "avatar_url"})

    def test_username_global_avatar_and_default_fallbacks(self):
        data = presentation(A, "456", member(nick=None))
        self.assertEqual(data["display_name"], "account_name")
        self.assertIn(f"/avatars/{A}/", data["avatar_url"])
        data = presentation(A, "456", {"user": {"id": A, "username": "name", "avatar": None}})
        self.assertIn("/embed/avatars/", data["avatar_url"])

    def test_invalid_identity_and_missing_username_are_not_cached(self):
        self.assertIsNone(presentation(B, "456", member()))
        self.assertIsNone(presentation(A, "456", {}))
        self.assertIsNone(presentation(A, "456", {"user": {"id": A}}))

    def test_long_names_and_untrusted_avatar_values(self):
        data = presentation(A, "456", member(nick="x" * 1000, avatar="https://evil.example/x"))
        self.assertEqual(len(data["display_name"]), 80)
        self.assertTrue(data["avatar_url"].startswith("https://cdn.discordapp.com/avatars/"))


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0
        self.discord = SimpleNamespace(lock=asyncio.Lock(), config=SimpleNamespace(guild_id="456", bot_token="test-only"), request=AsyncMock(return_value=httpx.Response(200, json=member())))
        self.cache = Profiles(self.discord, clock=lambda: self.now)
        self.addAsyncCleanup(self.cache.close)

    async def flush(self):
        await asyncio.gather(*list(self.cache.tasks.values()))

    async def test_first_read_is_nonblocking_and_concurrent_reads_coalesce(self):
        gate = asyncio.Event()
        async def slow(*args, **kwargs):
            await gate.wait()
            return httpx.Response(200, json=member())
        self.discord.request.side_effect = slow
        self.assertEqual(self.cache.view([A]), [])
        self.assertEqual(self.cache.view([A]), [])
        self.assertEqual(len(self.cache.tasks), 1)
        gate.set()
        await self.flush()
        self.assertEqual(self.discord.request.await_count, 1)
        self.assertEqual(self.cache.view([A])[0]["display_name"], "Table nickname")

    async def test_five_minute_ttl_and_failure_keeps_stale_profile(self):
        self.cache.view([A]); await self.flush()
        self.now = 299
        self.cache.view([A]); self.assertFalse(self.cache.tasks)
        self.now = 300
        self.discord.request.return_value = httpx.Response(429, json={"retry_after": 60})
        self.assertEqual(len(self.cache.view([A])), 1)
        await self.flush()
        self.now = 359
        self.assertEqual(len(self.cache.view([A])), 1)
        self.assertFalse(self.cache.tasks)
        self.now = 360
        self.discord.request.return_value = httpx.Response(200, json=member(nick="Changed"))
        self.cache.view([A]); await self.flush()
        self.assertEqual(self.cache.view([A])[0]["display_name"], "Changed")

    async def test_first_failure_and_malformed_reply_retry_without_crashing(self):
        for response in (None, httpx.Response(500), httpx.Response(200, json=[])):
            self.discord.request.return_value = response
            self.assertEqual(self.cache.view([A]), [])
            await self.flush()
            self.assertFalse(self.cache.tasks)
            self.now += 61

    async def test_busy_authentication_boundary_defers_cosmetic_work(self):
        async with self.discord.lock:
            self.cache.view([A]); await self.flush()
            self.discord.request.assert_not_awaited()
        self.now = 2
        self.cache.view([A]); await self.flush()
        self.assertEqual(self.discord.request.await_args.kwargs["timeout"], 2)
        self.assertEqual(len(self.cache.view([A])), 1)

    async def test_shutdown_cancels_inflight_profile_work(self):
        self.discord.request.side_effect = lambda *a, **kw: None
        gate = asyncio.Event()
        async def slow(*a, **kw):
            await gate.wait()
        self.discord.request.side_effect = slow
        self.cache.view([A]); await asyncio.sleep(0)
        await self.cache.close()
        self.assertFalse(self.cache.tasks)


class ProfileEndpointTests(unittest.TestCase):
    def test_only_current_table_players_and_authenticated_session(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(data_dir=Path(directory), environment="test", origin="http://testserver", client_id="123", guild_id="456", client_secret="s" * 32, bot_token="b" * 32, reader_token="r" * 32, funds_token="f" * 32)
            app = create_app(config, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})), initialize=True)
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/table/profiles").status_code, 401)
                token = client.portal.call(app.state.store.login, A)
                client.cookies.set("poker_session", token)
                response = client.post("/api/tables", headers={"origin": config.origin}, json={"command_id": "create", "name": "profiles", "private": True, "amount": "2000"})
                self.assertEqual(response.status_code, 200)
                app.state.profiles.view = Mock(return_value=[presentation(A, "456", member())])
                response = client.get("/api/table/profiles?user_id=" + B)
                self.assertEqual(response.status_code, 200)
                app.state.profiles.view.assert_called_once_with([A])
                self.assertEqual(response.json()["profiles"][0]["id"], A)
                self.assertIn("img-src 'self' https://cdn.discordapp.com", response.headers["content-security-policy"])
                other = client.portal.call(app.state.store.login, B)
                client.cookies.set("poker_session", other)
                app.state.profiles.view.reset_mock()
                client.get("/api/table/profiles")
                app.state.profiles.view.assert_called_once_with([])
