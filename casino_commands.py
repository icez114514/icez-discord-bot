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

from casino_rules import CasinoError, InsufficientBalance, dice_points, parse_integer
from blackjack import total
import paigow
from casino_store import CasinoStore, Game, Preferences, LobbySnapshot
from casino_records import CasinoRecords, Record, Summary
from casino_images import renderer
from database import DatabaseError, DatabaseBusy
from latency import measure, record_age, timing_logger, discord_update, mark_status, mark_action, operation, timed, measured_lock, add_time, correlation_id

# Unsigned attachment URLs in embeds are refreshed by Discord.
DEALER_IMAGE_URLS = ('https://cdn.discordapp.com/attachments/1495692135452901496/1546121292745539614/Mei_1.jpg', 'https://cdn.discordapp.com/attachments/1495692135452901496/1546121293353451642/Mei_2.jpg', 'https://cdn.discordapp.com/attachments/1495692135452901496/1546121294054170634/Mei_3.jpg', 'https://cdn.discordapp.com/attachments/1495692135452901496/1546121295106674698/Mei_4.jpg', 'https://cdn.discordapp.com/attachments/1495692135452901496/1546121295765315614/Mei_5.jpg', 'https://cdn.discordapp.com/attachments/1495692135452901496/1546121296457236590/Mei_6.jpg')

GAME_NAMES = {'dice': '18 豆仔', 'blackjack': '21 點', 'paigow': '牌九撲克'}

COLOR = 0xDC9FB4
UNAVAILABLE = "賭場資料庫暫時無法確認操作結果，請重新使用 /賭場 查證；請勿假定未扣款。"
BUSY = "賭場目前忙碌，請稍後再試；若已有牌局，請使用 /賭場 查證。"
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
        self.image_task: asyncio.Task | None = None
        self.image_uploading = False
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
            await discord_update(interaction.response.send_message(OWNER_ONLY, ephemeral=True))
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
        self.button("牌九撲克", "paigow", style=discord.ButtonStyle.primary)
        self.button("我的紀錄", "records")
        self.button("莊家統計", "house")


class RecordsView(OwnedView):
    def __init__(self, feature, owner_id, *, house=False, user_id=None, game=None,
                 game_id=None, page=0, detail=False, audit=False, has_next=False):
        super().__init__(feature, owner_id)
        self.has_next = has_next
        self.house = house
        self.user_id = None if house else (owner_id if user_id is None and not audit else user_id)
        self.game_filter = game
        self.game_id = game_id
        self.page = page
        self.detail = detail
        self.audit = audit
        self.button("上一頁", "previous", disabled=page == 0)
        self.button("下一頁", "next", disabled=not has_next)
        if not house and game_id is None:
            self.button("統計" if detail else "牌局明細", "toggle")
        self.button("遊戲篩選", "filter")


    async def interaction_check(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        if self.is_finished():
            await discord_update(interaction.response.send_message("此查詢頁已失效，請使用最新頁面或重新開啟紀錄。", ephemeral=True))
            return False
        return True


class AuditView(OwnedView):
    async def interaction_check(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        if self.is_finished():
            await discord_update(interaction.response.send_message("目前沒有查帳權限或入口已失效。", ephemeral=True))
            return False
        return True

    def __init__(self, feature, owner_id):
        super().__init__(feature, owner_id)
        self.button("查玩家", "audit_player")
        self.button("查牌局", "audit_game")


class AuditModal(discord.ui.Modal):
    def __init__(self, panel, kind):
        super().__init__(title="管理查帳")
        self.panel = panel
        self.kind = kind
        self.value: discord.ui.TextInput = discord.ui.TextInput(
            label="玩家 ID" if kind == "audit_player" else "牌局 UUID", max_length=36)
        self.add_item(self.value)

    async def on_submit(self, interaction):
        if not await self.panel.interaction_check(interaction):
            return
        value = self.value.value.strip()
        try:
            user_id, game_id = None, None
            if self.kind == "audit_player":
                if not value.isascii() or not value.isdecimal() or not 0 < int(value) < 2**64:
                    raise ValueError()
                user_id = int(value)
            else:
                game_id = UUID(value)
        except ValueError:
            await discord_update(interaction.response.send_message("請輸入有效的玩家 ID 或牌局 UUID。", ephemeral=True))
            return
        await self.panel.feature.show_records(interaction, RecordsView(
            self.panel.feature, self.panel.owner_id, user_id=user_id, game_id=game_id, audit=True, detail=True))


class QueryModal(discord.ui.Modal):
    def __init__(self, panel):
        super().__init__(title="遊戲篩選")
        self.panel = panel
        self.value: discord.ui.TextInput = discord.ui.TextInput(
            label="遊戲識別（dice／blackjack／paigow）", required=False, max_length=100,
            default=panel.game_filter)
        self.add_item(self.value)

    async def on_submit(self, interaction):
        await self.panel.feature.records_action(interaction, self.panel, "apply_filter", self.value.value.strip())


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



class PaiGowSelect(discord.ui.Select):
    def __init__(self, panel):
        self.panel = panel
        options = [discord.SelectOption(label=f'{i + 1}. {card_text(card)}',
                    value=str(card), default=card in panel.game.front)
                   for i, card in enumerate(paigow.display_order(panel.game.player))]
        super().__init__(placeholder='選擇前墩兩張，剩餘五張為後墩',
                         min_values=2, max_values=2, options=options, row=0)

    async def callback(self, interaction):
        await self.panel.feature.act(interaction, self.panel, 'pai_select', list(self.values))


class PaiGowView(OwnedView):
    def __init__(self, feature, owner_id, game: Game):
        super().__init__(feature, owner_id)
        self.game = game
        self.add_item(PaiGowSelect(self))
        self.button('自動分牌', 'pai_auto', row=1)
        self.button('確認分牌', 'pai_confirm', row=1, style=discord.ButtonStyle.success,
                    disabled=not game.front)


def paigow_hand_text(cards):
    evaluated = paigow.evaluate(cards)
    text = ' · '.join(map(card_text, paigow.display_order(cards))) + f'（{evaluated.name}）'
    if evaluated.joker_as is not None:
        text += f' Joker 當 {card_text(evaluated.joker_as)}'
    return text


def paigow_description(game):
    lines = ['手牌：' + ' · '.join(f'{i + 1}:{card_text(card)}' for i, card in enumerate(paigow.display_order(game.player)))]
    if game.front:
        low, high = paigow.split(game.player, game.front)
        lines += ['你的前墩：' + paigow_hand_text(low), '你的後墩：' + paigow_hand_text(high)]
    else:
        lines.append('請選前墩兩張牌，或使用自動分牌，再確認送出。')
    if game.status == 'active':
        lines.append('莊家：七張暗牌，確認後揭曉。')
        if game.deadline is not None:
            lines.append(f'期限：<t:{int(game.deadline.timestamp())}:R>（固定 120 秒，到期自動分牌結算）')
    else:
        low, high = paigow.split(game.dealer, game.dealer_front)
        player_low, player_high = paigow.split(game.player, game.front)
        comparisons, _ = paigow.compare(player_low, player_high, low, high)
        results = {1: '勝', 0: '同牌，莊家勝', -1: '負'}
        lines += ['莊家前墩：' + paigow_hand_text(low), '莊家後墩：' + paigow_hand_text(high),
                  f'逐墩結果：前墩 {results[comparisons[0]]}／後墩 {results[comparisons[1]]}']
    lines.append('全萬用 Joker · 五條最高 · A2345 第二大順子 · 同牌莊家勝 · 免抽水')
    return '\n'.join(lines)


def card_text(card):
    if card is None:
        return '暗牌'
    if card == paigow.JOKER:
        return 'Joker'
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
        self.pending_actions: set[int] = set()
        self.image_tasks: set[asyncio.Task] = set()

    def preload(self):
        renderer(self.asset_directory)
        paths = [self.dealer_path] if self.dealer_path else []
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
        images = list(self.image_tasks)
        for image_task in images:
            image_task.cancel()
        await asyncio.gather(*images, return_exceptions=True)
        self.image_tasks.clear()

    @tasks.loop(seconds=2)
    async def expiry_loop(self):
        try:
            await self.expire_once()
        except Exception:
            logging.warning('Casino expiry check failed; will retry from persisted state.')

    @operation("casino.expire_once")
    async def expire_once(self):
        results = await self.storage().expire_pending()
        for game in results:
            async with measured_lock(self.owner_lock(game.user_id)):
                target = self.active_messages.get(game.user_id)
                if target is not None and target.game_id == game.id:
                    try:
                        await self.show_result(target.interaction, game)
                    except discord.HTTPException:
                        mark_status("delivery_error")
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

    async def acknowledge(self, interaction, **kwargs):
        started = time.perf_counter()
        record_age(interaction, "ack_start_age_ms")
        try:
            with measure("ack_http_ms"):
                await discord_update(interaction.response.defer(**kwargs))
        except discord.NotFound as error:
            if error.code != 10062:
                raise
            mark_status('expired_interaction')
            logging.warning('Casino acknowledgement expired (10062), ack_ms=%.1f; '
                            'operation not started. Reopen /casino.',
                            (time.perf_counter() - started) * 1000)
            return False
        finally:
            record_age(interaction, "ack_complete_age_ms")
        return True

    @operation("casino.slash")
    async def slash(self, interaction):
        if interaction.guild is None or interaction.user.bot:
            await discord_update(interaction.response.send_message("請在伺服器中使用賭場。", ephemeral=True))
            return
        channel_name = (getattr(getattr(interaction, 'channel', None), 'name', None) or '').casefold()
        if not any(word in channel_name for word in ('簽到', '測試', '賭場', '指令', 'test')):
            await discord_update(interaction.response.send_message(
                '請至指令頻道使用',
                ephemeral=True))
            return
        if not await self.acknowledge(interaction, thinking=True):
            return
        async with measured_lock(self.owner_lock(interaction.user.id)):
            await self._slash(interaction)

    async def _slash(self, interaction):
        try:
            game = await self.storage().open_panel(interaction.user.id)
            if isinstance(game, Game):
                await self.show_result(interaction, game)
            else:
                await self.show_lobby(interaction, game)
        except (CasinoError, DatabaseError) as error:
            mark_status("rejected" if isinstance(error, CasinoError) else "database_error")
            await discord_update(interaction.edit_original_response(content=str(error) if isinstance(error, CasinoError) else BUSY if isinstance(error, DatabaseBusy) else UNAVAILABLE))
        except discord.HTTPException:
            mark_status("delivery_error")
            logging.warning("Casino delivery failed; reopen /casino to recover. No financial operation retried.")

    @operation("casino.act")
    async def act(self, interaction, view: OwnedView, action: str, value=None):
        mark_action(action)
        if action not in ('start', 'replay', 'hit', 'stand', 'double', 'pai_select', 'pai_auto', 'pai_confirm'):
            return await self._act(interaction, view, action, value)
        if interaction.user.id != view.owner_id:
            await view.interaction_check(interaction)
            return
        if view.owner_id in self.pending_actions:
            mark_status('duplicate_ignored')
            await self.acknowledge(interaction)
            return
        # Reserve before the first await, including Discord acknowledgement.
        self.pending_actions.add(view.owner_id)
        try:
            return await self._act(interaction, view, action, value)
        finally:
            self.pending_actions.discard(view.owner_id)

    async def _act(self, interaction, view: OwnedView, action: str, value=None):
        if isinstance(view, AuditView):
            if await view.interaction_check(interaction) and action in ("audit_player", "audit_game"):
                if not await self.is_auditor(interaction):
                    await discord_update(interaction.response.send_message("目前沒有查帳權限。", ephemeral=True))
                    return
                await discord_update(interaction.response.send_modal(AuditModal(view, action)))
            return
        if isinstance(view, RecordsView):
            await self.records_action(interaction, view, action, value)
            return
        if not await view.interaction_check(interaction):
            return
        if action.startswith("custom:") and isinstance(view, SettingsView):
            await discord_update(interaction.response.send_modal(BetModal(view, action.split(":")[1])))
            return
        if isinstance(view, LobbyView) and action in ("records", "house"):
            await self.show_records(interaction, RecordsView(self, view.owner_id, house=action == "house"))
            return
        if not await self.acknowledge(interaction):
            return
        async with measured_lock(self.owner_lock(view.owner_id)):
            try:
                store = self.storage()
                uid = view.owner_id
                if action == "start" and isinstance(view, SettingsView):
                    game = await store.start(uid, view.prefs.token, game=view.game_type)
                    await self.show_result(interaction, game)
                elif action in ('hit', 'stand', 'double') and isinstance(view, PlayView):
                    game = await store.play(uid, view.game.id, view.game.version, action)
                    await self.show_result(interaction, game)
                elif action in ('pai_select', 'pai_auto', 'pai_confirm') and isinstance(view, PaiGowView):
                    front = None
                    if action == 'pai_select':
                        if not isinstance(value, list) or len(value) != 2:
                            raise CasinoError('請選擇前墩兩張牌。')
                        try:
                            front = [int(card) for card in value]
                        except (ValueError, TypeError):
                            raise CasinoError('選牌無效，請重新選擇。')
                    game = await store.play_paigow(uid, view.game.id, view.game.version,
                                                   action.removeprefix('pai_'), front)
                    await self.show_result(interaction, game)
                elif action == "replay" and isinstance(view, ResultView):
                    game = await store.replay(uid, view.game.id)
                    await self.show_result(interaction, game)
                elif action in ("settings", "blackjack", "paigow", "lobby"):
                    game_type = action if action in ('blackjack', 'paigow') else (
                        view.game.game if isinstance(view, ResultView) else 'dice')
                    source = ({'game_id': view.game.id} if isinstance(view, ResultView) else
                              {'token': view.prefs.token} if isinstance(view, SettingsView) else {})
                    panel = await store.open_panel(uid, settings=action != 'lobby', **source)
                    if isinstance(panel, Game):
                        await self.show_result(interaction, panel)
                    elif isinstance(panel, LobbySnapshot):
                        await self.show_lobby(interaction, panel)
                    else:
                        await self.show_settings(interaction, panel, game_type)
                else:
                    if not isinstance(view, SettingsView):
                        raise CasinoError('此操作不適用目前面板。')
                    custom = action.startswith("submit:")
                    field, raw = action.split(":") if not custom else (action.split(":")[1], value)
                    prefs = await store.choose_settings(uid, view.prefs.token, **{field: parse_integer(raw)}, custom=custom)
                    await self.show_settings(interaction, prefs, view.game_type)
            except InsufficientBalance as error:
                mark_status("rejected")
                try:
                    await discord_update(interaction.edit_original_response(
                        content=str(error), allowed_mentions=discord.AllowedMentions.none()))
                except discord.HTTPException:
                    logging.warning('Casino insufficient balance notice failed; no financial operation retried.')
            except CasinoError as error:
                mark_status("rejected")
                await discord_update(interaction.followup.send(str(error), ephemeral=True))
            except DatabaseBusy:
                mark_status("busy")
                await discord_update(interaction.followup.send(BUSY, ephemeral=True))
            except DatabaseError:
                mark_status("database_error")
                await discord_update(interaction.followup.send(UNAVAILABLE, ephemeral=True))
            except discord.HTTPException:
                mark_status("delivery_error")
                logging.warning("Casino delivery failed; no financial operation retried.")

    async def show_lobby(self, interaction, panel: LobbySnapshot):
        balance = panel.balance
        embed = discord.Embed(title="水晶賭場", description="荷官歡迎你。請先選擇遊戲，再設定下注。", color=COLOR)
        embed.add_field(name="水晶餘額", value="尚無帳戶，請先 /水晶 簽到。" if balance is None else money(balance), inline=False)
        embed.set_footer(text="面板僅限本人操作；面板逾時請重新 /賭場。")
        await self.render(interaction, embed, LobbyView(self, interaction.user.id), dealer=True)
        if await self.is_auditor(interaction):
            await discord_update(interaction.followup.send("管理查帳（僅限授權者）", view=AuditView(self, interaction.user.id),
                ephemeral=True, allowed_mentions=discord.AllowedMentions.none()))

    @timed('auth_ms')
    async def is_auditor(self, interaction) -> bool:
        # Read current configuration, never remember a grant in a view or Modal.
        ids = os.getenv("CASINO_AUDITOR_IDS", "").replace(",", " ").split()
        if str(interaction.user.id) in ids:
            return True
        client = getattr(interaction, "client", None)
        if client is None:
            return False
        try:
            app = await asyncio.wait_for(client.application_info(), timeout=1.5)
            owner_id = app.team.owner_id if app.team is not None else app.owner.id
            return interaction.user.id == owner_id
        except (discord.HTTPException, asyncio.TimeoutError):
            return False

    @operation("casino.records_action")
    async def records_action(self, interaction, view: RecordsView, action: str, value=None):
        mark_action(action)
        if not await view.interaction_check(interaction):
            return
        if action == "filter":
            if view.audit and not await self.is_auditor(interaction):
                await discord_update(interaction.response.send_message("目前沒有查帳權限。", ephemeral=True))
                return
            await discord_update(interaction.response.send_modal(QueryModal(view)))
            return
        if not await self.acknowledge(interaction):
            return
        async with view.lock:
            if view.is_finished():
                await discord_update(interaction.followup.send("此查詢頁已失效或權限已撤銷。", ephemeral=True))
                return
            page, detail, game = view.page, view.detail, view.game_filter
            if action == "next" and view.has_next:
                page += 1
            elif action == "previous" and page > 0:
                page -= 1
            elif action == "toggle" and not view.house and view.game_id is None:
                page, detail = 0, not detail
            elif action == "apply_filter":
                page, game = 0, value or None
            else:
                await discord_update(interaction.followup.send("此查詢操作已失效。", ephemeral=True))
                return
            replacement = RecordsView(self, view.owner_id, house=view.house, user_id=view.user_id,
                game=game, game_id=view.game_id, page=page, detail=detail, audit=view.audit)
            if await self.show_records(interaction, replacement, edit=True):
                view.stop()

    @operation("casino.show_records")
    async def show_records(self, interaction, view: RecordsView, *, edit=False):
        if not edit:
            if not await self.acknowledge(interaction, ephemeral=not view.house, thinking=True):
                return
        try:
            if view.audit and not await self.is_auditor(interaction):
                await discord_update(interaction.followup.send("目前沒有查帳權限。", ephemeral=True))
                return False
            records = CasinoRecords(self.storage())
            summary_rows: tuple[Summary, ...] = ()
            detail_rows: tuple[Record, ...] = ()
            if view.detail:
                history = await records.history(user_id=view.user_id, game=view.game_filter, game_id=view.game_id, page=view.page)
                detail_rows, has_next = history.rows, history.has_next
            else:
                summary = await records.summary(user_id=view.user_id, game=view.game_filter, page=view.page)
                summary_rows, has_next = summary.rows, summary.has_next
            embed = discord.Embed(title="莊家統計" if view.house else ("管理查帳" if view.audit else "我的紀錄"), color=COLOR)
            for row in summary_rows:
                status = {"settled": "正常完成", "active": "進行中（另列）", "void": "作廢退款（另列）"}[row.status]
                amounts = (f"收取 {money(row.wager)}／支出 {money(row.returned)}／淨額 {money(-row.net)}"
                           if view.house else
                           f"累計下注 {money(row.wager)}／返還含本金 {money(row.returned)}／淨盈虧 {money(row.net)}")
                embed.add_field(name=f"{row.game} · {status}", inline=False,
                                value=f"{row.count} 局 · 勝 {row.losses if view.house else row.wins}／負 {row.wins if view.house else row.losses}／平 {row.ties}\n{amounts}")
            if view.detail:
                for record in detail_rows:
                    embed.description = (f"玩家 {record.user_id} · 遊戲 {record.game}\n牌局 {record.id}\n"
                        f"狀態 {record.status} · 結果 {record.outcome or '待結算'}\n"
                        f"開始 <t:{int(record.created_at.timestamp())}:f>\n"
                        + (f"結束 <t:{int(record.finished_at.timestamp())}:f>\n" if record.finished_at else "")
                        + (f"原因 {record.reason}" if record.reason else ""))
                    embed.add_field(name="原下注", value=money(record.original_wager))
                    embed.add_field(name="累計下注", value=money(record.wager))
                    embed.add_field(name="退款" if record.status == "void" else "返還（含本金）", value=money(record.returned))
                    embed.add_field(name="在途淨額（未結算）" if record.status == "active" else "淨盈虧", value=money(record.net))
                    for entry in record.entries:
                        embed.add_field(name=f"流水 · {entry.kind}", inline=False,
                            value=f"金額 {money(entry.amount)}\n餘額 {money(entry.before)} → {money(entry.after)}")
            if not summary_rows and not detail_rows:
                embed.description = "沒有符合條件的紀錄。"
            embed.set_footer(text=f"第 {view.page + 1} 頁 · 進行中與作廢不計正常局數；金額依流水重算。")
            if view.audit and not await self.is_auditor(interaction):
                await discord_update(interaction.followup.send("查帳權限已撤銷。", ephemeral=True))
                return False
            view.has_next = has_next
            for button in view.children:
                if isinstance(button, ActionButton) and button.action == "next":
                    button.disabled = not has_next
            if edit:
                await discord_update(interaction.edit_original_response(embed=embed, view=view,
                    allowed_mentions=discord.AllowedMentions.none()))
            else:
                await discord_update(interaction.followup.send(embed=embed, view=view, ephemeral=not view.house,
                    allowed_mentions=discord.AllowedMentions.none()))
            return True
        except DatabaseError as error:
            mark_status("busy" if isinstance(error, DatabaseBusy) else "database_error")
            await discord_update(interaction.followup.send(BUSY if isinstance(error, DatabaseBusy) else UNAVAILABLE, ephemeral=True))

    async def show_settings(self, interaction, panel, game_type='dice'):
        prefs, balance = panel.preferences, panel.balance
        embed = discord.Embed(title=GAME_NAMES.get(game_type, game_type) + ' · 下注設定', color=COLOR)
        embed.add_field(name="基本下注", value=money(prefs.bet.base))
        embed.add_field(name="倍率", value=money(prefs.bet.multiplier))
        embed.add_field(name="實際下注", value=money(prefs.bet.total))
        embed.add_field(name="目前餘額", value=money(balance) if balance is not None else "尚無帳戶")
        if balance is not None and balance < prefs.bet.total:
            embed.description = '水晶餘額不足，請修改下注金額。'
        embed.set_footer(text="設定與返回不扣款。豹子＝骰值×10、456＝7、對子取單點、123＝0、散骰＝−1；同點比總和，不重擲、不抽水。")
        if game_type == 'blackjack':
            embed.set_footer(text='首兩張可加倍；軟 17 停牌；120 秒無有效操作自動停牌。天然勝利返還 2.5 倍，普通勝利 2 倍。')
        if game_type == 'paigow':
            embed.set_footer(text='前二後五；Joker 全萬用、五條最高、A2345 第二大順子、同牌莊家勝。免抽水，勝／和／負返還 2／1／0 倍；120 秒到期自動分牌結算。')
        await self.render(interaction, embed, SettingsView(self, interaction.user.id, prefs, game_type))

    async def show_result(self, interaction, game):
        labels = {"win": "勝利", "loss": "落敗", "tie": "平手", "void": "作廢退款"}
        name = GAME_NAMES.get(game.game, game.game)
        embed = discord.Embed(title=f"{name} · {labels.get(game.outcome, '你的回合')}", color=COLOR)
        if game.game == 'blackjack' and game.status != 'void':
            dealer_total = str(total(game.dealer)) if game.status != 'active' else f'{total(game.dealer[:1])} + ?'
            embed.description = (f"玩家：{' · '.join(map(card_text, game.player))}（{total(game.player)} 點）\n"
                                 f"莊家：{' · '.join(map(card_text, game.dealer))}（{dealer_total} 點）")
            if game.deadline is not None:
                embed.description += f'\n期限：<t:{int(game.deadline.timestamp())}:R>（到期自動停牌）'
        elif game.game == 'paigow' and game.status != 'void':
            embed.description = paigow_description(game)
        elif game.game == 'dice' and game.status != "void":
            embed.description = (f"玩家：{' · '.join(map(str, game.dice[:3]))}（{dice_points(game.dice[:3])} 點）\n"
                                 f"莊家：{' · '.join(map(str, game.dice[3:]))}（{dice_points(game.dice[3:])} 點）")
        else:
            embed.description = "牌局資料無法恢復，已退回全部下注並保留退款流水。"
        embed.add_field(name="下注", value=money(game.wager))
        embed.add_field(name="返還（含本金）", value=money(game.returned) if game.status != 'active' else '待結算')
        embed.add_field(name="淨盈虧", value=money(game.net) if game.status != 'active' else '待結算')
        embed.add_field(name="扣款後餘額" if game.status == 'active' else "結算後餘額", value=money(game.balance_after), inline=False)
        if game.balance_after < game.bet.total:
            if game.status != 'active':
                embed.add_field(name='提示', value='水晶餘額不足以再來一局，請修改下注金額。', inline=False)
            elif len(game.player) == 2:
                embed.add_field(name='提示', value='水晶餘額不足，無法加倍；仍可要牌或停牌。', inline=False)
        embed.set_footer(text=f"牌局 {game.id} · 版本 {game.version}")
        view = (PaiGowView(self, game.user_id, game) if game.game == 'paigow' else
                PlayView(self, game.user_id, game)) if game.status == 'active' else ResultView(self, game.user_id, game)
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


    async def preview_paigow(self, interaction, embed, view, game, delivery, revision):
        # This projection was committed before show_result. Enable controls immediately;
        # New composition/upload runs outside the owner action lock and click guard.
        # A previously accepted image edit must finish before this newer preview.
        async with delivery.lock:
            if revision != delivery.revision:
                return False
            message = await discord_update(interaction.edit_original_response(
                content=None, embed=embed, view=view, attachments=[],
                allowed_mentions=discord.AllowedMentions.none()))
            if isinstance(getattr(message, 'id', None), int):
                self.deliveries[message.id] = delivery
        task = asyncio.create_task(self.refresh_paigow_image(
            interaction, embed.copy(), game, delivery, revision))
        delivery.image_task = task
        self.image_tasks.add(task)
        task.add_done_callback(self.image_tasks.discard)
        return True

    async def refresh_paigow_image(self, interaction, embed, game, delivery, revision):
        started = time.perf_counter()
        try:
            payload = await self.table_image(game)
            composed = time.perf_counter()
            embed.set_image(url='attachment://table.png')
            # Never restore controls from a previous snapshot. The preview already
            # owns the current view; an image refresh changes only image and embed.
            async with delivery.lock:
                if revision != delivery.revision:
                    return
                attachment = discord.File(io.BytesIO(payload), filename='table.png')
                delivery.image_uploading = True
                try:
                    await interaction.edit_original_response(
                        embed=embed, attachments=[attachment],
                        allowed_mentions=discord.AllowedMentions.none())
                finally:
                    delivery.image_uploading = False
                    attachment.close()
            timing_logger.info('Casino image refresh compose_ms=%.1f upload_ms=%.1f version=%s',
                               (composed-started)*1000, (time.perf_counter()-composed)*1000, game.version)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The confirmed text preview remains usable even if composition or upload fails.
            logging.warning('Casino image refresh failed; committed text preview remains available.')

    def lobby_image(self):
        return dealer_bytes(self.dealer_path)

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
        if delivery.image_task is not None:
            # Cancellation cannot revoke a PATCH already accepted by Discord.
            # Keep an in-flight upload serialized before any newer preview.
            if not delivery.image_uploading:
                delivery.image_task.cancel()
            delivery.image_task = None
        delivery.game_id = game.id if game is not None else None
        delivery.version = game.version if game is not None else 0
        delivery.revision += 1
        revision = delivery.revision
        if game is not None and game.game == 'paigow' and game.status == 'active':
            return await self.preview_paigow(interaction, embed, view, game, delivery, revision)
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
        if dealer and not self.dealer_path:
            embed.set_image(url=secrets.choice(DEALER_IMAGE_URLS))
        elif dealer:
            try:
                payload = await asyncio.to_thread(self.lobby_image)
                attachments = [discord.File(io.BytesIO(payload), filename="dealer.jpg")]
                embed.set_image(url="attachment://dealer.jpg")
            except OSError:
                embed.description += "\n荷官圖片暫時無法載入。"
        composed = time.perf_counter()
        add_time("compose_ms", composed-started)
        try:
            async with delivery.lock:
                if revision != delivery.revision:
                    return
                try:
                    message = await interaction.edit_original_response(content=None, embed=embed, view=view, attachments=attachments,
                                                                      allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    mark_status("delivery_error")
                    if not attachments:
                        raise
                    embed.set_image(url=None)
                    embed.description = (embed.description or '') + '\n圖片暫時無法載入。'
                    message = await interaction.edit_original_response(content=None, embed=embed, view=view, attachments=[],
                                                                      allowed_mentions=discord.AllowedMentions.none())
                if isinstance(getattr(message, 'id', None), int):
                    self.deliveries[message.id] = delivery
                timing_logger.info('Casino render correlation=%s compose_ms=%.1f update_ms=%.1f version=%s',
                             correlation_id(), (composed-started)*1000, (time.perf_counter()-composed)*1000, delivery.version)
                return True
        finally:
            add_time("update_ms", time.perf_counter()-composed)
            for attachment in attachments:
                attachment.close()
