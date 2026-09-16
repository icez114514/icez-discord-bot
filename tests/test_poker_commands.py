import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord import app_commands
from poker_commands import PokerFeature, render_statistics


class PokerCommandTests(unittest.IsolatedAsyncioTestCase):
    def report(self):
        return {
            "as_of": "2026-09-16T12:00:00+08:00",
            "personal": {
                "hands": 1,
                "low_sample": True,
                "metrics": {
                    "vpip": {
                        "numerator": 0,
                        "denominator": 1,
                        "percent": "0.0%",
                        "low_sample": True,
                    }
                },
            },
            "leaderboard": [],
        }

    async def test_private_reply_has_no_target_or_public_delivery(self):
        client = SimpleNamespace(statistics=AsyncMock(return_value=self.report()))
        feature = PokerFeature(client, 456)
        interaction = SimpleNamespace(
            guild_id=456,
            user=SimpleNamespace(id=111),
            response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        await feature.respond(interaction, "statistics", "7", "mixed")
        client.statistics.assert_awaited_once_with(111, 456, "7", "mixed")
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        self.assertTrue(interaction.followup.send.call_args.kwargs["ephemeral"])
        self.assertIn(
            render_statistics(self.report()),
            interaction.followup.send.call_args.args[0],
        )
        interaction.guild_id = 999
        await feature.respond(interaction, "statistics")
        self.assertEqual(client.statistics.await_count, 1)
        self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])

    async def test_commands_registered_without_changing_crystal_group(self):
        bot = discord.Client(intents=discord.Intents.none())
        async with bot:
            tree = app_commands.CommandTree(bot)
            tree.add_command(app_commands.Group(name="水晶", description="Existing"))
            PokerFeature(None, 456).register(tree)
            group = tree.get_command("德撲")
            self.assertEqual({c.name for c in group.commands}, {"餘額", "榜單", "數據"})
            self.assertIsNotNone(tree.get_command("水晶"))
            for command in group.commands:
                self.assertNotIn("user_id", [p.name for p in command.parameters])
