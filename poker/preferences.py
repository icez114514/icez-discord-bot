"""Account-only visual preferences, independent of gameplay and funds."""

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from .sessions import authenticate
from typing import Literal

THEMES = ("classic_walnut", "midnight_oak", "burgundy_leather")


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    theme: str | None = Field(default=None, max_length=64)
    voice_pack: Literal["oneesan", "shoujo", "nekomimi"] | None = None


def install(app, cookie):
    async def preference(token, theme=None, voice_pack=None):
        def operation(db):
            user = authenticate(db, token)
            if theme is not None:
                selected = theme if theme in THEMES else THEMES[0]
                db.execute(
                    "INSERT INTO account_preferences VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme",
                    (user, selected),
                )
            if voice_pack is not None:
                db.execute(
                    "INSERT INTO account_voices VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET voice_pack=excluded.voice_pack",
                    (user, voice_pack),
                )
            voice = db.execute("SELECT voice_pack FROM account_voices WHERE user_id=?", (user,)).fetchone()
            row = db.execute(
                "SELECT theme FROM account_preferences WHERE user_id=?", (user,)
            ).fetchone()
            return {"theme": row[0] if row and row[0] in THEMES else THEMES[0], "voice_pack": voice[0] if voice else None}

        return await app.state.store.run(operation)

    @app.get("/api/preferences")
    async def get_preferences(request: Request):
        return await preference(request.cookies.get(cookie, ""))

    @app.put("/api/preferences")
    async def save_preferences(data: Preferences, request: Request):
        return await preference(request.cookies.get(cookie, ""), data.theme, data.voice_pack)
