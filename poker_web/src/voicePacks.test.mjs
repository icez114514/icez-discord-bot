import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const storage = new Map(), played = [];
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
globalThis.document = { hidden: false };
globalThis.fetch = async url => ({ ok: true, arrayBuffer: async () => url });
class Context {
  state = 'suspended'; destination = {};
  async resume() { this.state = 'running'; }
  async decodeAudioData(url) { return { url }; }
  createGain() { return { gain: { value: 0 }, connect() {}, disconnect() {} }; }
  createBufferSource() {
    const source = { playbackRate: { value: 1 }, connect() {}, disconnect() {}, start() { played.push(source.buffer.url); }, stop() { source.onended?.(); } };
    return source;
  }
}
globalThis.AudioContext = Context;

test('selection previews All-in, persists per account and reloads with safe defaults', async () => {
  const { sound, voicePacks } = await import('./sound.ts?packs');
  assert.deepEqual(voicePacks.map(p => p.label), ['御姊', '少女', '貓娘']);
  sound.setUser('alice');
  await sound.selectVoice('shoujo');
  assert.match(played.at(-1), /voices\/shoujo\/voice-allin\.ogg/);
  for (const action of ['call', 'bet', 'fold', 'check', 'raise', 'allin']) {
    await sound.play('voice_' + action);
    assert.match(played.at(-1), new RegExp('voices/shoujo/voice-' + action + '\\.ogg'));
  }
  sound.setUser('bob'); assert.equal(sound.preferences().voicePack, 'oneesan');
  sound.setUser('alice'); assert.equal(sound.preferences().voicePack, 'shoujo');
  const { sound: reloaded } = await import('./sound.ts?packs-reload');
  reloaded.setUser('alice'); assert.equal(reloaded.preferences().voicePack, 'shoujo');
  storage.set('poker-sound:v1:legacy', JSON.stringify({ master: .4 }));
  reloaded.setUser('legacy'); assert.equal(reloaded.preferences().voicePack, 'oneesan');
  assert.equal(reloaded.preferences().master, .4);
  storage.set('poker-sound:v1:invalid', JSON.stringify({ voicePack: '../bad' }));
  reloaded.setUser('invalid'); assert.equal(reloaded.preferences().voicePack, 'oneesan');
  sound.stop(); reloaded.stop();
});

test('selection respects mute, zero voice volume and hidden pages; storage failure retains choice', async () => {
  const { sound } = await import('./sound.ts?packs-muted');
  sound.setUser('quiet'); sound.configure({ muted: true });
  const count = played.length;
  await sound.selectVoice('nekomimi'); assert.equal(played.length, count);
  sound.configure({ muted: false, groups: { ...sound.preferences().groups, voice: 0 } });
  await sound.selectVoice('shoujo'); assert.equal(played.length, count);
  sound.configure({ groups: { ...sound.preferences().groups, voice: 1 } });
  document.hidden = true;
  await sound.selectVoice('oneesan'); assert.equal(played.length, count);
  document.hidden = false;
  const save = localStorage.setItem;
  try {
    localStorage.setItem = () => { throw Error('denied'); };
    await sound.selectVoice('nekomimi'); assert.equal(sound.storageFailed(), true);
    sound.setUser('elsewhere'); sound.setUser('quiet');
    assert.equal(sound.preferences().voicePack, 'nekomimi');
  } finally { localStorage.setItem = save; sound.stop(); }
});

test('slow manual previews still play but switching cancels an older pack load', async () => {
  const previousFetch = fetch, previousPerformance = performance;
  let release, clock = 0;
  const wait = new Promise(resolve => { release = resolve; });
  globalThis.performance = { now: () => clock };
  globalThis.fetch = async url => {
    if (url.includes('shoujo/voice-allin')) await wait;
    return { ok: true, arrayBuffer: async () => url };
  };
  const { sound } = await import('./sound.ts?packs-race');
  try {
    sound.setUser('race');
    const old = sound.selectVoice('shoujo');
    await new Promise(resolve => setImmediate(resolve));
    await sound.selectVoice('nekomimi');
    const count = played.length;
    release(); await old;
    assert.equal(played.length, count);
    assert.match(played.at(-1), /nekomimi\/voice-allin/);
    let finish;
    const slow = new Promise(resolve => { finish = resolve; });
    globalThis.fetch = async url => { await slow; return { ok: true, arrayBuffer: async () => url }; };
    const preview = sound.selectVoice('oneesan');
    await new Promise(resolve => setImmediate(resolve));
    clock = 900; finish(); await preview;
    assert.equal(played.length, count + 1);
    assert.match(played.at(-1), /oneesan\/voice-allin/);
  } finally { release(); sound.stop(); globalThis.fetch = previousFetch; globalThis.performance = previousPerformance; }
});

test('all 18 shipped voice clips match the approved hashes', () => {
  const base = new URL('../public/assets/audio/voices/', import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('manifest.json', base), 'utf8'));
  assert.equal(manifest.packs.length, 3);
  for (const pack of manifest.packs) {
    assert.equal(pack.clips.length, 6);
    for (const clip of pack.clips) {
      assert.equal(createHash('sha256').update(readFileSync(new URL(clip.file, base))).digest('hex'), clip.sha256);
    }
  }
});

test('remote actor voice does not change listener preference', async () => {
  const { sound } = await import('./sound.ts?remote-actor');
  sound.setUser('listener');
  await sound.selectVoice('shoujo');
  await sound.play('voice_call', false, 'nekomimi');
  assert.match(played.at(-1), /voices\/nekomimi\/voice-call/);
  assert.equal(sound.preferences().voicePack, 'shoujo');
  sound.stop();
});

test('late voice-save failure notifies the settings snapshot after preview finishes', async () => {
  const original = fetch;
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  globalThis.fetch = async (url, options) => url === '/api/preferences' ? pending : original(url, options);
  const { sound } = await import('./sound.ts?save-failure');
  sound.setUser('save-failure');
  try {
    await sound.selectVoice('shoujo');
    const before = sound.preferences();
    let notified = 0;
    const unsubscribe = sound.subscribe(() => notified++);
    finish({ok:false});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sound.voiceSyncFailed(), true);
    assert(notified > 0);
    assert.notEqual(sound.preferences(), before);
    unsubscribe();
  } finally { finish({ok:false}); sound.stop(); globalThis.fetch = original; }
});
