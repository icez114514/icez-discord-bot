"""Save redacted service samples during a real, operator-driven two-table run."""
import argparse
import asyncio
import json
import time
from pathlib import Path

from .backups import private_directory
from .config import Config, load_environment
from .operator_cli import request


async def sample(config, output, duration, interval):
    private_directory(output.parent)
    with output.open("x", encoding="utf-8") as stream:
        import os
        os.chmod(output, 0o600)
        start = time.monotonic()
        while time.monotonic() - start <= duration:
            now = time.monotonic()
            try:
                state = await request(config, "GET", "/operations")
                row = {"elapsed_seconds": now - start, "utc_unix": time.time(), **state}
            except Exception as error:
                row = {"elapsed_seconds": now - start, "error": type(error).__name__}
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            await asyncio.sleep(max(.1, interval - (time.monotonic() - now)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=int, default=7200)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    if args.duration < 1 or args.interval < 1:
        parser.error("duration and interval must be positive")
    load_environment()
    config = Config.from_env()
    config.validate()
    asyncio.run(sample(config, args.output, args.duration, args.interval))


if __name__ == "__main__":
    main()
