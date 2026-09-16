"""Session-bound statistics and explicitly allowlisted management routes."""

from fastapi import Request, Query
from pydantic import BaseModel, ConfigDict, Field

from .management import Management, roles
from .sessions import authenticate
from .statistics import query
from .store import Unauthorized


class ManagementCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    action: str = Field(pattern=r"^(adjust|disable|close|remove|rebuild)$")
    target: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)
    amount: str | None = Field(default=None, pattern=r"^-?(0|[1-9][0-9]{0,15})$")


def install(app, config, cookie):
    @app.get("/api/statistics")
    async def statistics(
        request: Request,
        period: str = "all",
        opponents: str = "all",
        user_id: str | None = None,
    ):
        def operation(db):
            user = authenticate(db, request.cookies.get(cookie, ""))
            if user_id is not None and user_id != user:
                raise Unauthorized("personal_statistics_only")
            return query(db, user, period, opponents)

        return await app.state.store.run(operation)

    @app.get("/api/roles")
    async def capabilities(request: Request):
        return await app.state.store.run(
            lambda db: roles(config, authenticate(db, request.cookies.get(cookie, "")))
        )

    @app.get("/api/management")
    async def management(request: Request):
        return await Management(app.state.store, config).view(
            request.cookies.get(cookie, "")
        )

    @app.post("/api/management/commands")
    async def command(body: ManagementCommand, request: Request):
        return await Management(app.state.store, config).command(
            body.model_dump(), token=request.cookies.get(cookie, "")
        )

    @app.get("/api/management/audit")
    async def history(
        request: Request,
        user_id: str | None = None,
        after: int = Query(default=0, ge=0),
    ):
        return await Management(app.state.store, config).history(
            request.cookies.get(cookie, ""), user_id, after
        )

    @app.get("/api/management/ledger/{user_id}")
    async def ledger(
        user_id: str, request: Request, after: int = Query(default=0, ge=0)
    ):
        return await Management(app.state.store, config).ledger(
            request.cookies.get(cookie, ""), user_id, after
        )
