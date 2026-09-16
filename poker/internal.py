"""Only the dedicated loopback listener mounts this application."""

import secrets
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from .store import Conflict, Unauthorized


class Adjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    user_id: str = Field(pattern=r"^[0-9]{1,20}$")
    amount: str = Field(pattern=r"^-?(0|[1-9][0-9]{0,15})$")
    reason: str = Field(min_length=1, max_length=500)


def create_internal(config, public):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authorize(request: Request, call_next):
        if (
            request.client is None
            or request.client.host not in ("127.0.0.1", "::1")
            or request.headers.get("origin")
        ):
            return JSONResponse({"error": "loopback_only"}, status_code=403)
        expected = (
            config.funds_token if request.method == "POST" else config.reader_token
        )
        if not secrets.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + expected
        ):
            return JSONResponse(
                {"error": "internal_credential_required"}, status_code=403
            )
        if (
            request.method == "POST"
            and request.headers.get("x-actor-id") not in config.funds_admins
        ):
            return JSONResponse({"error": "funds_role_required"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({"error": str(error)}, status_code=409)

    @app.exception_handler(Unauthorized)
    async def unauthorized(request, error):
        return JSONResponse({"error": str(error)}, status_code=404)

    @app.get("/accounts/{user_id}")
    async def account(user_id: str):
        return await public.state.store.account(user_id)

    @app.get("/statistics")
    async def statistics(request: Request, period: str = "all", opponents: str = "all", user_id: str | None = None):
        from .statistics import query

        actor = request.headers.get("x-actor-id", "")
        if (not actor.isdigit() or len(actor) > 20
                or request.headers.get("x-guild-id") != config.guild_id
                or (user_id is not None and user_id != actor)):
            raise Unauthorized("personal_statistics_only")
        if await public.state.discord.member(actor) != "member":
            raise Unauthorized("guild_membership_required")
        def operation(db):
            row = db.execute("SELECT disabled FROM accounts WHERE user_id=?", (actor,)).fetchone()
            if row and row[0]:
                raise Unauthorized("account_disabled")
            return query(db, actor, period, opponents)
        return await public.state.store.run(operation)

    @app.get("/scans")
    async def scans():
        return await public.state.scan.status()

    @app.post("/adjustments")
    async def adjust(body: Adjustment, request: Request):
        actor = request.headers["x-actor-id"]
        from .management import Management

        result = await Management(public.state.store, config).command(
            {"command_id": body.command_id, "action": "adjust", "target": body.user_id,
             "amount": body.amount, "reason": body.reason}, trusted_actor=actor)
        return result["result"]

    return app
