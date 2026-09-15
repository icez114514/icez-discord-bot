"""python -m poker check | migrate | serve. Ctrl+C stops both listeners."""

import argparse
import asyncio
import logging
import os
import sqlite3
from .config import Config
from .store import Store


async def migrate(config):
    async with Store(config.data_dir / "poker.db", initialize=True):
        print("Poker schema version 1 ready")


async def serve(config):
    import uvicorn
    from .app import create_app
    from .internal import create_internal

    public = create_app(config)
    internal = create_internal(config, public)

    # One process and event loop. Internal API has no independently managed store.
    def server(app, port):
        return uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                workers=1,
                access_log=False,
                proxy_headers=False,
                log_level="warning",
                ws_max_size=4096,
                lifespan="off",
            )
        )

    public_server = server(public, config.public_port)
    internal_server = server(internal, config.internal_port)
    async with public.router.lifespan_context(public):
        public_server.config.lifespan = "off"
        tasks = [
            asyncio.create_task(server.serve())
            for server in (public_server, internal_server)
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            public_server.should_exit = internal_server.should_exit = True
            await asyncio.gather(*tasks, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "migrate", "serve"))
    args = parser.parse_args()
    try:
        config = Config.from_env()
        config.validate()
        if os.name != "nt":
            os.umask(0o077)
            if config.data_dir.exists() and config.data_dir.stat().st_mode & 0o077:
                raise ValueError("POKER_DATA_DIR must be private (chmod 700)")
        if args.command == "check":
            print(
                "Configuration valid; SQLite "
                + sqlite3.sqlite_version
                + "; one worker; OAuth and Termux not verified by this check"
            )
        elif args.command == "migrate":
            asyncio.run(migrate(config))
        else:
            if not (config.static_dir / "index.html").is_file():
                raise ValueError("Build poker_web before serving")
            logging.basicConfig(
                level=logging.INFO, format="%(levelname)s %(name)s %(message)s"
            )
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
            asyncio.run(serve(config))
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as error:
        # Configuration errors name keys, never their values. Runtime errors are sanitized.
        if isinstance(error, ValueError):
            parser.exit(2, str(error) + "\n")
        parser.exit(2, "Poker startup failed: " + type(error).__name__ + "\n")


if __name__ == "__main__":
    main()
