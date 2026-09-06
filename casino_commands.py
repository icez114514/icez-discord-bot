"""Public casino panels; durable money and operation tokens live in CasinoStore."""

import asyncio
import io
import logging
import os
import secrets
import time
from weakref import WeakValueDictionary
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import discord
from discord import app_commands
from discord.ext import tasks

from casino_rules import CasinoError, parse_integer
from blackjack import total
from casino_store import CasinoStore, Game, Preferences
from casino_images import renderer
from database import DatabaseError

COLOR = 0xDC9FB4
UNAVAILABLE = "賭場資料庫暫時無法確認操作結果，請重新使用 /賭場 查證；請勿假定未扣款。"
OWNER_ONLY = "這是其他玩家的面板，請使用 /賭場 開啟自己的大廳。"


def money(value: int) -> str:
    text = str(value)
    # Discord has field limits; storage and arithmetic always keep the exact integer.
    return text if len(text) <= 180 else f"{text[:80]}…{text[-40:]}（共 {len(text)} 位，顯示省略）"


@lru_cache(maxsize=16)
def dealer_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


@dataclass(frozen=True)
class ActiveMessage:
    game_id: UUID
    interaction: discord.Interaction
    shown_at: float
    version: int


class Delivery:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.revision = 0
        self.game_id = None
        self.version = 0


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
        self.button("21 點", "blackjack", style=discord.ButtonStyle.primary)
        self.button("18 豆仔", "settings", style=discord.ButtonStyle.primary)


class SettingsView(OwnedView):
    def __init__(self, feature, owner_id, prefs: Preferences, game_type='dice'):
        super().__init__(feature, owner_id)
        self.prefs = prefs
        self.game_type = game_type
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


class PlayView(OwnedView):
    def __init__(self, feature, owner_id, game: Game):
        super().__init__(feature, owner_id)
        self.game = game
        self.button('要牌', 'hit', style=discord.ButtonStyle.success)
        self.button('停牌', 'stand', style=discord.ButtonStyle.danger)
        self.button('加倍', 'double', style=discord.ButtonStyle.primary,
                    disabled=len(game.player) != 2 or game.balance_after < game.bet.total)


def card_text(card):
    if card is None:
        return '暗牌'
    return ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')[card % 13] + '♠♥♦♣'[card // 13]


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
        self.dealer_path = os.getenv('CASINO_DEALER_IMAGE') or ''
        self.asset_directory = os.getenv('CASINO_ASSET_DIR') or str(Path(__file__).with_name('casino_assets'))
        self.deliveries: WeakValueDictionary[int, Delivery] = WeakValueDictionary()
        self.owner_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
        self.active_messages: dict[int, ActiveMessage] = {}

    def preload(self):
        renderer(self.asset_directory)
        paths = [self.dealer_path] if self.dealer_path else Path(__file__).with_name('Mei').glob('*.jpg')
        for path in paths:
            try:
                dealer_bytes(str(path))
            except OSError:
                logging.warning('Casino dealer preload failed; text fallback remains available.')

    async def start_background(self):
        if self.store is not None and not self.expiry_loop.is_running():
            try:
                await asyncio.to_thread(self.preload)
            except Exception:
                logging.warning('Casino asset preload failed; text fallback remains available.')
            self.expiry_loop.start()

    async def stop_background(self):
        task = self.expiry_loop.get_task()
        self.expiry_loop.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.active_messages.clear()

    @tasks.loop(seconds=2)
    async def expiry_loop(self):
        try:
            await self.expire_once()
        except Exception:
            logging.warning('Casino expiry check failed; will retry from persisted state.')

    async def expire_once(self):
        results = await self.storage().expire_pending()
        for game in results:
            async with self.owner_lock(game.user_id):
                target = self.active_messages.get(game.user_id)
                if target is not None and target.game_id == game.id:
                    try:
                        await self.show_result(target.interaction, game)
                    except discord.HTTPException:
                        logging.warning('Casino expiry delivery failed; settlement is durable.')
        for user_id, target in list(self.active_messages.items()):
            if time.monotonic() - target.shown_at > 600:
                self.active_messages.pop(user_id, None)

    def owner_lock(self, user_id):
        lock = self.owner_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self.owner_locks[user_id] = lock
        return lock

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
        async with self.owner_lock(interaction.user.id):
            await self._slash(interaction)

    async def _slash(self, interaction):
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
        async with self.owner_lock(view.owner_id):
            try:
                store = self.storage()
                uid = view.owner_id
                if action == "start" and isinstance(view, SettingsView):
                    game = await store.start(uid, view.prefs.token, game=view.game_type)
                    await self.show_result(interaction, game)
                elif action in ('hit', 'stand', 'double') and isinstance(view, PlayView):
                    game = await store.play(uid, view.game.id, view.game.version, action)
                    await self.show_result(interaction, game)
                elif action == "replay" and isinstance(view, ResultView):
                    game = await store.replay(uid, view.game.id)
                    await self.show_result(interaction, game)
                elif action in ("settings", "blackjack", "lobby"):
                    game_type = 'blackjack' if action == 'blackjack' else (
                        view.game.game if isinstance(view, ResultView) else 'dice')
                    if isinstance(view, ResultView):
                        await store.leave(uid, game_id=view.game.id)
                    elif isinstance(view, SettingsView):
                        await store.leave(uid, token=view.prefs.token)
                    else:
                        recovered = await store.recover(uid)
                        if recovered is not None:
                            await self.show_result(interaction, recovered)
                            return
                    if action in ('settings', 'blackjack'):
                        await self.show_settings(interaction, await store.settings(uid), game_type)
                    else:
                        await self.show_lobby(interaction)
                else:
                    if not isinstance(view, SettingsView):
                        raise CasinoError('此操作不適用目前面板。')
                    custom = action.startswith("submit:")
                    field, raw = action.split(":") if not custom else (action.split(":")[1], value)
                    prefs = await store.choose(uid, view.prefs.token, **{field: parse_integer(raw)}, custom=custom)
                    await self.show_settings(interaction, prefs, view.game_type)
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
        embed.set_footer(text="面板僅限本人操作；面板逾時請重新 /賭場。")
        await self.render(interaction, embed, LobbyView(self, interaction.user.id), dealer=True)

    async def show_settings(self, interaction, prefs, game_type='dice'):
        balance = await self.storage().balance(interaction.user.id)
        embed = discord.Embed(title=('21 點' if game_type == 'blackjack' else '18 豆仔') + ' · 下注設定', color=COLOR)
        embed.add_field(name="基本下注", value=money(prefs.bet.base))
        embed.add_field(name="倍率", value=money(prefs.bet.multiplier))
        embed.add_field(name="實際下注", value=money(prefs.bet.total))
        embed.add_field(name="目前餘額", value=money(balance) if balance is not None else "尚無帳戶")
        embed.set_footer(text="設定與返回不扣款。豹子 > 456 > 對子單點 > 123 > 散骰；同級比總和，不重擲、不抽水。")
        if game_type == 'blackjack':
            embed.set_footer(text='首兩張可加倍；軟 17 停牌；120 秒無有效操作自動停牌。天然勝利返還 2.5 倍，普通勝利 2 倍。')
        await self.render(interaction, embed, SettingsView(self, interaction.user.id, prefs, game_type))

    async def show_result(self, interaction, game):
        labels = {"win": "勝利", "loss": "落敗", "tie": "平手", "void": "作廢退款"}
        name = '21 點' if game.game == 'blackjack' else '18 豆仔'
        embed = discord.Embed(title=f"{name} · {labels.get(game.outcome, '你的回合')}", color=COLOR)
        if game.game == 'blackjack' and game.status != 'void':
            dealer_total = str(total(game.dealer)) if game.status != 'active' else f'{total(game.dealer[:1])} + ?'
            embed.description = (f"玩家：{' · '.join(map(card_text, game.player))}（{total(game.player)} 點）\n"
                                 f"莊家：{' · '.join(map(card_text, game.dealer))}（{dealer_total} 點）")
            if game.deadline is not None:
                embed.description += f'\n期限：<t:{int(game.deadline.timestamp())}:R>（到期自動停牌）'
        elif game.status != "void":
            embed.description = (f"玩家：{' · '.join(map(str, game.dice[:3]))}（總和 {sum(game.dice[:3])}）\n"
                                 f"莊家：{' · '.join(map(str, game.dice[3:]))}（總和 {sum(game.dice[3:])}）")
        else:
            embed.description = "牌局資料無法恢復，已退回全部下注並保留退款流水。"
        embed.add_field(name="下注", value=money(game.wager))
        embed.add_field(name="返還（含本金）", value=money(game.returned) if game.status != 'active' else '待結算')
        embed.add_field(name="淨盈虧", value=money(game.net) if game.status != 'active' else '待結算')
        embed.add_field(name="扣款後餘額" if game.status == 'active' else "結算後餘額", value=money(game.balance_after), inline=False)
        embed.set_footer(text=f"牌局 {game.id} · 版本 {game.version}")
        view = PlayView(self, game.user_id, game) if game.status == 'active' else ResultView(self, game.user_id, game)
        shown = await self.render(interaction, embed, view, game=game)
        if not shown:
            return
        if game.status == 'active':
            current = self.active_messages.get(game.user_id)
            if current is None or current.game_id != game.id or current.version <= game.version:
                self.active_messages[game.user_id] = ActiveMessage(game.id, interaction, time.monotonic(), game.version)
        else:
            current = self.active_messages.get(game.user_id)
            if current is not None and current.game_id == game.id:
                self.active_messages.pop(game.user_id, None)

    async def table_image(self, game):
        return await asyncio.to_thread(lambda: renderer(self.asset_directory).render(game))

    def lobby_image(self):
        paths = [self.dealer_path] if self.dealer_path else sorted(str(path) for path in Path(__file__).with_name('Mei').glob('*.jpg'))
        if not paths:
            raise OSError('No dealer images')
        return dealer_bytes(secrets.choice(paths))

    async def render(self, interaction, embed, view, *, dealer=False, game=None):
        key = getattr(getattr(interaction, 'message', None), 'id', None) or getattr(interaction, 'id', id(interaction))
        if not isinstance(key, int):
            key = id(interaction)
        delivery = self.deliveries.get(key)
        if delivery is None:
            delivery = Delivery()
            self.deliveries[key] = delivery
        view.delivery = delivery
        if game is not None and delivery.game_id == game.id and game.version < delivery.version:
            return
        delivery.game_id = game.id if game is not None else None
        delivery.version = game.version if game is not None else 0
        delivery.revision += 1
        revision = delivery.revision
        started = time.perf_counter()
        attachments = []
        if game is not None:
            try:
                payload = await self.table_image(game)
                attachments = [discord.File(io.BytesIO(payload), filename='table.png')]
                embed.set_image(url='attachment://table.png')
            except Exception:
                logging.warning('Casino composition failed; using text projection.')
                embed.description = (embed.description or '') + '\n圖片暫時無法載入。'
        if dealer:
            try:
                payload = await asyncio.to_thread(self.lobby_image)
                attachments = [discord.File(io.BytesIO(payload), filename="dealer.jpg")]
                embed.set_image(url="attachment://dealer.jpg")
            except OSError:
                embed.description += "\n荷官圖片暫時無法載入。"
        composed = time.perf_counter()
        try:
            async with delivery.lock:
                if revision != delivery.revision:
                    return
                try:
                    message = await interaction.edit_original_response(content=None, embed=embed, view=view, attachments=attachments,
                                                                      allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    if not attachments:
                        raise
                    embed.set_image(url=None)
                    embed.description = (embed.description or '') + '\n圖片暫時無法載入。'
                    message = await interaction.edit_original_response(content=None, embed=embed, view=view, attachments=[],
                                                                      allowed_mentions=discord.AllowedMentions.none())
                if isinstance(getattr(message, 'id', None), int):
                    self.deliveries[message.id] = delivery
                logging.info('Casino render compose_ms=%.1f update_ms=%.1f version=%s',
                             (composed-started)*1000, (time.perf_counter()-composed)*1000, delivery.version)
                return True
        finally:
            for attachment in attachments:
                attachment.close()
