export type Preselection = {
  table: string; hand: string; street: string; endpoint: string; seq: number;
  action: 'check' | 'call'; amount: string;
};
type State = {
  id: string; joined: boolean; closed: boolean; frozen?: boolean; control?: boolean;
  event_seq?: number; events?: { seq: number; kind: string; user?: string }[];
  members?: { id: string; mode: string; sitout: boolean; leaving: boolean }[];
  hand?: {
    id: string; street: string; actor: number | null; deadline: number | null;
    payouts: Record<string, string> | null; call_amount?: string | null;
    players: { id: string; stack: string; bet: string; folded: boolean }[];
    legal: { check?: boolean; fold?: boolean; call?: string };
  } | null;
};
export function evaluatePreselection(selected: Preselection, state: State, user: string, endpoint: string | null, now: number): 'wait' | 'cancel' | 'confirm' | 'check' | 'call' {
  const hand = state.hand, member = state.members?.find(m => m.id === user);
  const player = hand?.players.find(p => p.id === user);
  if (!state.joined || state.closed || state.frozen || !state.control || endpoint !== selected.endpoint ||
      state.id !== selected.table || !hand || hand.payouts || hand.id !== selected.hand || hand.street !== selected.street ||
      !member || member.sitout || member.leaving || member.mode !== 'active' ||
      !player || player.folded || BigInt(player.stack) <= 0n || hand.call_amount == null) return 'cancel';
  const events = (state.events ?? []).filter(e => e.seq > selected.seq);
  if ((state.event_seq ?? 0) - selected.seq !== events.length ||
      events.some(e => e.kind === 'action' && e.user === user)) return 'cancel';
  if (hand.call_amount !== selected.amount) return 'cancel';
  if (hand.actor === null || hand.players[hand.actor]?.id !== user) return 'wait';
  if (!hand.deadline || hand.deadline <= now || !hand.legal.fold) return 'cancel';
  if (selected.action === 'check') return hand.legal.check ? 'check' : 'cancel';
  if (hand.legal.call !== selected.amount || BigInt(selected.amount) <= 0n) return 'cancel';
  return BigInt(selected.amount) >= BigInt(player.stack) ? 'confirm' : 'call';
}
