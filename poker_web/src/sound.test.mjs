import { test } from 'node:test';
import assert from 'node:assert/strict';
const storage = new Map();
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
globalThis.document = { hidden: false };
const played = [];
globalThis.fetch = async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(1) });
class Context {
  state = 'running'; destination = {};
  resume() { return Promise.resolve(); }
  decodeAudioData() { return Promise.resolve({}); }
  createGain() { return { gain: { value: 0 }, connect() {}, disconnect() {} }; }
  createBufferSource() {
    const source = { playbackRate: { value: 1 }, connect() {}, disconnect() {}, start() { played.push(source); }, stop() { source.onended?.(); } };
    return source;
  }
}
globalThis.AudioContext = Context;
const { sound } = await import('./sound.ts');
test('account volumes persist; mute and category zero also silence preview', async () => {
  sound.setUser('a'); sound.unlock();
  sound.configure({ master: 0.4, groups: { ...sound.preferences().groups, chips: 0 } });
  await sound.play('chips'); assert.equal(played.length, 0);
  sound.configure({ muted: true }); await sound.play('turn'); assert.equal(played.length, 0);
  sound.setUser('b'); assert.equal(sound.preferences().master, 1);
  sound.setUser('a'); assert.equal(sound.preferences().master, 0.4); assert.equal(sound.isMuted(), true);
  sound.configure({ muted: false, groups: { ...sound.preferences().groups, chips: 1 } });
  sound.unlock(); await sound.play('chips'); assert.equal(played.length, 1);
});
test('concurrency protects turn prompts without bypassing disabled reminder group', async () => {
  sound.stop(); played.length = 0; sound.setUser('priority'); sound.unlock();
  for (let i = 0; i < 6; i++) await sound.play('chips');
  assert.equal(played.length, 4);
  await sound.play('turn'); assert.equal(played.length, 5);
  sound.configure({ groups: { ...sound.preferences().groups, reminders: 0 } });
  await sound.play('turn'); assert.equal(played.length, 5);
});
test('slow audio loads never replay an expired cue', async () => {
  const fetchBefore = globalThis.fetch, performanceBefore = globalThis.performance;
  let clock = 0, resolve;
  globalThis.performance = { now: () => clock };
  const ready = new Promise(r => { resolve = r; });
  globalThis.fetch = async () => { await ready; return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) }; };
  try {
    const { sound: slow } = await import('./sound.ts?slow');
    slow.setUser('slow'); slow.unlock();
    const count = played.length, playback = slow.play('turn');
    clock = 900; resolve(); await playback;
    assert.equal(played.length, count); assert.equal(slow.diagnosis(), 'expired');
    slow.stop();
  } finally { globalThis.fetch = fetchBefore; globalThis.performance = performanceBefore; }
});
test('settlement preempts chip noise while reminders remain available', async () => {
  sound.stop(); sound.setUser('settlement'); sound.unlock(); played.length = 0;
  for (let i = 0; i < 4; i++) await sound.play('chips');
  await sound.play('settle'); await sound.play('turn');
  assert.equal(played.length, 6);
});
test('multi-pot settlement cannot starve the following refund cue', async () => {
  sound.stop(); sound.setUser('multi-pots'); sound.unlock(); played.length = 0;
  for (let i = 0; i < 4; i++) await sound.play('settle');
  await sound.play('refund');
  assert.equal(played.length, 5);
  assert.equal(played.at(-1).playbackRate.value, 1.2);
});
test('storage failures retain session preferences per account and hidden pages remain silent', async () => {
  const original = localStorage.setItem;
  localStorage.setItem = () => { throw Error('denied'); };
  sound.setUser('private'); sound.configure({ master: 0.3 });
  sound.setUser('other'); sound.setUser('private'); assert.equal(sound.preferences().master, 0.3);
  document.hidden = true; const count = played.length;
  await sound.play('turn'); assert.equal(played.length, count); assert.equal(sound.diagnosis(), 'hidden');
  document.hidden = false; localStorage.setItem = original;
});
