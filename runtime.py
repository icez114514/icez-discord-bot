"""Shared entry-point support for Windows and Termux."""

import asyncio
import sys


def configure_event_loop() -> None:
    # Exact NUMERIC balances may exceed Python 3.11's default decimal conversion cap.
    # Discord limits individual inputs; the account domain has no product amount cap.
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    # Psycopg async connections require selectors on Windows.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
