import { test } from 'node:test';
import assert from 'node:assert/strict';
import { tableSoundEvents } from './tableAudio.ts';
const hand = { id: 'h1', board: [], pot: '150', turn: 1, extensions: 0, payouts: null, players: [{ id: 'a', folded: false }], legal: {} };
test('repeated snapshots and rejected actions stay silent', () => {
  assert.deepEqual(tableSoundEvents(hand, structuredClone(hand), true), []);
});
test('accepted check plays an operation cue even without pot changes', () => {
  assert.deepEqual(tableSoundEvents(hand, { ...hand, turn: 2 }, true), ['click']);
});
test('first deal, board, chips, fold, settlement have distinct cues', () => {
  assert.deepEqual(tableSoundEvents(null, hand, true), ['deal']);
  assert.deepEqual(tableSoundEvents(hand, { ...hand, board: ['As', 'Kh', '2d'] }, true), ['deal']);
  assert.deepEqual(tableSoundEvents(hand, { ...hand, pot: '250' }, true), ['chips']);
  assert.deepEqual(tableSoundEvents(hand, { ...hand, players: [{ id: 'a', folded: true }] }, true), ['fold']);
  assert.deepEqual(tableSoundEvents(hand, { ...hand, payouts: { a: '150' } }, true), ['settle']);
});
test('timebank and turn prompts belong to the controlling player only', () => {
  const own = { ...hand, legal: { fold: true } };
  assert.deepEqual(tableSoundEvents(hand, own, true), ['turn']);
  assert.deepEqual(tableSoundEvents(hand, own, false), []);
  assert.deepEqual(tableSoundEvents(own, { ...own, extensions: 1 }, true), ['bank']);
  assert.deepEqual(tableSoundEvents(own, { ...own, extensions: 1 }, false), []);
});
