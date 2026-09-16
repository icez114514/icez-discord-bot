"""Bounded persistent subprocess; deployment must additionally restrict OS access."""

import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from pathlib import Path

from . import rules

log = logging.getLogger("poker.npc")


def action_log(hand):
    result = []
    for street in rules.STREETS[: rules.STREETS.index(hand["street"]) + 1]:
        if street != "preflop":
            result.append({"action": "deal"})
        for action in hand["history"]:
            if action["street"] != street:
                continue
            kind = "all_in" if action.get("all_in") else action["action"]
            result.append(
                {
                    "seat": action["seat"],
                    "action": kind,
                    "amount": action["raise_to"]
                    if kind in ("raise", "all_in")
                    else action["amount"],
                }
            )
    return result


def observation(hand):
    i = hand["actor"]
    p = hand["players"][i]
    legal = rules.legal(hand)
    return {
        "street": hand["street"],
        "dealer": hand["button"],
        "seat_to_act": i,
        "your_cards": p["cards"],
        "community_cards": hand["board"],
        "your_stack": p["stack"],
        "your_bet_this_street": p["bet"],
        "amount_owed": max(0, hand["current_bet"] - p["bet"]),
        "current_bet": hand["current_bet"],
        "pot": sum(q["paid"] for q in hand["players"]),
        "can_check": legal["check"],
        "min_raise_to": legal["min_raise_to"] if legal["raise"] else 0,
        "players": [
            {
                "seat": j,
                "stack": q["stack"],
                "bet_this_street": q["bet"],
                "is_folded": q["folded"],
                "is_all_in": q["stack"] == 0,
            }
            for j, q in enumerate(hand["players"])
        ],
        "action_log": action_log(hand),
    }


class NPC:
    def __init__(self):
        self.process = None
        self.lock = asyncio.Lock()
        self.waiting = 0
        self.status = "not_started"
        self.requests = 0
        self.timeouts = 0
        self.failures = 0

    async def start(self):
        root = Path(__file__).resolve().parent
        env = {
            key: os.environ[key]
            for key in ("SystemRoot", "WINDIR", "TEMP", "TMP")
            if key in os.environ
        }
        env.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-u",
            str(root / "npc_worker.py"),
            cwd=str(root / "vendor" / "fullhouse"),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=4096,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        try:
            assert self.process.stdout is not None
            response = json.loads(
                await asyncio.wait_for(self.process.stdout.readline(), 20)
            )
            if not response.get("ready"):
                raise RuntimeError(response.get("error", "npc_startup_failed"))
            self.status = "ready"
        except Exception:
            await self.close()
            self.status = "npc_startup_failed"
            log.error("fixed_npc_startup_failed")
            raise

    async def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.returncode is None:
                if os.name == "nt":
                    killer = await asyncio.create_subprocess_exec(
                        str(
                            Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
                        ),
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        creationflags=0x08000000,
                    )
                    await killer.wait()
                else:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
            if process.stdin is not None:
                process.stdin.close()
            await process.communicate()

    async def decide(self, hand):
        self.requests += 1
        remaining = min(2.0, hand["deadline"] - time.time())
        if self.waiting >= 8 or remaining <= 0:
            self.timeouts += 1
            return None, "npc_queue_deadline"
        self.waiting += 1
        try:

            async def request():
                async with self.lock:
                    if self.process is None or self.process.returncode is not None:
                        self.failures += 1
                        return None, "npc_unavailable"
                    self.process.stdin.write(
                        (json.dumps(observation(hand)) + "\n").encode()
                    )
                    await self.process.stdin.drain()
                    response = json.loads(await self.process.stdout.readline())
                    if "error" in response:
                        self.failures += 1
                        return None, response["error"]
                    decision = response.get("decision")
                    if not isinstance(decision, dict):
                        return None, "npc_invalid_response"
                    return decision, None

            return await asyncio.wait_for(request(), remaining)
        except (asyncio.TimeoutError, OSError, ValueError) as error:
            self.failures += 1
            if isinstance(error, asyncio.TimeoutError):
                self.timeouts += 1
            await self.close()  # Never consume an old reply as a subsequent decision.
            log.error("fixed_npc_request_failed")
            return None, "npc_timeout_or_protocol"
        finally:
            self.waiting -= 1
