import { useEffect, useRef, useState } from 'react';
import { EventCursor, eventSound, type EventState, type PublicEvent } from './tableAudio';
import { sound } from './sound';

export const chips = (value: string) => BigInt(value).toLocaleString('zh-TW');
const actions: Record<string, string> = { small_blind: '小盲', big_blind: '大盲', check: '過牌', fold: '棄牌', call: '跟注', bet: '下注', raise: '加注' };
export function actionLabel(event: PublicEvent) {
  const label = event.all_in ? '全下' : actions[event.action ?? ''] ?? '';
  if (!event.amount || event.amount === '0') return label;
  return event.action === 'raise'
    ? label + '至 ' + chips(event.raise_to ?? '0') + ' · 投入 ' + chips(event.amount)
    : label + ' ' + chips(event.amount);
}
type View = { context: string; flights: PublicEvent[]; actions: Record<string, PublicEvent>; wins: Record<string, PublicEvent> };
type Snapshot = EventState & { control?: boolean; hand?: { id: string } | null; members?: { id: string; seat: number }[] };
const empty = (context = ''): View => ({ context, flights: [], actions: {}, wins: {} });
export function useTablePresentation(user: string) {
  const [view, setView] = useState<View>(() => empty());
  const cursor = useRef(new EventCursor());
  const context = useRef('');
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const celebrated = useRef(new Set<string>());
  const announced = useRef(new Set<string>());
  const queueEnd = useRef(0);
  const receipts = useRef(new Set<string>());
  const delay = (ms: number, work: () => void) => {
    const timer = setTimeout(() => { timers.current.delete(timer); work(); }, ms);
    timers.current.add(timer);
  };
  function clear() {
    for (const timer of timers.current) clearTimeout(timer);
    timers.current.clear(); queueEnd.current = 0; celebrated.current.clear(); announced.current.clear(); setView(empty(context.current)); sound.stop();
  }
  function reset() { cursor.current.reset(); clear(); }
  useEffect(() => {
    sound.setUser(user);
    const visibility = () => reset();
    document.addEventListener('visibilitychange', visibility);
    return () => { document.removeEventListener('visibilitychange', visibility); for (const t of timers.current) clearTimeout(t); sound.stop(); };
  }, [user]);
  function receive(state: Snapshot, baseline = false) {
    const key = state.id + ':' + (state.hand?.id ?? '') + ':' + (state.members ?? []).map(m => m.id + '@' + m.seat).sort().join(',');
    if (context.current !== key) { context.current = key; clear(); }
    if (baseline || document.hidden) reset();
    const events = cursor.current.consume(state).filter(e => !e.hand_id || e.hand_id === state.hand?.id);
    const step = Math.min(240, 1600 / Math.max(1, events.length));
    for (const event of events) {
      const cue = eventSound(event, user, !!state.control);
      if (['turn', 'bank', 'topup'].includes(event.kind)) { if (cue) void sound.play(cue); continue; }
      // Compress bursts to a bounded presentation window without dropping awards.
      const start = Math.min(Math.max(performance.now(), queueEnd.current), performance.now() + 2200);
      queueEnd.current = start + step;
      delay(Math.max(0, start - performance.now()), () => {
        if (document.hidden) return;
        if (cue) {
          const repeatWin = event.kind === 'payout' && !!event.user && announced.current.has(event.user);
          void sound.play(repeatWin ? 'payout' : cue);
          if (event.kind === 'payout' && event.user) announced.current.add(event.user);
        }
        const flight = event.kind === 'collect' || ['payout', 'refund'].includes(event.kind) || event.kind === 'action' && BigInt(event.amount ?? '0') > 0n;
        setView(old => ({ ...old,
          flights: flight ? [...old.flights, event] : old.flights,
          actions: event.kind === 'action' && event.user ? { ...old.actions, [event.user]: event } : old.actions,
        }));
        if (event.kind === 'action' && event.user) delay(1400, () => setView(old => {
          const actions = { ...old.actions }; if (actions[event.user!]?.id === event.id) delete actions[event.user!]; return { ...old, actions };
        }));
        if (flight) delay(280, () => {
          setView(old => ({ ...old, flights: old.flights.filter(e => e.id !== event.id) }));
          if (event.kind !== 'payout' || !event.user || celebrated.current.has(event.user)) return;
          celebrated.current.add(event.user);
          setView(old => ({ ...old, wins: { ...old.wins, [event.user!]: event } }));
          delay(1200, () => setView(old => { const wins = { ...old.wins }; delete wins[event.user!]; return { ...old, wins }; }));
        });
      });
    }
    return events;
  }
  function result(id: string, failed: boolean) {
    if (receipts.current.has(id)) return;
    receipts.current.add(id);
    if (receipts.current.size > 128) receipts.current.delete(receipts.current.values().next().value!);
    if (!document.hidden) void sound.play(failed ? 'error' : 'result');
  }
  return { view, receive, reset, result };
}
