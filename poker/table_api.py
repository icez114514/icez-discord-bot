"""Authenticated minimal table HTTP and per-account WebSocket projections."""

import asyncio
import contextlib
import logging
import secrets
from typing import Literal

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .store import Conflict, Unauthorized

log = logging.getLogger("poker.table")


class TableCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    table_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    version: int = Field(ge=0)
    kind: Literal[
        "join",
        "act",
        "topup",
        "leave",
        "sitout",
        "sit_in",
        "add_npc",
        "remove_npc",
        "close",
    ]
    invitation: str | None = Field(default=None, max_length=128)
    control: str | None = Field(default=None, max_length=128)
    hand_id: str | None = Field(default=None, max_length=128)
    turn: int | None = Field(default=None, ge=0)
    action: Literal["check", "call", "raise", "fold", "all_in"] | None = None
    amount: str | None = Field(default=None, pattern=r"^(0|[1-9][0-9]{0,15})$")
    npc_id: str | None = Field(default=None, max_length=128)

    def payload(self):
        data = self.model_dump()
        # Preserve fingerprints of pre-lobby commands across schema upgrades.
        if data["invitation"] is None:
            data.pop("invitation")
        return data

    @model_validator(mode="after")
    def required_fields(self):
        if self.kind in ("join", "topup") and self.amount is None:
            raise ValueError("amount_required")
        if self.kind == "act":
            if self.action is None or self.hand_id is None or self.turn is None:
                raise ValueError("action_hand_turn_required")
            if self.action == "raise" and self.amount is None:
                raise ValueError("amount_required")
        if self.kind == "remove_npc" and self.npc_id is None:
            raise ValueError("npc_id_required")
        return self


def install(app, config, cookie):
    from .lobby import install as install_lobby

    install_lobby(app, cookie)

    @app.get("/api/table")
    async def table(request: Request, table_id: str | None = None):
        return await app.state.tables.view(
            request.cookies.get(cookie, ""),
            table_id=table_id,
            invitation=request.headers.get("x-table-invitation"),
        )

    @app.post("/api/table/commands")
    async def command(data: TableCommand, request: Request):
        result = await app.state.tables.command(
            request.cookies.get(cookie, ""), data.payload()
        )
        return JSONResponse(
            result, status_code=409 if "error" in result["result"] else 200
        )

    @app.websocket("/ws/table")
    async def socket(socket: WebSocket):
        token = socket.cookies.get(cookie, "")
        connection = secrets.token_urlsafe(24)
        entered = False
        try:
            if socket.headers.get("origin") != config.origin:
                await socket.close(code=4403)
                return
            state = await app.state.tables.view(token)
            await socket.accept()
            await app.state.store.presence(token, connection, "enter")
            entered = True
            state = await app.state.tables.connection(token, connection, "enter")
            await socket.send_json(
                {"type": "ready", "connection": connection, "state": state}
            )
            while True:
                try:
                    message = await asyncio.wait_for(socket.receive_json(), 0.5)
                except asyncio.TimeoutError:
                    # Revalidates session even when a tab sends no further messages.
                    state = await app.state.tables.view(token, connection)
                    await socket.send_json({"type": "state", "state": state})
                    continue
                if not isinstance(message, dict):
                    await socket.close(code=4400)
                    break
                kind = message.get("type")
                if kind in ("heartbeat", "leave"):
                    await app.state.store.presence(token, connection, kind)
                    state = await app.state.tables.connection(token, connection, kind)
                    if kind == "leave":
                        entered = False
                        await socket.close(code=1000)
                        break
                    await socket.send_json({"type": "state", "state": state})
                elif kind == "command":
                    try:
                        data = TableCommand.model_validate(message.get("command"))
                        if data.control != connection:
                            raise Conflict("not_control_endpoint")
                        result = await app.state.tables.command(
                            token, data.payload()
                        )
                    except (Conflict, ValidationError) as error:
                        result = {
                            "result": {
                                "error": str(error)
                                if isinstance(error, Conflict)
                                else "invalid_command"
                            },
                            "state": await app.state.tables.view(token, connection),
                        }
                    await socket.send_json({"type": "result", **result})
                else:
                    await socket.close(code=4400)
                    break
        except Unauthorized:
            with contextlib.suppress(RuntimeError):
                await socket.close(code=4401)
        except (Conflict, ValidationError):
            with contextlib.suppress(RuntimeError):
                await socket.close(code=4400)
        except (WebSocketDisconnect, ValueError):
            pass
        finally:
            if entered:
                with contextlib.suppress(Unauthorized, Conflict):
                    await app.state.store.presence(token, connection, "disconnect")
                with contextlib.suppress(Unauthorized, Conflict):
                    await app.state.tables.connection(token, connection, "disconnect")


async def run_tables(tables, npc):
    pending = None
    try:
        while True:
            try:
                hand = await tables.tick()
                if pending is not None and pending.done():
                    await pending
                    pending = None
                if hand is not None and pending is None:

                    async def decide(current):
                        result, error = await npc.decide(current)
                        if error:
                            log.warning("fixed_npc_fallback reason=%s", error)
                        await tables.npc_result(
                            current["id"], current["turn"], result, error
                        )

                    pending = asyncio.create_task(decide(hand))
            except Exception as error:
                log.error("table_scheduler_failed type=%s", type(error).__name__)
                if pending is not None and pending.done():
                    pending = None
            await asyncio.sleep(0.1)
    finally:
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
