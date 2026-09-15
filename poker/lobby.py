"""Authenticated table discovery and atomic, idempotent table creation."""

import json
import secrets
import sqlite3
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .sessions import authenticate
from .store import Conflict
from .tables import (
    Transaction,
    all_tables,
    current_table,
    initial,
    member,
    public,
    save,
)


class CreateTable(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=40)
    private: bool = False
    amount: str = Field(pattern=r"^[1-9][0-9]{0,15}$")


async def create(tables, token, data):
    def operation(db):
        user = authenticate(db, token)
        cid = "create:" + user + ":" + data["command_id"]
        fingerprint = json.dumps(data, sort_keys=True)
        old = db.execute(
            "SELECT * FROM game_commands WHERE command_id=?", (cid,)
        ).fetchone()
        if old:
            result = (
                json.loads(old["result"])
                if old["fingerprint"] == fingerprint
                else {"error": "command_id_reused"}
            )
        else:
            db.execute("SAVEPOINT create_table")
            try:
                table = initial(secrets.token_hex(12))
                table.update(
                    name=data["name"].strip() or "50 / 100", private=data["private"]
                )
                if data["private"]:
                    table["invitation"] = secrets.token_urlsafe(32)
                Transaction(db, table, cid, time.time()).command(
                    user, {"kind": "join", "amount": data["amount"]}
                )
                table["version"] += 1
                save(db, table)
                result = {"accepted": True, "table_id": table["id"]}
                db.execute("RELEASE create_table")
            except (Conflict, sqlite3.IntegrityError) as error:
                db.execute("ROLLBACK TO create_table")
                db.execute("RELEASE create_table")
                result = {
                    "error": str(error)
                    if isinstance(error, Conflict)
                    else "funds_or_state_conflict"
                }
            db.execute(
                "INSERT INTO game_commands VALUES(?,?,?)",
                (cid, fingerprint, json.dumps(result)),
            )
        current = current_table(db, user)
        return {
            "result": result,
            "state": public(db, current, user) if current else {"joined": False},
        }

    return await tables.store.run(operation)


def install(app, cookie):
    install_invitations(app, cookie)

    @app.get("/api/tables")
    async def lobby(request: Request):
        def operation(db):
            user = authenticate(db, request.cookies.get(cookie, ""))
            current = current_table(db, user)
            return {
                "current_table": current["id"] if current else None,
                "capacity": 2,
                "tables": [
                    {
                        "id": t["id"],
                        "name": t.get("name", "50 / 100"),
                        "version": t["version"],
                        "seats": len({m["seat"] for m in t["members"]}),
                        "limit": 6,
                    }
                    for t in all_tables(db)
                    if not t.get("private") and not t["closed"] and t["members"]
                ],
            }

        return await app.state.store.run(operation)

    @app.post("/api/tables")
    async def create_table(data: CreateTable, request: Request):
        result = await create(
            app.state.tables, request.cookies.get(cookie, ""), data.model_dump()
        )
        return JSONResponse(
            result, status_code=409 if "error" in result["result"] else 200
        )


class RotateInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    control: str = Field(min_length=1, max_length=128)


def install_invitations(app, cookie):
    async def invitation(token, data=None):
        def operation(db):
            user = authenticate(db, token)
            table = current_table(db, user)
            if (
                not table
                or table["owner"] != user
                or not table.get("private")
                or table["closed"]
            ):
                raise Conflict("private_host_required")
            if data is not None:
                seat = member(table, user)
                if (
                    seat.get("control") != data["control"]
                    or seat.get("heartbeat", 0) + 30 <= time.time()
                ):
                    raise Conflict("not_control_endpoint")
                cid = "invite:" + user + ":" + data["command_id"]
                fingerprint = json.dumps(
                    {"table_id": table["id"], **data}, sort_keys=True
                )
                old = db.execute(
                    "SELECT * FROM game_commands WHERE command_id=?", (cid,)
                ).fetchone()
                if old and old["fingerprint"] != fingerprint:
                    raise Conflict("command_id_reused")
                if not old:
                    table["invitation"] = secrets.token_urlsafe(32)
                    save(db, table)
                    db.execute(
                        "INSERT INTO game_commands VALUES(?,?,?)",
                        (cid, fingerprint, "{}"),
                    )
            return {"table_id": table["id"], "invitation": table["invitation"]}

        return await app.state.store.run(operation)

    @app.get("/api/table/invitation")
    async def get_invitation(request: Request):
        return await invitation(request.cookies.get(cookie, ""))

    @app.post("/api/table/invitation")
    async def rotate_invitation(data: RotateInvitation, request: Request):
        return await invitation(request.cookies.get(cookie, ""), data.model_dump())
