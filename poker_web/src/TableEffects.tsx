import { useLayoutEffect, useState, type CSSProperties, type RefObject } from 'react';
import type { PublicEvent } from './tableAudio';
import { chips } from './tablePresentation';

type Flight = { id: string; amount: string; kind: string; style: CSSProperties };
export function ChipFlights({ events, scene }: { events: PublicEvent[]; scene: RefObject<HTMLDivElement | null> }) {
  const [flights, setFlights] = useState<Flight[]>([]);
  useLayoutEffect(() => {
    const root = scene.current;
    if (!root) return;
    const rect = root.getBoundingClientRect(), pot = root.querySelector('.pot')?.getBoundingClientRect();
    if (!pot) return;
    const center = { x: pot.x + pot.width / 2 - rect.x, y: pot.y + pot.height / 2 - rect.y };
    setFlights(events.flatMap(event => Object.entries(event.amounts ?? (event.user ? { [event.user]: event.amount ?? '0' } : {})).flatMap(([user, amount]) => {
      const seat = root.querySelector('[data-player="' + CSS.escape(user) + '"] .seat-plaque')?.getBoundingClientRect();
      if (!seat) return [];
      const player = { x: seat.x + seat.width / 2 - rect.x, y: seat.y + seat.height / 2 - rect.y };
      const bet = { x: player.x + (center.x - player.x) * 0.3, y: player.y + (center.y - player.y) * 0.3 };
      const from = event.kind === 'collect' ? bet : event.kind === 'action' ? player : center;
      const to = event.kind === 'collect' ? center : event.kind === 'action' ? bet : player;
      return [{ id: event.id + ':' + user, amount, kind: event.kind, style: {
        '--from-x': from.x + 'px', '--from-y': from.y + 'px', '--to-x': to.x + 'px', '--to-y': to.y + 'px',
      } as CSSProperties }];
    })));
  }, [events, scene]);
  return <div className="chip-layer" aria-hidden="true">{flights.map(f => <span key={f.id} className={'chip-flight ' + f.kind} style={f.style}>◉ {f.kind === 'refund' ? '退回 ' : ''}{chips(f.amount)}</span>)}</div>;
}
export type Settlement = { pots: { id: string; amount: string; winners: string[]; awards: Record<string, string> }[]; refunds: Record<string, string>; void: boolean };
export function SettlementDetails({ settlement, name }: { settlement: Settlement; name: (id: string) => string }) {
  return <details className="settlement-details"><summary>{settlement.void ? '作廢退款明細' : '主池／邊池結算明細'}</summary>
    <p>派彩為各池實領，未扣除本手投入；退款獨立列示。</p>
    {settlement.pots.map((pot, index) => <section key={pot.id}><strong>{index ? '邊池 ' + index : '主池'} · {chips(pot.amount)}</strong><ul>{Object.entries(pot.awards).map(([id, amount]) => <li key={id}>{name(id)} · 實領 {chips(amount)}</li>)}</ul></section>)}
    {Object.entries(settlement.refunds).map(([id, amount]) => <p key={id}>{name(id)} · {settlement.void ? '作廢退款' : '未跟注退款'} {chips(amount)}</p>)}
    <strong>合計 {chips((settlement.pots.reduce((n, p) => n + BigInt(p.amount), 0n) + Object.values(settlement.refunds).reduce((n, a) => n + BigInt(a), 0n)).toString())}</strong>
  </details>;
}
