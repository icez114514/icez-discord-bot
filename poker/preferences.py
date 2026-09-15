"""Account-only visual preferences, independent of gameplay and funds."""

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field

from .sessions import authenticate

THEMES = ("classic_walnut", "midnight_oak", "burgundy_leather")


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    theme: str = Field(max_length=64)


def install(app, cookie):
    async def preference(token, theme=None):
        def operation(db):
            user = authenticate(db, token)
            if theme is not None:
                selected = theme if theme in THEMES else THEMES[0]
                db.execute(
                    "INSERT INTO account_preferences VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme",
                    (user, selected),
                )
            row = db.execute(
                "SELECT theme FROM account_preferences WHERE user_id=?", (user,)
            ).fetchone()
            return {"theme": row[0] if row and row[0] in THEMES else THEMES[0]}

        return await app.state.store.run(operation)

    @app.get("/api/preferences")
    async def get_preferences(request: Request):
        return await preference(request.cookies.get(cookie, ""))

    @app.put("/api/preferences")
    async def save_preferences(data: Preferences, request: Request):
        return await preference(request.cookies.get(cookie, ""), data.theme)
