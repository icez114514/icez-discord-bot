import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot


class ConfigTests(unittest.TestCase):
    def config(self, values):
        with patch.dict(os.environ, values, clear=True), patch("bot.load_dotenv"):
            return bot.read_config()

    def test_missing_token(self):
        for token in ("", "   ", "paste-your-bot-token-here"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.config({"DISCORD_TOKEN": token})

    def test_global_and_guild(self):
        self.assertEqual(self.config({"DISCORD_TOKEN": " test "}), ("test", None))
        self.assertEqual(self.config({"DISCORD_TOKEN": "test", "DISCORD_GUILD_ID": " 123 "}), ("test", 123))

    def test_invalid_guild(self):
        for guild in ("0", "-1", "abc", "1.2", str(2**64)):
            with self.subTest(guild=guild), self.assertRaises(ValueError):
                self.config({"DISCORD_TOKEN": "test", "DISCORD_GUILD_ID": guild})

    def test_dotenv_location_and_environment_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "bot.py"
            script.with_name(".env").write_text("DISCORD_TOKEN=file-token\nDISCORD_GUILD_ID=123\n", encoding="utf-8")
            with patch("bot.__file__", str(script)), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(bot.read_config(), ("file-token", 123))
            with patch("bot.__file__", str(script)), patch.dict(os.environ, {"DISCORD_TOKEN": "env-token"}, clear=True):
                self.assertEqual(bot.read_config(), ("env-token", 123))


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_sync(self):
        client = bot.create_bot()
        async with client:
            with patch.object(client.tree, "sync", new_callable=AsyncMock, return_value=[]) as sync:
                await client.setup_hook()
                sync.assert_awaited_once_with()
                self.assertEqual(sorted(c.name for c in client.tree.get_commands()), ["ping", "水晶", "賭場"])

    async def test_guild_sync(self):
        client = bot.create_bot(123)
        async with client:
            with patch.object(client.tree, "sync", new_callable=AsyncMock, return_value=[]) as sync:
                await client.setup_hook()
                guild = sync.call_args.kwargs["guild"]
                self.assertEqual(guild.id, 123)
                self.assertEqual(sorted(c.name for c in client.tree.get_commands(guild=guild)), ["ping", "水晶", "賭場"])

    async def test_ping(self):
        send = AsyncMock()
        interaction = SimpleNamespace(client=SimpleNamespace(latency=0.123), response=SimpleNamespace(send_message=send))
        await bot.ping(interaction)
        send.assert_awaited_once_with("Pong! 123 ms")


if __name__ == "__main__":
    unittest.main()
