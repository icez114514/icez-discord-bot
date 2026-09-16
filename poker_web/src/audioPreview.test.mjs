import { test } from 'node:test';
import assert from 'node:assert/strict';
globalThis.document = { hidden: false };
globalThis.localStorage = { getItem: () => null, setItem() {} };
const played = [];
let release, resumeWait = Promise.resolve(), clock = 0;
globalThis.performance = { now: () => clock };
globalThis.fetch = async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(1) });
class Context {
  state = 'suspended'; destination = {};
  async resume() { await resumeWait; this.state = 'running'; }
  async decodeAudioData() { return {}; }
  createGain() { return { gain: { value: 0 }, connect() {}, disconnect() {} }; }
  createBufferSource() { const s = { playbackRate: { value: 1 }, connect() {}, disconnect() {}, start() { played.push(s); }, stop() { s.onended?.(); } }; return s; }
}
globalThis.AudioContext = Context;

test('first preview waits for browser resume; pending interaction cues also play', async () => {
  const { sound } = await import('./sound.ts?preview-resume');
  resumeWait = new Promise(resolve => { release = resolve; });
  sound.setUser('preview');
  const preview = sound.preview('voice_allin');
  const cue = sound.play('chips');
  assert.equal(played.length, 0);
  release(); await Promise.all([preview, cue]);
  assert.equal(played.length, 2); sound.stop();
});

test('manual preview tolerates slow cold loads while gameplay cues expire', async () => {
  let finish;
  const wait = new Promise(resolve => { finish = resolve; });
  globalThis.fetch = async () => { await wait; return { ok: true, arrayBuffer: async () => new ArrayBuffer(1) }; };
  const { sound } = await import('./sound.ts?preview-slow');
  sound.setUser('slow'); await sound.unlock();
  const before = played.length;
  const preview = sound.preview('chips');
  const cue = sound.play('turn');
  await new Promise(resolve => setImmediate(resolve));
  clock = 900; finish(); await Promise.all([preview, cue]);
  assert.equal(played.length, before + 1); sound.stop();
});

test('mute while waiting for resume cancels both pending preview and gameplay cue', async () => {
  const { sound } = await import('./sound.ts?preview-cancel');
  resumeWait = new Promise(resolve => { release = resolve; });
  sound.setUser('cancel'); const before = played.length;
  const preview = sound.preview('voice_allin'), cue = sound.play('chips');
  sound.mute(true); release(); await Promise.all([preview, cue]);
  assert.equal(played.length, before); sound.stop();
});

test('rapid manual previews replace each other instead of exhausting gameplay voice slots', async () => {
  const { sound } = await import('./sound.ts?preview-overlap');
  resumeWait = Promise.resolve();
  sound.setUser('overlap'); const before = played.length;
  for (const cue of ['voice_allin', 'turn', 'chips', 'settle', 'click']) await sound.preview(cue);
  assert.equal(played.length, before + 5);
  sound.stop();
});
