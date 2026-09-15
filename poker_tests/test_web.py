import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import httpx
from fastapi.testclient import TestClient
from poker.app import create_app
from poker.config import Config


class WebTests(unittest.TestCase):
    def test_oauth_state_membership_origin_and_revoked_websocket(self):
        def discord(request):
            if request.url.path.endswith("/oauth2/token"):
                return httpx.Response(200, json={"access_token": "external-secret"})
            if request.url.path.endswith("/users/@me"):
                return httpx.Response(200, json={"id": "123456789012345678"})
            return httpx.Response(200, json={"user": {"id": "123456789012345678"}})

        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                data_dir=Path(directory),
                environment="test",
                origin="http://testserver",
                client_id="123",
                client_secret="s" * 32,
                bot_token="b" * 32,
                guild_id="456",
                reader_token="r" * 32,
                funds_token="f" * 32,
            )
            app = create_app(
                config, transport=httpx.MockTransport(discord), initialize=True
            )
            with TestClient(app) as client:
                self.assertEqual(client.get("/api/account").status_code, 401)
                auth = client.get("/auth/login", follow_redirects=False)
                state = parse_qs(urlparse(auth.headers["location"]).query)["state"][0]
                self.assertEqual(
                    client.get("/auth/callback?code=x&state=wrong").status_code, 401
                )
                self.assertEqual(
                    client.get(
                        "/auth/callback",
                        params={"code": "x", "state": state},
                        follow_redirects=False,
                    ).status_code,
                    303,
                )
                self.assertEqual(
                    client.get("/api/account").json()["available"], "50000"
                )
                self.assertEqual(
                    client.post("/api/subsidy", json={"command_id": "one"}).status_code,
                    403,
                )
                with client.websocket_connect(
                    "/ws/presence", headers={"origin": config.origin}
                ) as websocket:
                    self.assertEqual(websocket.receive_json()["type"], "ready")
                    self.assertEqual(
                        client.post(
                            "/auth/logout", headers={"origin": config.origin}
                        ).status_code,
                        200,
                    )
                    websocket.send_json({"type": "heartbeat"})
                    from starlette.websockets import WebSocketDisconnect

                    with self.assertRaises(WebSocketDisconnect):
                        websocket.receive_json()
                self.assertEqual(client.get("/api/account").status_code, 401)
