"""Operator commands never accept passwords or bearer tokens on argv."""
import asyncio
import getpass
import json
import time

import httpx

from .backups import file_hash, restore, take_backup
from .operations import maintenance
from .store import Store


async def request(config, method, route, actor=""):
    headers = {"Authorization": "Bearer " + (config.funds_token if method == "POST" else config.reader_token)}
    if actor:
        headers["X-Actor-ID"] = actor
    async with httpx.AsyncClient(trust_env=False, timeout=120) as client:
        response = await client.request(method, f"http://127.0.0.1:{config.internal_port}" + route, headers=headers)
        if response.status_code != 200:
            raise ValueError("local_operation_rejected_" + str(response.status_code))
        return response.json()


async def operate(args, config):
    command = args.command
    if command in ("status", "drain", "resume"):
        if command == "drain":
            maintenance(config, True)
        state = await request(config, "GET", "/operations")
        if command == "resume":
            if state["frozen_tables"]:
                raise ValueError("resume_requires_recovery_investigation")
            if state["npc"]["status"] != "ready" or state["backup"]["error"] or not state["backup"]["completed_at"]:
                raise ValueError("resume_requires_healthy_npc_and_backup")
            if time.time() - state["backup"]["completed_at"] > 900:
                raise ValueError("resume_requires_recent_backup")
            maintenance(config, False)
            state = await request(config, "GET", "/operations")
        print(json.dumps(state, indent=2))
        if command == "drain" and state["active_hands"]:
            print("Maintenance enabled; hands still active. Wait for status active_hands=0 before stopping.")
    elif command == "backup":
        try:
            result = await request(config, "POST", "/backup", args.actor)
        except httpx.ConnectError:
            async with Store(config.data_dir / "poker.db") as store:
                result = await take_backup(store, config.backup_dir)
        print(json.dumps(result, indent=2))
    elif command in ("export", "decrypt"):
        if args.source is None or args.destination is None:
            raise ValueError("source_and_destination_required")
        from .encryption import transform
        password = getpass.getpass("Export password (12+ characters): ")
        if command == "export" and getpass.getpass("Confirm password: ") != password:
            raise ValueError("password_confirmation_mismatch")
        await asyncio.to_thread(transform, args.source, args.destination, password, command == "decrypt")
        print(json.dumps({"sha256": file_hash(args.destination), "status": "completed"}))
    elif command == "restore":
        if args.source is None or args.destination is None or not args.sha256:
            raise ValueError("source_destination_and_trusted_sha256_required")
        result = await asyncio.to_thread(restore, args.source, args.destination, args.sha256)
        print(json.dumps({**result, "maintenance": True, "status": "restore_completed"}))
