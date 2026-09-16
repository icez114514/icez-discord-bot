export type Preselection = {
  table: string; hand: string; street: string; endpoint: string; seq: number;
  action: 'check_fold' | 'call_any';
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
export function evaluatePreselection(selected: Preselection, state: State, user: string, endpoint: string | null, now: number): 'wait' | 'cancel' | 'confirm' | 'check' | 'call' | 'fold' {
  const hand = state.hand, member = state.members?.find(m => m.id === user);
  const player = hand?.players.find(p => p.id === user);
  if (!state.joined || state.closed || state.frozen || !state.control || endpoint !== selected.endpoint ||
      state.id !== selected.table || !hand || hand.payouts || hand.id !== selected.hand || hand.street !== selected.street ||
      !member || member.sitout || member.leaving || member.mode !== 'active' ||
      !player || player.folded || BigInt(player.stack) <= 0n) return 'cancel';
  const events = (state.events ?? []).filter(e => e.seq > selected.seq);
  if ((state.event_seq ?? 0) - selected.seq !== events.length ||
      events.some(e => e.kind === 'action' && e.user === user)) return 'cancel';
  if (hand.actor === null || hand.players[hand.actor]?.id !== user) return 'wait';
  if (!hand.deadline || hand.deadline <= now || !hand.legal.fold) return 'cancel';
  if (hand.legal.check) return 'check';
  if (selected.action === 'check_fold') return 'fold';
  if (!hand.legal.call || !/^[1-9][0-9]*$/.test(hand.legal.call)) return 'cancel';
  return BigInt(hand.legal.call) >= BigInt(player.stack) ? 'confirm' : 'call';
}
