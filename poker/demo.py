"""Explicit local TEST demonstration; never started by the production entry point."""
import argparse
import os
from pathlib import Path
import httpx
import uvicorn
from fastapi.responses import RedirectResponse
from .app import create_app
from .config import Config


def demo_app(path, port=8765, eligible=False):
    if os.environ.get('POKER_ENV') != 'test':
        raise ValueError('Demo requires explicit POKER_ENV=test')
    config = Config(data_dir=path.resolve(), environment='test', origin='http://127.0.0.1:'+str(port), client_id='123', guild_id='456', client_secret='test-secret-only-0000', bot_token='test-bot-only-000000', reader_token='test-read-only-00000', funds_token='test-funds-only-0000')
    def discord(request):
        if request.url.path.endswith('/oauth2/token'):
            return httpx.Response(200, json={'access_token':'demo-only'})
        if request.url.path.endswith('/users/@me'):
            return httpx.Response(200, json={'id':'123456789012345678'})
        return httpx.Response(200, json={})
    app = create_app(config, transport=httpx.MockTransport(discord), initialize=True)
    @app.middleware('http')
    async def simulated_authorization(request, call_next):
        response = await call_next(request)
        if request.url.path == '/auth/login' and response.status_code == 303:
            from urllib.parse import parse_qs, urlparse
            state = parse_qs(urlparse(response.headers['location']).query)['state'][0]
            response.headers['location'] = '/auth/callback?code=demo&state='+state
        if request.url.path == '/auth/callback' and response.status_code == 303 and eligible:
            await app.state.store.command('demo-opening-loss', 'adjust', user_id='123456789012345678', amount='-49000', actor='123', reason='Explicit TEST demonstration of subsidy')
        return response
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--eligible', action='store_true')
    args = parser.parse_args()
    uvicorn.run(demo_app(args.data_dir, args.port, args.eligible), host='127.0.0.1', port=args.port, workers=1, access_log=False, proxy_headers=False, ws_max_size=4096)


if __name__ == '__main__':
    main()