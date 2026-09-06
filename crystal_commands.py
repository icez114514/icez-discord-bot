"""Discord adapters for the shared crystal account operation."""

import logging

import discord
from discord import app_commands

from latency import discord_update, mark_status, operation
from crystal_rules import DOUBLE_ROLE_ID, daily_reward, is_crystal_message, level_for_roles
from database import Account, ClaimResult, CrystalStore, DatabaseError, DatabaseBusy

COLOR = 0xDC9FB4
THUMBNAIL = "https://i.imgur.com/tvAkopu.png"
DATABASE_UNAVAILABLE = "水晶資料庫暫時無法使用，請稍後重試；若剛才已成功領取，重試只會顯示餘額。"
DATABASE_BUSY = "水晶資料庫目前忙碌，請稍後再試。"
SERVER_ONLY = "請在伺服器中使用水晶功能。"


def safe_name(name: str | None, user_id: int) -> str:
    value = (name or str(user_id)).strip() or str(user_id)
    return discord.utils.escape_markdown(discord.utils.escape_mentions(value))[:256]


def balance_embed(result: ClaimResult, display_name: str, user_id: int) -> discord.Embed:
    embed = discord.Embed(color=COLOR)
    if result.reward is not None:
        embed.add_field(name="每日水晶", value=f"你獲得了 **{result.reward}** 顆水晶")
    embed.add_field(name=safe_name(display_name, user_id), value=f"水晶數量： **{result.balance}**")
    embed.set_thumbnail(url=THUMBNAIL)
    return embed


def ranking_embed(accounts: list[Account]) -> discord.Embed:
    embed = discord.Embed(title="水晶排行榜", color=COLOR)
    if not accounts:
        embed.description = "目前尚無水晶帳戶。"
    for index, account in enumerate(accounts[:5], 1):
        embed.add_field(
            name=f"#{index}",
            value=f"{safe_name(account.display_name, account.user_id)}   水晶資產： {account.balance}",
            inline=False,
        )
    embed.set_thumbnail(url=THUMBNAIL)
    return embed


class CrystalFeature:
    def __init__(self, store: CrystalStore | None) -> None:
        self.store = store

    async def render(self, member: discord.Member, action: str) -> discord.Embed:
        if self.store is None:
            raise DatabaseError("Crystal storage is not configured.")
        if action == "rank":
            return ranking_embed(await self.store.leaderboard())
        if action != "daily":
            raise ValueError("Unknown crystal action.")
        level = level_for_roles(role.name for role in member.roles)
        doubled = any(role.id == DOUBLE_ROLE_ID for role in member.roles)
        result = await self.store.claim(
            member.id, member.display_name, lambda: daily_reward(level, doubled)
        )
        return balance_embed(result, member.display_name, member.id)

    def register(self, tree: app_commands.CommandTree) -> None:
        @tree.command(name="水晶", description="每日簽到、查詢水晶或查看排行榜")
        @app_commands.guild_only()
        @app_commands.rename(action="操作")
        @app_commands.describe(action="未選擇時執行簽到／查詢")
        @app_commands.choices(action=[
            app_commands.Choice(name="簽到／查詢", value="daily"),
            app_commands.Choice(name="排行榜", value="rank"),
        ])
        async def crystal(interaction: discord.Interaction, action: str = "daily") -> None:
            await self.slash(interaction, action)

    @operation("crystal.slash")
    async def slash(self, interaction: discord.Interaction, action: str = "daily") -> None:
        if interaction.guild is None or interaction.user.bot:
            await discord_update(interaction.response.send_message(SERVER_ONLY, ephemeral=True))
            return
        await discord_update(interaction.response.defer(thinking=True))
        try:
            embed = await self.render(interaction.user, action)
        except DatabaseError as error:
            mark_status("busy" if isinstance(error, DatabaseBusy) else "database_error")
            logging.warning("Crystal database operation failed; details suppressed.")
            await discord_update(interaction.edit_original_response(content=DATABASE_BUSY if isinstance(error, DatabaseBusy) else DATABASE_UNAVAILABLE))
            return
        await discord_update(interaction.edit_original_response(embed=embed, allowed_mentions=discord.AllowedMentions.none()))

    async def on_message(self, message: discord.Message) -> None:
        if (message.guild is None or message.author.bot or message.webhook_id is not None
                or not is_crystal_message(message.content)):
            return
        await self._respond_message(message)

    @operation("crystal.message")
    async def _respond_message(self, message: discord.Message) -> None:
        try:
            try:
                embed = await self.render(message.author, "daily")
            except DatabaseError as error:
                mark_status("busy" if isinstance(error, DatabaseBusy) else "database_error")
                logging.warning("Crystal database operation failed; details suppressed.")
                await discord_update(message.channel.send(DATABASE_BUSY if isinstance(error, DatabaseBusy) else DATABASE_UNAVAILABLE, allowed_mentions=discord.AllowedMentions.none()))
                return
            await discord_update(message.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none()))
        except discord.HTTPException:
            mark_status("delivery_error")
            logging.warning("Crystal response delivery failed; no reward retry was attempted.")
