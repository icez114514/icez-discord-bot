"""Best-effort guild presentation data, independent of the game writer."""

import asyncio
import re
import time


def presentation(user_id, guild_id, member):
    user = member.get("user")
    if not isinstance(user, dict) or user.get("id") != user_id:
        return None
    nickname = member.get("nick")
    name = nickname.strip() if isinstance(nickname, str) else ""
    if not name:
        username = user.get("username")
        name = username.strip() if isinstance(username, str) else ""
    if not name:
        return None
    def valid_hash(value):
        return isinstance(value, str) and re.fullmatch(r"(?:a_)?[0-9a-f]{32}", value)
    if valid_hash(member.get("avatar")):
        asset = f"guilds/{guild_id}/users/{user_id}/avatars/{member['avatar']}"
    elif valid_hash(user.get("avatar")):
        asset = f"avatars/{user_id}/{user['avatar']}"
    else:
        discriminator = str(user.get("discriminator", "0"))
        index = int(discriminator) % 5 if discriminator.isdecimal() and discriminator != "0" else (int(user_id) >> 22) % 6
        asset = f"embed/avatars/{index}"
    return {"id": user_id, "display_name": name[:80], "avatar_url": f"https://cdn.discordapp.com/{asset}.png?size=128"}


class Profiles:
    def __init__(self, discord, clock=time.monotonic):
        self.discord = discord
        self.clock = clock
        self.cache = {}
        self.retry_at = {}
        self.tasks = {}

    def view(self, users):
        now = self.clock()
        # Bound the process-local cache without evicting players requested together.
        if len(self.retry_at) > 512:
            for user in list(self.retry_at):
                if user not in users and user not in self.tasks:
                    self.retry_at.pop(user, None)
                    self.cache.pop(user, None)
        for user in users:
            if user not in self.tasks and now >= self.retry_at.get(user, 0):
                self.tasks[user] = asyncio.create_task(self.refresh(user))
        return [self.cache[user] for user in users if user in self.cache]

    async def refresh(self, user):
        try:
            # Presentation never queues behind authentication/eligibility work.
            if self.discord.lock.locked():
                self.retry_at[user] = self.clock() + 2
                return
            response = await self.discord.request(
                "GET", f"/guilds/{self.discord.config.guild_id}/members/{user}",
                headers={"Authorization": "Bot " + self.discord.config.bot_token}, timeout=2,
            )
            profile = None
            if response is not None and response.status_code == 200:
                profile = presentation(user, self.discord.config.guild_id, response.json())
            if profile:
                self.cache[user] = profile
            self.retry_at[user] = self.clock() + (300 if profile else 60)
        except (ValueError, TypeError, AttributeError):
            self.retry_at[user] = self.clock() + 60
        finally:
            self.tasks.pop(user, None)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
