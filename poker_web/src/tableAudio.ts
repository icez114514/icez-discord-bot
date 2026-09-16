import type { Sound } from './sound';
type AudioHand = { id: string; board: string[]; pot: string; turn: number; extensions: number; payouts: Record<string, string> | null; players: { id: string; folded: boolean }[]; legal: { fold?: boolean } };
/** Compare authoritative projections only: failed commands and repeated snapshots stay silent. */
export function tableSoundEvents(old: AudioHand | null | undefined, next: AudioHand, control: boolean): Sound[] {
  const events: Sound[] = [];
  if (!old || old.id !== next.id || next.board.length > old.board.length) events.push('deal');
  else if (!old.payouts && next.payouts) events.push('settle');
  else if (BigInt(next.pot) > BigInt(old.pot)) events.push('chips');
  else if (next.players.some(p => p.folded && !old.players.find(q => q.id === p.id)?.folded)) events.push('fold');
  else if (old.turn !== next.turn) events.push('click');
  if (!next.payouts && next.legal.fold && control) {
    if (!old || old.id !== next.id || old.turn !== next.turn || !old.legal.fold) events.push('turn');
    else if (next.extensions > old.extensions) events.push('bank');
  }
  return events;
}
