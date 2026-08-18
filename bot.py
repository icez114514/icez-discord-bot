import asyncio
import logging
import os

import discord
from discord import app_commands


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class TestBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def on_ready(self) -> None:
        if self.user is not None:
            logging.info("Logged in as %s (ID: %s)", self.user, self.user.id)


bot = TestBot()


@bot.tree.command(name="ping", description="Check whether the bot is online")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! {latency_ms} ms")


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set.")

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
