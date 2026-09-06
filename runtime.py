"""Shared entry-point support for Windows and Termux."""

import asyncio
import sys


def configure_event_loop() -> None:
    # Psycopg async connections require selectors on Windows.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
