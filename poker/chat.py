"""Table-local text chat, serialized independently of poker commands and events."""
import hashlib
import json
import secrets
import time
from pydantic import BaseModel, ConfigDict, Field
from .sessions import authenticate
from .store import Conflict
from .tables import accessible, load, save

class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    table_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    client_message_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(max_length=2000)

def authorized(db, token, table_id):
    user = authenticate(db, token)
    table = load(db, table_id)
    accessible(table, user, spectator=True)
    if user.startswith("npc:"):
        raise Conflict("chat_unavailable")
    return user, table

async def history(store, token, table_id, after=0):
    def operation(db):
        _, table = authorized(db, token, table_id)
        messages = [] if table["closed"] else table.get("chat", [])
        return {"type": "chat", "table_id": table_id, "closed": table["closed"],
                "sequence": table.get("chat_sequence", 0),
                "messages": [m for m in messages if m["sequence"] > after]}
    return await store.run(operation)

async def send(store, profiles, token, data):
    user = await store.run(lambda db: authorized(db, token, data.table_id)[0])
    names = profiles.view([user])
    author = {"id": user, "display_name": names[0]["display_name"] if names else "玩家"}
    text = data.text.strip()
    if not text or len(text) > 200 or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise Conflict("chat_invalid_text")
    fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
    key = "chat:" + hashlib.sha256(f"{data.table_id}:{user}:{data.client_message_id}".encode()).hexdigest()
    def operation(db):
        actual, table = authorized(db, token, data.table_id)
        if actual != user or table["closed"]:
            raise Conflict("chat_closed")
        old = db.execute("SELECT fingerprint,result FROM game_commands WHERE command_id=?", (key,)).fetchone()
        if old:
            if old["fingerprint"] != fingerprint:
                raise Conflict("chat_message_conflict")
            receipt = json.loads(old["result"])
            message = next((m for m in table.get("chat", []) if m["id"] == receipt["id"]), None)
            return {"receipt": receipt, "message": message}
        now = time.time()
        rates = {uid: [t for t in stamps if t > now - 60] for uid, stamps in table.get("chat_rates", {}).items()}
        rates = {uid: stamps for uid, stamps in rates.items() if stamps}
        stamps = rates.get(user, [])
        if stamps and (now - stamps[-1] < 1 or len(stamps) >= 10):
            raise Conflict("chat_rate_limited")
        sequence = table.get("chat_sequence", 0) + 1
        message = {"id": secrets.token_urlsafe(18), "sequence": sequence, "author": author,
                   "created_at": now, "text": text, "client_message_id": data.client_message_id}
        receipt = {"id": message["id"], "sequence": sequence, "table_id": data.table_id}
        rates[user] = [*stamps, now]
        table.update(chat=[*table.get("chat", []), message][-100:], chat_sequence=sequence, chat_rates=rates)
        save(db, table)
        db.execute("INSERT INTO game_commands VALUES(?,?,?)", (key, fingerprint, json.dumps(receipt)))
        return {"receipt": receipt, "message": message}
    return await store.run(operation)
