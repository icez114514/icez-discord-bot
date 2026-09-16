"""Public ASGI boundary. No money-engine or internal admin endpoints are mounted here."""

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from .discord_api import Discord
from .profiles import Profiles
from .eligibility import Eligibility
from .store import Store, Conflict, Unauthorized

log = logging.getLogger("poker")
COOKIE = "poker_session"


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


def create_app(config, transport=None, initialize=False):
    config.validate()
    if config.environment != "test" and (transport is not None or initialize):
        raise ValueError("test_overrides_forbidden")

    @asynccontextmanager
    async def lifespan(app):
        async with (
            Store(config.data_dir / "poker.db", initialize=initialize) as store,
            httpx.AsyncClient(
                timeout=8, transport=transport, follow_redirects=False, trust_env=False
            ) as client,
        ):
            app.state.store = store
            app.state.backup = {"completed_at": None, "error": None}
            app.state.timing = {"max_loop_delay_ms": 0.0, "max_wall_clock_step_ms": 0.0}
            app.state.discord = Discord(config, client)
            app.state.profiles = Profiles(app.state.discord)
            app.state.scan = Eligibility(store, app.state.discord)
            await app.state.scan.recover()
            from .tables import Tables
            from .npc import NPC
            from .table_api import run_tables

            app.state.tables = Tables(store)
            await app.state.tables.recover()
            app.state.npc = NPC()
            try:
                await app.state.npc.start()
            except Exception:
                log.error("fixed_npc_unavailable_at_startup")
            backup_task = None
            if config.backup_dir is not None:
                from .backups import schedule
                backup_task = asyncio.create_task(schedule(store, config.backup_dir, app.state.backup))
            game_task = asyncio.create_task(run_tables(app.state.tables, app.state.npc))
            from .operations import monitor_timing
            timing_task = asyncio.create_task(monitor_timing(app.state.timing))

            async def scheduler():
                while True:
                    try:
                        await app.state.scan.run()
                    except Exception as error:
                        log.error("membership_job_failed type=%s", type(error).__name__)
                    await asyncio.sleep(1)

            task = (
                asyncio.create_task(scheduler())
                if config.environment != "test"
                else None
            )
            try:
                yield
            finally:
                timing_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await timing_task
                if backup_task:
                    backup_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await backup_task
                game_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await game_task
                await app.state.npc.close()
                await app.state.profiles.close()
                if task:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security(request: Request, call_next):
        if (
            request.method not in ("GET", "HEAD", "OPTIONS")
            and request.headers.get("origin") != config.origin
        ):
            return JSONResponse({"error": "origin_rejected"}, status_code=403)
        if request.headers.get(
            "sec-fetch-site"
        ) == "cross-site" and request.url.path.startswith("/api/"):
            return JSONResponse({"error": "origin_rejected"}, status_code=403)
        try:
            response = await call_next(request)
        except Exception as error:
            incident = secrets.token_hex(8)
            log.error(
                "request_failed incident=%s type=%s", incident, type(error).__name__
            )
            response = JSONResponse(
                {"error": "service_unavailable", "incident": incident}, status_code=503
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https://cdn.discordapp.com; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(Unauthorized)
    async def unauthorized(request, error):
        return JSONResponse({"error": str(error)}, status_code=401)

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse({"error": str(error)}, status_code=409)

    @app.get("/api/environment")
    async def environment():
        return {"environment": config.environment}

    @app.get("/health")
    async def health():
        await app.state.store.run(lambda db: db.execute("SELECT 1").fetchone())
        return {"status": "ok", "schema": 4, "maintenance": app.state.store.maintenance}

    @app.get("/auth/login")
    async def login():
        state, browser = await app.state.store.oauth_begin()
        response = RedirectResponse(
            "https://discord.com/oauth2/authorize?"
            + urlencode(
                {
                    "client_id": config.client_id,
                    "response_type": "code",
                    "scope": "identify",
                    "redirect_uri": config.callback,
                    "state": state,
                }
            ),
            status_code=303,
        )
        response.set_cookie(
            "poker_oauth",
            browser,
            max_age=600,
            httponly=True,
            secure=config.secure,
            samesite="lax",
            path="/auth",
        )
        return response

    @app.get("/auth/callback")
    async def callback(request: Request, state: str = "", code: str = ""):
        if not code or len(code) > 2048 or len(state) > 128:
            raise Unauthorized("invalid_oauth_callback")
        await app.state.store.oauth_consume(
            state, request.cookies.get("poker_oauth", "")
        )
        user = await app.state.discord.identity(code)
        member = await app.state.discord.member(user)
        if member != "member":
            return JSONResponse(
                {
                    "error": "guild_membership_required"
                    if member == "absent"
                    else "discord_verification_unavailable"
                },
                status_code=403 if member == "absent" else 503,
            )
        token = await app.state.store.login(user)
        response = RedirectResponse("/", status_code=303)
        # The cookie persists; the server never expires the local session on a daily schedule.
        response.set_cookie(
            COOKIE,
            token,
            max_age=34560000,
            httponly=True,
            secure=config.secure,
            samesite="lax",
            path="/",
        )
        response.delete_cookie("poker_oauth", path="/auth")
        return response

    @app.get("/api/account")
    async def account(request: Request):
        return {
            **await app.state.store.account_for_session(
                request.cookies.get(COOKIE, "")
            ),
            "environment": config.environment,
        }

    @app.post("/api/subsidy")
    async def subsidy(command: Command, request: Request):
        token = request.cookies.get(COOKIE, "")
        user = await app.state.store.authenticate(token)
        result = await app.state.store.command(
            "subsidy:" + user + ":" + command.command_id,
            "subsidy",
            user_id=user,
            session=token,
        )
        return {**result, "environment": config.environment}

    @app.post("/auth/logout")
    async def logout(request: Request):
        await app.state.store.logout(request.cookies.get(COOKIE, ""))
        response = JSONResponse({"status": "logged_out_all_devices"})
        response.delete_cookie(COOKIE)
        return response

    @app.websocket("/ws/presence")
    async def presence(socket: WebSocket):
        token = socket.cookies.get(COOKIE, "")
        connection = secrets.token_urlsafe(24)
        entered = False
        try:
            if socket.headers.get("origin") != config.origin:
                await socket.close(code=4403)
                return
            await app.state.store.authenticate(token)
            await socket.accept()
            await app.state.store.presence(token, connection, "enter")
            entered = True
            await socket.send_json({"type": "ready", "heartbeat_seconds": 30})
            while True:
                try:
                    message = await asyncio.wait_for(socket.receive_json(), timeout=1)
                except asyncio.TimeoutError:
                    await app.state.store.authenticate(token)
                    continue
                if not isinstance(message, dict) or message.get("type") not in (
                    "heartbeat",
                    "leave",
                ):
                    await socket.close(code=4400)
                    break
                await app.state.store.presence(token, connection, message["type"])
                if message["type"] == "leave":
                    entered = False
                    await socket.close(code=1000)
                    break
                await socket.send_json({"type": "heartbeat"})
        except Unauthorized:
            await socket.close(code=4401)
        except (WebSocketDisconnect, ValueError):
            pass
        finally:
            if entered:
                with contextlib.suppress(Unauthorized, Conflict):
                    await app.state.store.presence(token, connection, "disconnect")

    if config.static_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=config.static_dir / "assets"),
            name="assets",
        )

    @app.get("/")
    async def index():
        if not (config.static_dir / "index.html").is_file():
            return JSONResponse({"error": "frontend_build_required"}, status_code=503)
        return FileResponse(config.static_dir / "index.html")

    from .table_api import install

    install(app, config, COOKIE)
    from .preferences import install as install_preferences

    install_preferences(app, COOKIE)
    from .statistics_api import install as install_statistics

    install_statistics(app, config, COOKIE)
    return app
