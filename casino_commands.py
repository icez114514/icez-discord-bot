"""Public casino panels; durable money and operation tokens live in CasinoStore."""

import asyncio
import io
import logging
import os
from functools import lru_cache
from pathlib import Path

import discord
from discord import app_commands

from casino_rules import CasinoError, parse_integer
from casino_store import CasinoStore, Game, Preferences
from database import DatabaseError

COLOR = 0xDC9FB4
UNAVAILABLE = "賭場資料庫暫時無法確認操作結果，請重新使用 /賭場 查證；請勿假定未扣款。"
OWNER_ONLY = "這是其他玩家的面板，請使用 /賭場 開啟自己的大廳。"


def money(value: int) -> str:
    text = str(value)
    # Discord has field limits; storage and arithmetic always keep the exact integer.
    return text if len(text) <= 180 else f"{text[:80]}…{text[-40:]}（共 {len(text)} 位，顯示省略）"


@lru_cache(maxsize=4)
def dealer_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


class OwnedView(discord.ui.View):
    def __init__(self, feature, owner_id):
        super().__init__(timeout=600)
        self.feature = feature
        self.owner_id = owner_id
        self.lock = asyncio.Lock()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(OWNER_ONLY, ephemeral=True)
            return False
        return True

    def button(self, label, action, *, style=discord.ButtonStyle.secondary, row=0, disabled=False):
        self.add_item(ActionButton(self, action, label=label, style=style, row=row, disabled=disabled))


class ActionButton(discord.ui.Button):
    def __init__(self, panel, action, **kwargs):
        super().__init__(**kwargs)
        self.panel = panel
        self.action = action

    async def callback(self, interaction):
        await self.panel.feature.act(interaction, self.panel, self.action)


class LobbyView(OwnedView):
    def __init__(self, feature, owner_id):
        super().__init__(feature, owner_id)
        self.button("21 點（尚未開放）", "blackjack", disabled=True)
        self.button("18 豆仔", "settings", style=discord.ButtonStyle.primary)


class SettingsView(OwnedView):
    def __init__(self, feature, owner_id, prefs: Preferences):
        super().__init__(feature, owner_id)
        self.prefs = prefs
        for amount in (10, 50, 100, 500):
            self.button(str(amount), f"base:{amount}", row=0)
        self.button("自訂下注", "custom:base", row=0)
        for multiplier in (1, 2, 5, 10):
            self.button(f"×{multiplier}", f"multiplier:{multiplier}", row=1)
        self.button("自訂倍率", "custom:multiplier", row=1)
        self.button("開局", "start", style=discord.ButtonStyle.success, row=2)
        self.button("返回大廳", "lobby", row=2)


class ResultView(OwnedView):
    def __init__(self, feature, owner_id, game: Game):
        super().__init__(feature, owner_id)
        self.game = game
        self.button("再來一局", "replay", style=discord.ButtonStyle.success)
        self.button("修改下注", "settings", style=discord.ButtonStyle.primary)
        self.button("返回大廳", "lobby")


class BetModal(discord.ui.Modal):
    def __init__(self, view: SettingsView, field: str):
        super().__init__(title="自訂下注" if field == "base" else "自訂倍率")
        self.panel = view
        self.field = field
        previous = view.prefs.custom_base if field == "base" else view.prefs.custom_multiplier
        # Discord caps modal inputs at 4000 characters, independently of storage.
        self.amount: discord.ui.TextInput = discord.ui.TextInput(label="偶數基本下注（至少 2）" if field == "base" else "正整數倍率",
                                           default=None if previous is None else str(previous)[:4000],
                                           max_length=4000)
        self.add_item(self.amount)

    async def on_submit(self, interaction):
        await self.panel.feature.act(interaction, self.panel, f"submit:{self.field}", self.amount.value)


class CasinoFeature:
    def __init__(self, store: CasinoStore | None):
        self.store = store
        self.dealer_path = os.getenv("CASINO_DEALER_IMAGE") or str(Path(__file__).with_name("Mei") / "Mei (1).jpg")

    def register(self, tree: app_commands.CommandTree):
        @tree.command(name="賭場", description="開啟水晶賭場或恢復上次牌局")
        @app_commands.guild_only()
        async def casino(interaction: discord.Interaction):
            await self.slash(interaction)

    def storage(self) -> CasinoStore:
        if self.store is None:
            raise DatabaseError("Casino storage is not configured")
        return self.store

    async def slash(self, interaction):
        if interaction.guild is None or interaction.user.bot:
            await interaction.response.send_message("請在伺服器中使用賭場。", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            game = await self.storage().recover(interaction.user.id)
            if game is not None:
                await self.show_result(interaction, game)
            else:
                await self.show_lobby(interaction)
        except (CasinoError, DatabaseError) as error:
            await interaction.edit_original_response(content=str(error) if isinstance(error, CasinoError) else UNAVAILABLE)
        except discord.HTTPException:
            logging.warning("Casino delivery failed; reopen /casino to recover. No financial operation retried.")

    async def act(self, interaction, view: OwnedView, action: str, value=None):
        if not await view.interaction_check(interaction):
            return
        if action.startswith("custom:") and isinstance(view, SettingsView):
            await interaction.response.send_modal(BetModal(view, action.split(":")[1]))
            return
        await interaction.response.defer()
        async with view.lock:
            try:
                store = self.storage()
                uid = view.owner_id
                if action == "blackjack":
                    raise CasinoError("21 點尚未開放，不會扣款。")
                if action == "start" and isinstance(view, SettingsView):
                    game = await store.start(uid, view.prefs.token)
                    await self.show_result(interaction, game)
                elif action == "replay" and isinstance(view, ResultView):
                    game = await store.replay(uid, view.game.id)
                    await self.show_result(interaction, game)
                elif action in ("settings", "lobby"):
                    if isinstance(view, ResultView):
                        await store.leave(uid, game_id=view.game.id)
                    elif isinstance(view, SettingsView):
                        await store.leave(uid, token=view.prefs.token)
                    else:
                        recovered = await store.recover(uid)
                        if recovered is not None:
                            await self.show_result(interaction, recovered)
                            return
                    if action == "settings":
                        await self.show_settings(interaction, await store.settings(uid))
                    else:
                        await self.show_lobby(interaction)
                else:
                    if not isinstance(view, SettingsView):
                        raise CasinoError('此操作不適用目前面板。')
                    custom = action.startswith("submit:")
                    field, raw = action.split(":") if not custom else (action.split(":")[1], value)
                    prefs = await store.choose(uid, view.prefs.token, **{field: parse_integer(raw)}, custom=custom)
                    await self.show_settings(interaction, prefs)
            except CasinoError as error:
                await interaction.followup.send(str(error), ephemeral=True)
            except DatabaseError:
                await interaction.followup.send(UNAVAILABLE, ephemeral=True)
            except discord.HTTPException:
                logging.warning("Casino delivery failed; no financial operation retried.")

    async def show_lobby(self, interaction):
        balance = await self.storage().balance(interaction.user.id)
        if balance is not None:
            await self.storage().leave(interaction.user.id)
        embed = discord.Embed(title="水晶賭場", description="荷官歡迎你。請先選擇遊戲，再設定下注。", color=COLOR)
        embed.add_field(name="水晶餘額", value="尚無帳戶，請先 /水晶 簽到。" if balance is None else money(balance), inline=False)
        embed.set_footer(text="21 點尚未開放。面板僅限本人操作；面板逾時請重新 /賭場。")
        await self.render(interaction, embed, LobbyView(self, interaction.user.id), dealer=True)

    async def show_settings(self, interaction, prefs):
        balance = await self.storage().balance(interaction.user.id)
        embed = discord.Embed(title="18 豆仔 · 下注設定", color=COLOR)
        embed.add_field(name="基本下注", value=money(prefs.bet.base))
        embed.add_field(name="倍率", value=money(prefs.bet.multiplier))
        embed.add_field(name="實際下注", value=money(prefs.bet.total))
        embed.add_field(name="目前餘額", value=money(balance) if balance is not None else "尚無帳戶")
        embed.set_footer(text="設定與返回不扣款。豹子 > 456 > 對子單點 > 123 > 散骰；同級比總和，不重擲、不抽水。")
        await self.render(interaction, embed, SettingsView(self, interaction.user.id, prefs))

    async def show_result(self, interaction, game):
        labels = {"win": "勝利", "loss": "落敗", "tie": "平手", "void": "作廢退款"}
        embed = discord.Embed(title=f"18 豆仔 · {labels.get(game.outcome, game.status)}", color=COLOR)
        if game.status != "void":
            embed.description = f"玩家：{' · '.join(map(str, game.dice[:3]))}\n莊家：{' · '.join(map(str, game.dice[3:]))}"
        else:
            embed.description = "牌局資料無法恢復，已退回全部下注並保留退款流水。"
        embed.add_field(name="下注", value=money(game.wager))
        embed.add_field(name="返還（含本金）", value=money(game.returned))
        embed.add_field(name="淨盈虧", value=money(game.net))
        embed.add_field(name="結算後餘額", value=money(game.balance_after), inline=False)
        embed.set_footer(text=f"牌局 {game.id} · 版本 {game.version}")
        await self.render(interaction, embed, ResultView(self, interaction.user.id, game))

    async def render(self, interaction, embed, view, *, dealer=False):
        attachments = []
        if dealer:
            try:
                payload = await asyncio.to_thread(dealer_bytes, self.dealer_path)
                attachments = [discord.File(io.BytesIO(payload), filename="dealer.jpg")]
                embed.set_image(url="attachment://dealer.jpg")
            except OSError:
                embed.description += "\n荷官圖片暫時無法載入。"
        try:
            await interaction.edit_original_response(content=None, embed=embed, view=view, attachments=attachments,
                                                     allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            if not attachments:
                raise
            embed.set_image(url=None)
            embed.description += "\n荷官圖片暫時無法載入。"
            await interaction.edit_original_response(content=None, embed=embed, view=view, attachments=[],
                                                     allowed_mentions=discord.AllowedMentions.none())
        finally:
            for attachment in attachments:
                attachment.close()
