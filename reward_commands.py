"""Legacy reward text command with live role checks and atomic accounting."""
import asyncio
import logging
import re

import discord

from crystal_rules import CRYSTAL_EMOJI
from database import DatabaseError, MAX_ID
from latency import operation, discord_update, mark_status

ROLE_IDS = {433683517235265537, 439412731632680960}
THRESHOLD = 'LV.10 女武神．戰車'


class RewardError(ValueError):
    pass


def parse_reward(content):
    parts = content.split()
    if len(parts) < 2:
        raise RewardError('請指定對象。')
    if len(parts) < 3:
        raise RewardError('請輸入給予的水晶數量。')
    if len(parts) != 3 or not re.fullmatch(r'[0-9]+', parts[2]) or int(parts[2]) <= 0:
        raise RewardError('請輸入正整數，不接受小數、科學記號或混雜文字。')
    target = parts[1]
    if target != 'all':
        match = re.fullmatch(r'<@!?([0-9]+)>', target)
        if match is None or not 0 < int(match[1]) <= MAX_ID:
            raise RewardError('請以 @成員 指定對象，或使用 all。')
        target = int(match[1])
    return target, int(parts[2])


def role_ids(member):
    # discord.py Member.roles resolves through the guild role cache; _roles retains
    # the raw IDs from the fresh REST response, including roles not cached yet.
    return set(member._roles)


class RewardFeature:
    def __init__(self, store):
        self.store = store

    async def on_message(self, message):
        if (message.guild is None or message.author.bot or message.webhook_id is not None
                or not message.content.split() or message.content.split()[0] != 'reward'):
            return
        await self.respond(message)

    async def send(self, message, text):
        await discord_update(message.channel.send(text, allowed_mentions=discord.AllowedMentions.none()))

    async def authorized(self, guild, uid):
        member = await guild.fetch_member(uid)
        if not role_ids(member) & ROLE_IDS:
            raise RewardError('需要**GM**權限')

    async def recipients(self, guild, target):
        if target != 'all':
            try:
                member = await guild.fetch_member(target)
            except discord.NotFound as error:
                if error.code != 10007:
                    raise
                raise RewardError('對象不存在。') from None
            return {member.id: member.display_name}
        roles = await guild.fetch_roles()
        threshold = next((role for role in roles if role.name == THRESHOLD), None)
        if threshold is None:
            raise RewardError('找不到 LV.10 女武神．戰車 角色，已取消全體發獎。')
        eligible_roles = {r.id for r in roles if r.hoist and r.position >= threshold.position}
        ids = iter(await self.store.account_ids())
        result = {}
        async def worker():
            for uid in ids:
                try:
                    member = await guild.fetch_member(uid)
                except discord.NotFound as error:
                    if error.code != 10007:
                        raise
                    continue
                if role_ids(member) & eligible_roles:
                    result[uid] = member.display_name
        workers = [asyncio.create_task(worker()) for _ in range(4)]
        try:
            await asyncio.gather(*workers)
        finally:
            for task in workers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        return result

    @operation('reward.message')
    async def respond(self, message):
        try:
            try:
                await self.authorized(message.guild, message.author.id)
                target, amount = parse_reward(message.content)
                if self.store is None:
                    raise DatabaseError('Reward storage is unavailable.')
                result = await self.store.find(message.id)
                if result is None:
                    recipients = await self.recipients(message.guild, target)
                    if not recipients:
                        await self.send(message, '沒有符合資格的成員')
                        return
                    # Batch REST discovery may take time; recheck before committing.
                    await self.authorized(message.guild, message.author.id)
                    result = await self.store.grant(message.id,message.author.id,message.guild.id,
                        message.channel.id,'all' if target == 'all' else 'single',amount,recipients)
                amount_text = str(result.amount)
                if len(amount_text) > 100:
                    amount_text = amount_text[:30] + '…（完整數量已保存於發獎流水）'
                await self.send(message, f'{CRYSTAL_EMOJI}已發放給 {result.count} 位成員，每人 {amount_text} 水晶。')
            except RewardError as error:
                mark_status('rejected')
                await self.send(message, str(error))
            except DatabaseError:
                mark_status('database_error')
                await self.send(message, '發獎結果暫時無法確認，請管理員查核發獎流水；不要另發新指令重試。')
            except discord.HTTPException:
                mark_status('discord_error')
                logging.warning('Reward Discord request failed; no financial operation retried.')
                await self.send(message, '成員查詢或回覆失敗；如已發放則不會重發，請查核發獎流水。')
        except discord.HTTPException:
            logging.warning('Reward response delivery failed; no financial operation retried.')
