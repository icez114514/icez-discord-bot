export type Sound = 'deal' | 'chips' | 'fold' | 'settle' | 'click' | 'turn' | 'tick' | 'bank' | 'check' | 'collect' | 'refund' | 'topup' | 'result' | 'error' | 'payout';
export type Group = 'reminders' | 'chips' | 'settlement' | 'interface';
export type Preferences = { muted: boolean; master: number; groups: Record<Group, number>; reduced: boolean };
const catalog: Record<Sound, { file: string; group: Group; rate?: number }> = {
  deal: { file: 'deal', group: 'chips' }, chips: { file: 'chips', group: 'chips' },
  fold: { file: 'fold', group: 'chips' }, check: { file: 'click', group: 'chips', rate: 0.8 },
  collect: { file: 'chips', group: 'chips', rate: 0.8 },
  payout: { file: 'chips', group: 'settlement' }, settle: { file: 'settle', group: 'settlement' }, refund: { file: 'chips', group: 'settlement', rate: 1.2 },
  turn: { file: 'turn', group: 'reminders' }, tick: { file: 'tick', group: 'reminders' },
  bank: { file: 'bank', group: 'reminders' }, click: { file: 'click', group: 'interface' },
  topup: { file: 'bank', group: 'interface' }, result: { file: 'click', group: 'interface' },
  error: { file: 'fold', group: 'interface', rate: 0.7 },
};
const defaults = (): Preferences => ({ muted: false, master: 1, groups: { reminders: 1, chips: 1, settlement: 1, interface: 1 }, reduced: false });
const volume = (n: unknown, fallback = 1) => typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : fallback;
function normalize(raw: Partial<Preferences> | null): Preferences {
  const p = defaults();
  p.muted = raw?.muted === true; p.reduced = raw?.reduced === true; p.master = volume(raw?.master);
  for (const group of Object.keys(p.groups) as Group[]) p.groups[group] = volume(raw?.groups?.[group]);
  return p;
}
let prefs = defaults(), user = '', context: AudioContext | undefined, epoch = 0, diagnostic = 'locked', storageFailed = false;
const sessions = new Map<string, Preferences>();
const listeners = new Set<() => void>();
const buffers = new Map<string, Promise<AudioBuffer>>();
const sources = new Map<AudioBufferSourceNode, number>();
function buffer(file: string, audio: AudioContext) {
  let pending = buffers.get(file);
  if (!pending) {
    pending = fetch('/assets/audio/' + file + '.ogg').then(r => { if (!r.ok) throw Error('audio'); return r.arrayBuffer(); }).then(data => audio.decodeAudioData(data));
    buffers.set(file, pending);
    void pending.catch(() => { buffers.delete(file); diagnostic = 'load_failed'; });
  }
  return pending;
}
function blocked(name: Sound): string | null {
  if (document.hidden) return 'hidden';
  if (prefs.muted) return 'muted';
  if (prefs.master === 0 || prefs.groups[catalog[name].group] === 0) return 'volume_zero';
  if (!context || context.state !== 'running') return 'locked';
  return null;
}
export const sound = {
  preferences: () => prefs,
  subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  diagnosis: () => diagnostic,
  storageFailed: () => storageFailed,
  isMuted: () => prefs.muted,
  setUser(next: string) {
    if (user === next) return;
    sound.stop(); user = next; storageFailed = false;
    let saved = sessions.get(user);
    if (!saved) {
      try { saved = normalize(JSON.parse(localStorage.getItem('poker-sound:v1:' + user) ?? 'null')); }
      catch { saved = defaults(); storageFailed = true; }
    }
    prefs = saved; for (const listener of listeners) listener();
  },
  configure(patch: Partial<Preferences>) {
    sound.stop(); prefs = normalize({ ...prefs, ...patch }); sessions.set(user, prefs);
    try { localStorage.setItem('poker-sound:v1:' + user, JSON.stringify(prefs)); storageFailed = false; }
    catch { storageFailed = true; }
    for (const listener of listeners) listener();
  },
  unlock() {
    if (prefs.muted) { diagnostic = 'muted'; return; }
    try {
      context ??= new AudioContext();
      const audio = context;
      void audio.resume().then(() => { diagnostic = audio.state === 'running' ? 'ready' : 'locked'; }).catch(() => { diagnostic = 'locked'; });
      for (const file of new Set(Object.values(catalog).map(c => c.file))) void buffer(file, audio).catch(() => {});
    } catch { diagnostic = 'unavailable'; }
  },
  stop() {
    epoch++;
    for (const source of sources.keys()) { try { source.stop(); } catch { /* Already stopped. */ } }
    sources.clear();
  },
  mute(value: boolean) { sound.configure({ muted: value }); if (!value) sound.unlock(); },
  async play(name: Sound) {
    const reason = blocked(name);
    if (reason) { diagnostic = reason; return; }
    const audio = context!;
    const started = performance.now(), revision = epoch, cue = catalog[name];
    try {
      const decoded = await buffer(cue.file, audio);
      const reason = blocked(name);
      if (reason) { diagnostic = reason; return; }
      if (revision !== epoch || performance.now() - started > 600) { diagnostic = 'expired'; return; }
      const priority = cue.group === 'reminders' ? 2 : cue.group === 'settlement' ? 1 : 0;
      // Keep two slots available for turn/countdown even during multi-player chip movement.
      if (priority < 2 && sources.size >= 4) {
        const victim = [...sources].find(([, p]) => priority > 0 && p <= priority);
        if (!victim) { diagnostic = 'limited'; return; }
        victim[0].stop(); sources.delete(victim[0]);
      }
      if (sources.size >= 6) {
        const victim = [...sources].find(([, p]) => p < priority);
        if (!victim) { diagnostic = 'limited'; return; }
        victim[0].stop(); sources.delete(victim[0]);
      }
      const source = audio.createBufferSource(), gain = audio.createGain();
      source.buffer = decoded; source.playbackRate.value = cue.rate ?? 1;
      gain.gain.value = prefs.master * prefs.groups[cue.group] * (name === 'tick' ? 0.18 : 0.32);
      source.connect(gain); gain.connect(audio.destination); sources.set(source, priority);
      source.onended = () => { sources.delete(source); source.disconnect(); gain.disconnect(); };
      source.start(); diagnostic = 'playing';
    } catch { diagnostic = 'load_failed'; }
  },
};
