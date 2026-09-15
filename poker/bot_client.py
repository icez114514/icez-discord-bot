"""Optional Bot adapter. It has no SQLite dependency and never imports the store."""

import httpx


class PokerClient:
    def __init__(self, reader_token, funds_token, port=8766):
        self.base = "http://127.0.0.1:" + str(port)
        self.reader_token = reader_token
        self.funds_token = funds_token

    async def account(self, user_id):
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(
                self.base + "/accounts/" + str(user_id),
                headers={"Authorization": "Bearer " + self.reader_token},
            )
            response.raise_for_status()
            return response.json()

    async def adjust(self, *, actor_id, user_id, amount, command_id, reason):
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.post(
                self.base + "/adjustments",
                headers={
                    "Authorization": "Bearer " + self.funds_token,
                    "X-Actor-ID": str(actor_id),
                },
                json={
                    "user_id": str(user_id),
                    "amount": str(amount),
                    "command_id": command_id,
                    "reason": reason,
                },
            )
            response.raise_for_status()
            return response.json()
