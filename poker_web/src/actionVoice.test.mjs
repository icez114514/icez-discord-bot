import { test } from 'node:test';
import assert from 'node:assert/strict';
import { eventVoice } from './tableAudio.ts';

test('confirmed voluntary actions select the correct voice, with all-in priority', () => {
  for (const action of ['call', 'bet', 'fold', 'check', 'raise']) {
    assert.equal(eventVoice({ kind: 'action', action }), 'voice_' + action);
  }
  assert.equal(eventVoice({ kind: 'action', action: 'raise', bet_level: 3 }), 'voice_threebet');
  assert.equal(eventVoice({ kind: 'action', action: 'raise', bet_level: 4 }), 'voice_fourbet');
  assert.equal(eventVoice({ kind: 'action', action: 'raise', bet_level: 5 }), 'voice_raise');
  assert.equal(eventVoice({ kind: 'action', action: 'call', all_in: true }), 'voice_allin');
  assert.equal(eventVoice({ kind: 'action', action: 'raise', bet_level: 3, all_in: true }), 'voice_allin');
  assert.equal(eventVoice({ kind: 'action', action: 'big_blind', all_in: true }), null);
  assert.equal(eventVoice({ kind: 'payout', action: 'call' }), null);
});
