"""Discord poker queries use only the authenticated loopback service."""

import os

import discord
from discord import app_commands
import httpx

from poker.bot_client import PokerClient

LABELS = {
    "net_win": "淨贏牌率",
    "vpip": "VPIP",
    "pfr": "PFR",
    "three_bet": "3-Bet",
    "fold_three_bet": "Fold to 3-Bet",
    "cbet": "Flop C-Bet",
    "wsd": "攤牌分池率",
}
PERIODS = [
    app_commands.Choice(name=n, value=v)
    for n, v in (("累計", "all"), ("近 30 天", "30"), ("近 7 天", "7"))
]
OPPONENTS = [
    app_commands.Choice(name=n, value=v)
    for n, v in (("全部", "all"), ("純真人", "human"), ("含 NPC", "mixed"))
]


def metric_text(metric):
    return f"{metric['numerator']}/{metric['denominator']} · {metric['percent']}" + (
        " · 樣本不足" if metric["low_sample"] else ""
    )


def render_statistics(data):
    personal = data["personal"]
    lines = [
        f"有效手數：{personal['hands']}"
        + (" · 樣本不足" if personal["low_sample"] else "")
    ]
    lines.extend(
        f"{LABELS[key]}：{metric_text(value)}"
        for key, value in personal["metrics"].items()
    )
    lines.append(f"截至 {data['as_of']}（Asia/Taipei）")
    return "\n".join(lines)


class PokerFeature:
    def __init__(self, client, guild_id):
        self.client, self.guild_id = client, int(guild_id)

    @classmethod
    def from_env(cls):
        token, guild = os.getenv("POKER_READER_TOKEN"), os.getenv("POKER_GUILD_ID")
        if not token or not guild:
            return None
        return cls(
            PokerClient(token, "", int(os.getenv("POKER_INTERNAL_PORT", "8766"))), guild
        )

    async def respond(self, interaction, kind, period="all", opponents="all"):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "請在指定社群伺服器使用德撲查詢。", ephemeral=True
            )
            return
        # Every private result is ephemeral; no target-user argument is accepted.
        await interaction.response.defer(ephemeral=True)
        try:
            data = await self.client.statistics(
                interaction.user.id, self.guild_id, period, opponents
            )
            if kind == "statistics":
                message = render_statistics(data)
            elif kind == "balance":
                row = next(
                    r
                    for r in data["leaderboard"]
                    if r["user_id"] == str(interaction.user.id)
                )
                message = f"已結算總資產：{int(row['settled']):,} 德撲籌碼\n有效手數：{row['hands']}\n淨贏牌率：{metric_text(row['metrics']['net_win'])}"
            else:
                lines = ["已結算總資產榜 · 德撲籌碼"]
                for row in data["leaderboard"]:
                    lines.append(
                        f"#{row['rank']} · {row['user_id']} · {int(row['settled']):,}\n{row['hands']} 手 · {metric_text(row['metrics']['net_win'])}"
                    )
                message = "\n".join(lines)
            # Bounded chunks retain every rank without exceeding Discord's limit.
            chunk = ""
            for line in message.splitlines():
                if len(chunk) + len(line) + 1 > 1900:
                    await interaction.followup.send(
                        chunk,
                        ephemeral=True,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    chunk = ""
                chunk += line + "\n"
            if chunk:
                await interaction.followup.send(
                    chunk,
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (httpx.HTTPError, KeyError, StopIteration):
            await interaction.followup.send(
                "暫時無法查詢德撲資料，請確認已建立德撲帳戶後再試。", ephemeral=True
            )

    def register(self, tree):
        group = app_commands.Group(name="德撲", description="查詢獨立德撲籌碼與戰績")

        @group.command(name="餘額", description="查看已結算德撲總資產")
        async def balance(interaction: discord.Interaction):
            await self.respond(interaction, "balance")

        @group.command(name="榜單", description="真人已結算總資產榜")
        @app_commands.choices(period=PERIODS, opponents=OPPONENTS)
        async def ranking(
            interaction: discord.Interaction,
            period: str = "all",
            opponents: str = "all",
        ):
            await self.respond(interaction, "ranking", period, opponents)

        @group.command(name="數據", description="僅本人可見的打法統計")
        @app_commands.choices(period=PERIODS, opponents=OPPONENTS)
        async def statistics(
            interaction: discord.Interaction,
            period: str = "all",
            opponents: str = "all",
        ):
            await self.respond(interaction, "statistics", period, opponents)

        tree.add_command(group)
