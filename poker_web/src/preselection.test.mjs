import { test } from 'node:test';
import assert from 'node:assert/strict';
import { evaluatePreselection } from './preselection.ts';
const waiting = () => ({
  id: 'table', joined: true, closed: false, control: true, event_seq: 0, events: [],
  members: [{ id: 'me', mode: 'active', sitout: false, leaving: false }],
  hand: { id: 'hand', street: 'flop', turn: 3, actor: 1, deadline: 200, payouts: null, call_amount: '50',
    players: [{ id: 'me', stack: '1000', bet: '0', folded: false }, { id: 'other', stack: '1000', bet: '50', folded: false }], legal: {} },
});
const selected = { table: 'table', hand: 'hand', street: 'flop', endpoint: 'tab', seq: 0, action: 'call', amount: '50' };
const check = (state, selection = selected, now = 100, endpoint = 'tab') => evaluatePreselection(selection, state, 'me', endpoint, now);
test('fixed call survives normal turn increments and executes only matching legal amount', () => {
  const state = waiting(); state.hand.turn = 4;
  assert.equal(check(state), 'wait');
  state.hand.actor = 0; state.hand.legal = { fold: true, call: '50' };
  assert.equal(check(state), 'call');
  state.hand.legal.call = '75';
  assert.equal(check(state), 'cancel');
});
test('changed amount, hand, street, control, membership and deadline cancel', () => {
  for (const mutate of [
    s => s.hand.call_amount = '60', s => s.hand.street = 'turn', s => s.hand.id = 'next',
    s => s.control = false, s => s.joined = false, s => s.closed = true, s => s.frozen = true,
    s => s.members[0].sitout = true, s => s.members[0].leaving = true,
    s => s.hand.players[0].folded = true,
    s => { s.hand.actor = 0; s.hand.deadline = 99; },
    s => { s.event_seq = 1; s.events = [{ seq: 1, kind: 'action', user: 'me' }]; },
    s => { s.event_seq = 100; s.events = []; },
  ]) { const state = waiting(); mutate(state); assert.equal(check(state), 'cancel'); }
  assert.equal(check(waiting(), selected, 100, 'other-tab'), 'cancel');
});
test('preselected all-in never auto-sends and check otherwise cancels', () => {
  const state = waiting(); state.hand.actor = 0;
  state.hand.players[0].stack = '50'; state.hand.legal = { fold: true, call: '50' };
  assert.equal(check(state), 'confirm');
  const precheck = { ...selected, action: 'check', amount: '0' };
  state.hand.call_amount = '0'; state.hand.legal = { fold: true, check: true, call: '0' };
  assert.equal(check(state, precheck), 'check');
  state.hand.call_amount = '50'; state.hand.legal.check = false;
  assert.equal(check(state, precheck), 'cancel');
});
