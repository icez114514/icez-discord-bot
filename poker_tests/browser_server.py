"""Browser acceptance server: simulated Discord only; real service and game engine."""

import argparse
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import uvicorn

from poker.app import create_app
from poker.config import Config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8874)
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    config = Config(
        data_dir=args.data_dir.resolve(),
        environment="test",
        origin=f"http://127.0.0.1:{args.port}",
        client_id="123",
        guild_id="456",
        client_secret=secrets.token_hex(16),
        bot_token=secrets.token_hex(16),
        reader_token=secrets.token_hex(16),
        funds_token=secrets.token_hex(16),
        table_admins=("111111111111111111",),
        funds_admins=("111111111111111111",),
    )

    def discord(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(
                200,
                json={"access_token": parse_qs(request.content.decode())["code"][0]},
            )
        if request.url.path.endswith("/users/@me"):
            return httpx.Response(
                200, json={"id": request.headers["authorization"].split()[-1]}
            )
        if "/members/" in request.url.path:
            user = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"nick": "桌上的長暱稱測試玩家", "user": {"id": user, "username": "table_player", "avatar": None, "discriminator": "0"}})
        return httpx.Response(200, json={})

    app = create_app(config, transport=httpx.MockTransport(discord), initialize=True)

    @app.middleware("http")
    async def simulated_oauth(request, call_next):
        response = await call_next(request)
        if request.url.path == "/auth/login" and response.status_code == 303:
            state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
            identity = request.query_params.get("identity", "111111111111111111")
            if identity not in (
                "111111111111111111",
                "222222222222222222",
                "333333333333333333",
            ):
                identity = "111111111111111111"
            response.headers["location"] = (
                f"/auth/callback?code={identity}&state={state}"
            )
        return response

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        proxy_headers=False,
        ws_max_size=4096,
    )


if __name__ == "__main__":
    main()
