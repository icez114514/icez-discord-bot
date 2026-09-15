import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import httpx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from poker.app import create_app
from poker.config import Config
from poker.internal import create_internal


class SecurityTests(unittest.TestCase):
    def test_nonmember_and_api_errors_never_log_in(self):
        for code, status, guild_status in ((10007,404,200),(10007,404,403),(10004,404,200),(0,401,200),(0,403,200),(0,429,200),(0,500,200)):
            with self.subTest(code=code, status=status, guild=guild_status), tempfile.TemporaryDirectory() as directory:
                def discord(request):
                    if request.url.path.endswith('/oauth2/token'):
                        return httpx.Response(200, json={'access_token':'secret'})
                    if request.url.path.endswith('/users/@me'):
                        return httpx.Response(200, json={'id':'111'})
                    if '/members/' in request.url.path:
                        return httpx.Response(status, json={'code':code})
                    return httpx.Response(guild_status, json={})
                config = self.config(directory)
                with TestClient(create_app(config, transport=httpx.MockTransport(discord), initialize=True)) as client:
                    auth = client.get('/auth/login', follow_redirects=False)
                    state = parse_qs(urlparse(auth.headers['location']).query)['state'][0]
                    response = client.get('/auth/callback', params={'state':state,'code':'x'}, follow_redirects=False)
                    self.assertEqual(response.status_code, 403 if status==404 and code==10007 and guild_status==200 else 503)
                    self.assertEqual(client.get('/api/account').status_code,401)
                    with self.assertRaises(WebSocketDisconnect):
                        with client.websocket_connect('/ws/presence', headers={'origin':config.origin}):
                            pass

    def config(self, directory, **extra):
        return Config(data_dir=Path(directory), environment='test', origin='http://testserver', client_id='123', client_secret='s'*32, bot_token='b'*32, guild_id='456', reader_token='r'*32, funds_token='f'*32, funds_admins=('999',), **extra)

    def test_internal_api_requires_loopback_credentials_and_funds_role(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(directory)
            app = create_app(config, initialize=True)
            with TestClient(app) as public:
                self.assertEqual(public.get('/accounts/111').status_code,404)
                public.portal.call(app.state.store.login, '111')
                api = create_internal(config,app)
                with TestClient(api,client=('127.0.0.1',45000)) as internal:
                    body={'command_id':'one','user_id':'111','amount':'1','reason':'test'}
                    self.assertEqual(internal.get('/accounts/111').status_code,403)
                    self.assertEqual(internal.post('/adjustments',json=body,headers={'authorization':'Bearer '+config.reader_token,'x-actor-id':'999'}).status_code,403)
                    self.assertEqual(internal.post('/adjustments',json=body,headers={'authorization':'Bearer '+config.funds_token,'x-actor-id':'888'}).status_code,403)
                    self.assertEqual(internal.post('/adjustments',json=body,headers={'authorization':'Bearer '+config.funds_token,'x-actor-id':'999'}).status_code,200)
                    response = internal.post('/adjustments',json=body,headers={'authorization':'Bearer '+config.funds_token,'x-actor-id':'999'})
                    self.assertEqual(response.json()['available'], '50001')
                    self.assertEqual(internal.get('/scans',headers={'authorization':'Bearer '+config.reader_token}).status_code,200)
                with TestClient(api,client=('192.0.2.1',45000)) as remote:
                    self.assertEqual(remote.get('/scans',headers={'authorization':'Bearer '+config.reader_token}).status_code,403)

    def test_production_rejects_test_overrides(self):
        from dataclasses import replace
        config = replace(self.config(str(Path.home() / '.poker-test-unused')), environment='production', origin='https://poker.example')
        with self.assertRaisesRegex(ValueError,'test_overrides_forbidden'):
            create_app(config,initialize=True)