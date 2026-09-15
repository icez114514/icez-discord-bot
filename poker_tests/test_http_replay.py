import tempfile
import unittest
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import httpx
from fastapi.testclient import TestClient
from poker.app import create_app
from poker.config import Config


class ReplayTests(unittest.TestCase):
    def test_http_replay_returns_original_result_after_account_changes(self):
        def discord(request):
            if request.url.path.endswith("/oauth2/token"):
                return httpx.Response(200, json={"access_token": "fake"})
            return httpx.Response(200, json={"id": "111"})

        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                data_dir=Path(directory),
                environment="test",
                origin="http://testserver",
                client_id="123",
                guild_id="456",
                client_secret="s" * 32,
                bot_token="b" * 32,
                reader_token="r" * 32,
                funds_token="f" * 32,
            )
            app = create_app(
                config, transport=httpx.MockTransport(discord), initialize=True
            )
            with TestClient(app) as client:
                location = client.get("/auth/login", follow_redirects=False).headers[
                    "location"
                ]
                state = parse_qs(urlparse(location).query)["state"][0]
                client.get("/auth/callback", params={"code": "x", "state": state})
                client.portal.call(
                    partial(
                        app.state.store.command,
                        "debit",
                        "adjust",
                        user_id="111",
                        amount="-49000",
                        reason="Replay test",
                        actor="999",
                    )
                )
                body = {"command_id": "help"}
                original = client.post(
                    "/api/subsidy", json=body, headers={"origin": config.origin}
                )
                self.assertEqual(original.status_code, 200)
                client.portal.call(
                    partial(
                        app.state.store.command,
                        "credit",
                        "adjust",
                        user_id="111",
                        amount="100",
                        reason="Replay test",
                        actor="999",
                    )
                )
                repeated = client.post(
                    "/api/subsidy", json=body, headers={"origin": config.origin}
                )
                self.assertEqual(repeated.json(), original.json())
                self.assertEqual(client.get("/api/account").json()["available"], "5100")
