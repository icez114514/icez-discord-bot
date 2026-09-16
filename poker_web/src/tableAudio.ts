import type { Sound } from './sound';

export type PublicEvent = {
  id: string; seq: number; at: number; kind: string; hand_id?: string; user?: string;
  action?: string; amount?: string; raise_to?: string; all_in?: boolean;
  amounts?: Record<string, string>; pot_id?: string; reason?: string; turn?: number;
};
export type EventState = { id: string; event_seq?: number; events?: PublicEvent[]; server_time?: number };
/** Consume at transport ingress, before React batching. A missing range becomes a new silent baseline. */
export class EventCursor {
  private table = '';
  private seq: number | null = null;
  reset() { this.seq = null; }
  consume(state: EventState): PublicEvent[] {
    const end = state.event_seq ?? 0;
    const before = this.seq;
    if (this.table !== state.id || before === null) {
      this.table = state.id; this.seq = end; return [];
    }
    if (end <= before) return [];
    this.seq = end;
    const events = (state.events ?? []).filter(e => e.seq > before);
    if (events.length !== end - before || events.some((e, i) => e.seq !== before + i + 1)) return [];
    if (events.some(e => (state.server_time ?? e.at) - e.at > 3)) return [];
    return events;
  }
}
export function eventSound(event: PublicEvent, user: string, control: boolean): Sound | null {
  if (['turn', 'bank'].includes(event.kind)) return control && event.user === user ? event.kind as Sound : null;
  if (event.kind === 'topup') return event.user === user ? 'topup' : null;
  if (event.kind === 'action') {
    if (event.action === 'fold') return 'fold';
    if (event.action === 'check') return 'check';
    return event.amount && BigInt(event.amount) > 0n ? 'chips' : null;
  }
  return ({ deal: 'deal', board: 'deal', collect: 'collect', payout: 'settle', refund: 'refund' } as Record<string, Sound>)[event.kind] ?? null;
}
