"""Discord is an external boundary: errors never become evidence of departure."""

import asyncio
import time
import httpx
from .store import Unauthorized


class Discord:
    def __init__(self, config, client):
        self.config = config
        self.client = client
        self.lock = asyncio.Lock()
        self.retry_at = 0.0

    async def request(self, method, path, **kwargs):
        async with self.lock:
            if time.monotonic() < self.retry_at:
                return None
            try:
                response = await self.client.request(
                    method, "https://discord.com/api/v10" + path, **kwargs
                )
                if response.status_code == 429:
                    try:
                        delay = float(response.json().get("retry_after", 60))
                    except (ValueError, TypeError, AttributeError):
                        delay = 60
                    self.retry_at = time.monotonic() + max(1, min(delay, 3600))
                elif response.headers.get("x-ratelimit-remaining") == "0":
                    try:
                        self.retry_at = time.monotonic() + max(
                            0,
                            float(response.headers.get("x-ratelimit-reset-after", "1")),
                        )
                    except ValueError:
                        self.retry_at = time.monotonic() + 1
                return response
            except httpx.HTTPError:
                return None

    async def identity(self, code):
        response = await self.request(
            "POST",
            "/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.callback,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
        )
        try:
            if response is None or response.status_code != 200:
                raise Unauthorized("discord_login_unavailable")
            token = response.json()["access_token"]
            response = await self.request(
                "GET", "/users/@me", headers={"Authorization": "Bearer " + token}
            )
            if response is None or response.status_code != 200:
                raise Unauthorized("discord_login_unavailable")
            user = response.json()["id"]
            if (
                not isinstance(user, str)
                or not user.isascii()
                or not user.isdigit()
                or len(user) > 20
            ):
                raise Unauthorized("discord_login_unavailable")
            return user
        except (KeyError, ValueError, TypeError) as error:
            raise Unauthorized("discord_login_unavailable") from error

    async def eligible(self, user):
        if str(user) in self.config.allowed_user_ids:
            return "member"
        return await self.member(user)

    async def member(self, user):
        # Only proven absence in every allowed guild is evidence of departure.
        results = []
        for guild in self.config.allowed_guild_ids:
            result = await self._member_in_guild(user, guild)
            if result == "member":
                return "member"
            results.append(result)
        return "absent" if all(result == "absent" for result in results) else "retry"

    async def _member_in_guild(self, user, guild_id):
        headers = {"Authorization": "Bot " + self.config.bot_token}
        response = await self.request(
            "GET",
            "/guilds/" + guild_id + "/members/" + user,
            headers=headers,
        )
        if response is not None and response.status_code == 200:
            return "member"
        try:
            absent = (
                response is not None
                and response.status_code == 404
                and response.json().get("code") == 10007
            )
        except (ValueError, AttributeError):
            absent = False
        if absent:
            guild = await self.request(
                "GET", "/guilds/" + guild_id, headers=headers
            )
            if guild is not None and guild.status_code == 200:
                return "absent"
        return "retry"
