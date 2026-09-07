import argparse
import asyncio
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from reward_commands import RewardFeature
from reward_store import RewardStore
from casino_commands import CasinoFeature
from casino_store import CasinoStore
from crystal_commands import CrystalFeature
from database import CrystalStore, DatabaseError, read_database_url
from runtime import configure_event_loop
from latency import LoopMonitor, record_received, configure_timing_logging, operation, measure, mark_cold


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


class TestBot(discord.Client):
    def __init__(self, guild_id: int | None = None, store: CrystalStore | None = None) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        self.guild_id = guild_id
        self.rewards = RewardFeature(RewardStore(store) if store is not None else None)
        self.crystals = CrystalFeature(store)
        self.crystals.register(self.tree)
        self.casino = CasinoFeature(CasinoStore(store) if store is not None else None)
        self.casino.register(self.tree)
        self.loop_monitor = LoopMonitor()

    def dispatch(self, event, /, *args, **kwargs):
        if event == 'interaction' and args:
            record_received(args[0])
        super().dispatch(event, *args, **kwargs)

    async def on_message(self, message: discord.Message) -> None:
        await self.crystals.on_message(message)
        await self.rewards.on_message(message)

    async def setup_hook(self) -> None:
        self.loop_monitor.start()
        await self.casino.start_background()
        if self.guild_id is not None:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            commands = await self.tree.sync(guild=guild)
            logging.info("Synced %d command(s) to test server %s", len(commands), guild.id)
        else:
            commands = await self.tree.sync()
            logging.info("Synced %d global command(s)", len(commands))

    async def on_ready(self) -> None:
        if self.user is not None:
            logging.info("Logged in as %s (ID: %s)", self.user, self.user.id)

    async def close(self) -> None:
        await self.loop_monitor.close()
        await self.casino.stop_background()
        await super().close()

async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(interaction.client.latency * 1000)
    await interaction.response.send_message(f"Pong! {latency_ms} ms")


def read_config() -> tuple[str, int | None]:
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "paste-your-bot-token-here":
        raise ValueError("Set DISCORD_TOKEN in .env or the environment (see .env.example).")
    raw_guild = os.getenv("DISCORD_GUILD_ID", "").strip()
    if raw_guild and (
        not raw_guild.isascii() or not raw_guild.isdecimal()
        or not 0 < int(raw_guild) < 2**64
    ):
        raise ValueError("DISCORD_GUILD_ID must be a positive Discord server ID, or empty.")
    return token, int(raw_guild) if raw_guild else None


def create_bot(guild_id: int | None = None, store: CrystalStore | None = None) -> TestBot:
    bot = TestBot(guild_id, store)
    bot.tree.command(name="ping", description="Check whether the bot is online")(ping)
    return bot


@operation('bot.database_startup')
async def prepare_database(store):
    mark_cold()
    with measure('db_ms'):
        await store.open()
    await store.check()
    await CasinoStore(store).check()
    await RewardStore(store).check()


async def main(token: str, guild_id: int | None) -> None:
    store = CrystalStore(read_database_url())
    try:
        await prepare_database(store)
        bot = create_bot(guild_id, store)
        async with bot:
            await bot.start(token)
    finally:
        await store.close()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Discord crystal bot.")
    parser.add_argument(
        "--check", action="store_true",
        help="Validate local configuration without connecting to Discord or Neon.",
    )
    args = parser.parse_args()
    configure_event_loop()
    try:
        token, guild_id = read_config()
        if args.check:
            CrystalStore(read_database_url())
            scope = f"test server {guild_id}" if guild_id else "global"
            print(f"Local configuration OK; command sync: {scope}. Credentials and database schema have NOT been checked.")
        else:
            configure_timing_logging(Path(__file__).resolve().parent / 'logs')
            asyncio.run(main(token, guild_id))
    except (ValueError, DatabaseError) as exc:
        raise SystemExit(str(exc)) from None
    except discord.PrivilegedIntentsRequired:
        raise SystemExit("Enable Message Content Intent in the Discord Developer Portal, then restart.") from None
    except discord.LoginFailure:
        raise SystemExit("Discord login failed. Check DISCORD_TOKEN locally.") from None
    except discord.Forbidden:
        raise SystemExit("Discord denied access. Check the bot invitation and DISCORD_GUILD_ID.") from None
    except KeyboardInterrupt:
        logging.info("Bot stopped.")
