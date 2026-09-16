import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventCursor, eventSound } from './tableAudio.ts';
const event = (seq, kind = 'action', extra = {}) => ({ id: 't:' + seq, seq, at: 100, kind, hand_id: 'h', ...extra });
const state = events => ({ id: 't', event_seq: events.at(-1)?.seq ?? 0, events, server_time: 100 });
test('initial load is silent and HTTP/WS duplicate event identities are consumed once', () => {
  const cursor = new EventCursor();
  assert.deepEqual(cursor.consume(state([event(1)])), []);
  const action = event(2, 'action', { action: 'call', amount: '50' });
  assert.deepEqual(cursor.consume(state([event(1), action])), [action]);
  assert.deepEqual(cursor.consume(state([event(1), action])), []);
});
test('background, reconnect, table change, stale and unknown intermediate events never replay', () => {
  const cursor = new EventCursor();
  cursor.consume(state([event(1)]));
  cursor.reset();
  assert.deepEqual(cursor.consume(state([event(1), event(2)])), []);
  assert.deepEqual(cursor.consume(state([event(4)])), []);
  assert.deepEqual(cursor.consume({ ...state([event(5)]), server_time: 110 }), []);
  assert.deepEqual(cursor.consume({ ...state([event(6)]), id: 'other' }), []);
  assert.deepEqual(cursor.consume(state([event(1)])), []);
});
test('board, payouts and refunds in one delivery all retain distinct sound cues', () => {
  const cursor = new EventCursor();
  cursor.consume(state([]));
  const events = [event(1, 'board'), event(2, 'payout'), event(3, 'refund')];
  assert.deepEqual(cursor.consume(state(events)).map(e => eventSound(e, 'a', true)), ['deal', 'settle', 'refund']);
  assert.equal(eventSound(event(4, 'action', { action: 'check' }), 'a', true), 'check');
  assert.equal(eventSound(event(5, 'turn', { user: 'a' }), 'a', false), null);
  assert.equal(eventSound(event(6, 'bank', { user: 'a' }), 'a', true), 'bank');
});
