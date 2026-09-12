"""Correlated, value-free operation timings; no user or financial payloads."""
import asyncio
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

timing_logger = logging.getLogger('bot.timing')
timing_logger.setLevel(logging.INFO)
timing_logger.propagate = False


def configure_timing_logging(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    path = str((directory / 'latency.log').resolve())
    for existing in timing_logger.handlers:
        if isinstance(existing, RotatingFileHandler) and existing.baseFilename == path:
            return existing
    handler = RotatingFileHandler(path, maxBytes=2 * 1024 * 1024, backupCount=3,
                                  encoding='utf-8', delay=True)
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    timing_logger.addHandler(handler)
    return handler


_current: ContextVar[dict | None] = ContextVar('operation_latency', default=None)


def correlation_id():
    state = _current.get()
    return state['id'] if state else '-'


def add_time(name, elapsed):
    state = _current.get()
    if state is not None:
        state[name] = state.get(name, 0.0) + elapsed * 1000


def mark_cold():
    state = _current.get()
    if state is not None:
        state['connection'] = 'cold'


@contextmanager
def measure(name):
    started = time.perf_counter()
    try:
        yield
    finally:
        add_time(name, time.perf_counter() - started)


def interaction_age_ms(interaction):
    created = getattr(interaction, 'created_at', None)
    if isinstance(created, datetime) and created.tzinfo is not None:
        return (datetime.now(timezone.utc) - created).total_seconds() * 1000
    return None


def record_received(interaction):
    extras = getattr(interaction, 'extras', None)
    if isinstance(extras, dict):
        extras['_timing_received'] = time.perf_counter()
        extras['_timing_received_age'] = interaction_age_ms(interaction)


def record_age(interaction, field):
    state = _current.get()
    age = interaction_age_ms(interaction)
    if state is not None and age is not None:
        state[field] = age


def observe_interaction(interaction):
    state = _current.get()
    if state is None:
        return
    record_age(interaction, 'interaction_age_ms')
    extras = getattr(interaction, 'extras', {})
    if isinstance(extras, dict) and '_timing_received' in extras:
        state['dispatch_wait_ms'] = (time.perf_counter()-extras['_timing_received'])*1000
        if extras.get('_timing_received_age') is not None:
            state['received_age_ms'] = extras['_timing_received_age']


class LoopMonitor:
    """Passive loop-lag samples, emitted only to the timing file every 30 seconds."""
    def __init__(self, interval=1.0):
        self.interval = interval
        self.max_lag_ms = 0.0
        self.task = None

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run(), name='event-loop-timing')

    async def run(self):
        reported = time.perf_counter()
        peak = 0.0
        while True:
            expected = time.perf_counter() + self.interval
            await asyncio.sleep(self.interval)
            now = time.perf_counter()
            lag = max(0.0, (now-expected)*1000)
            self.max_lag_ms = max(self.max_lag_ms, lag)
            peak = max(peak, lag)
            if now-reported >= 30:
                timing_logger.info('Event loop timing max_lag_ms=%.1f window_ms=%.1f', peak, (now-reported)*1000)
                peak, reported = 0.0, now

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


def operation(name):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            if _current.get() is not None:
                return await function(*args, **kwargs)
            state = dict(id=uuid4().hex[:16], operation=name, connection='warm', status='ok')
            token = _current.set(state)
            for arg in args:
                if hasattr(arg, 'response') and hasattr(arg, 'user'):
                    observe_interaction(arg)
                    break
            started = time.perf_counter()
            try:
                return await function(*args, **kwargs)
            except asyncio.CancelledError:
                state['status'] = 'cancelled'
                raise
            except Exception:
                state['status'] = 'error'
                raise
            finally:
                state['total_ms'] = (time.perf_counter()-started)*1000
                for field in ('owner_wait_ms', 'db_ms', 'pool_wait_ms', 'compose_ms', 'update_ms', 'auth_ms'):
                    state.setdefault(field, 0.0)
                timing_logger.info('Operation timing %s', ' '.join(
                    f'{key}={value:.1f}' if isinstance(value, float) else f'{key}={value}'
                    for key, value in state.items()))
                _current.reset(token)
        return wrapped
    return decorate


def timed(name):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with measure(name):
                return await function(*args, **kwargs)
        return wrapped
    return decorate


@asynccontextmanager
async def measured_lock(lock):
    with measure('owner_wait_ms'):
        await lock.acquire()
    try:
        yield
    finally:
        lock.release()


def mark_status(status):
    state = _current.get()
    if state is not None:
        state['status'] = status


async def discord_update(request):
    with measure('update_ms'):
        return await request


def mark_action(action):
    # Only fixed command categories; never log button values, filters or modal input.
    category = action.split(':', 1)[0]
    allowed = {'start', 'hit', 'stand', 'double', 'replay', 'settings', 'blackjack',
               'lobby', 'base', 'multiplier', 'custom', 'submit', 'records', 'house',
               'paigow', 'pai_select', 'pai_auto', 'pai_confirm',
               'audit_player', 'audit_game', 'previous', 'next', 'toggle', 'filter', 'apply_filter'}
    state = _current.get()
    if state is not None:
        state['action'] = category if category in allowed else 'unknown'
