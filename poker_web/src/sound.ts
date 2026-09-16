export type Sound = 'deal' | 'chips' | 'fold' | 'settle' | 'click' | 'turn' | 'tick' | 'bank';
let context: AudioContext | undefined;
let muted = false;
try { muted = localStorage.getItem('poker-muted') === 'true'; } catch { /* Private browsing storage can be unavailable. */ }
const buffers = new Map<Sound, Promise<AudioBuffer>>();
const sources = new Set<AudioBufferSourceNode>();
let epoch = 0;
export const sound = {
  isMuted: () => muted,
  unlock() {
    if (muted) return;
    try { context ??= new AudioContext(); void context.resume().catch(() => {}); } catch { /* Audio is optional. */ }
  },
  stop() { epoch++; for (const source of sources) { try { source.stop(); } catch { /* Already stopped. */ } } sources.clear(); },
  mute(value: boolean) {
    muted = value; sound.stop();
    try { localStorage.setItem('poker-muted', String(value)); } catch { /* Keep the session preference. */ }
    if (!value) sound.unlock();
  },
  async play(name: Sound) {
    const audio = context;
    if (muted || !audio || audio.state !== 'running' || document.hidden) return;
    const started = performance.now(), revision = epoch;
    try {
      let buffer = buffers.get(name);
      if (!buffer) {
        buffer = fetch(`/assets/audio/${name}.ogg`).then(response => { if (!response.ok) throw new Error('audio'); return response.arrayBuffer(); }).then(data => audio.decodeAudioData(data));
        buffers.set(name, buffer);
        void buffer.catch(() => buffers.delete(name));
      }
      const decoded = await buffer;
      if (muted || revision !== epoch || document.hidden || performance.now() - started > 600 || sources.size >= 4) return;
      const source = audio.createBufferSource(), gain = audio.createGain();
      source.buffer = decoded; gain.gain.value = name === 'tick' ? 0.18 : 0.32;
      source.connect(gain); gain.connect(audio.destination); sources.add(source);
      source.onended = () => { sources.delete(source); source.disconnect(); gain.disconnect(); };
      source.start();
    } catch { /* Missing or blocked audio must never interrupt the game. */ }
  },
};
