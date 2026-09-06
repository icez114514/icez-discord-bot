"""Correlated, value-free operation timings; no user or financial payloads."""
import asyncio
import logging
import time
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

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


def operation(name):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            if _current.get() is not None:
                return await function(*args, **kwargs)
            state = dict(id=uuid4().hex[:16], operation=name, connection='warm', status='ok')
            token = _current.set(state)
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
                logging.info('Operation timing %s', ' '.join(
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
               'audit_player', 'audit_game', 'previous', 'next', 'toggle', 'filter', 'apply_filter'}
    state = _current.get()
    if state is not None:
        state['action'] = category if category in allowed else 'unknown'
