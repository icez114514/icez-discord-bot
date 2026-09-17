import { CardBack } from './Cards';
import { PokerChips } from './PokerChips';
import { useLayoutEffect, useState, type CSSProperties, type RefObject } from 'react';
import type { PublicEvent } from './tableAudio';
import { chips } from './tablePresentation';

type Flight = { id: string; amount: string; kind: string; style: CSSProperties };
export function ChipFlights({ events, scene, format = chips, duration = 280 }: { events: PublicEvent[]; scene: RefObject<HTMLDivElement | null>; format?: (amount: string) => string; duration?: number }) {
  const [flights, setFlights] = useState<Flight[]>([]);
  useLayoutEffect(() => {
    const root = scene.current;
    if (!root) return;
    const rect = root.getBoundingClientRect(), pot = root.querySelector('.pot-chips')?.getBoundingClientRect();
    if (!pot) return;
    const scale = rect.width / root.offsetWidth || 1;
    const center = { x: pot.x + pot.width / 2 - rect.x, y: pot.y + pot.height / 2 - rect.y };
    setFlights(events.flatMap(event => Object.entries(event.amounts ?? (event.user ? { [event.user]: event.amount ?? '0' } : {})).flatMap(([user, amount]) => {
      const seat = root.querySelector('[data-player="' + CSS.escape(user) + '"] .portrait')?.getBoundingClientRect();
      const wager = root.querySelector('[data-player="' + CSS.escape(user) + '"] .seat-bet')?.getBoundingClientRect();
      if (!seat || !wager) return [];
      const player = { x: seat.x + seat.width / 2 - rect.x, y: seat.y + seat.height / 2 - rect.y };
      const bet = { x: wager.x + wager.width / 2 - rect.x, y: wager.y + wager.height / 2 - rect.y };
      const from = event.kind === 'collect' ? bet : event.kind === 'action' ? player : center;
      const to = event.kind === 'collect' ? center : event.kind === 'action' ? bet : player;
      return [{ id: event.id + ':' + user, amount, kind: event.kind, style: {
        '--flight-duration': duration + 'ms', '--from-x': from.x / scale + 'px', '--from-y': from.y / scale + 'px', '--to-x': to.x / scale + 'px', '--to-y': to.y / scale + 'px',
      } as CSSProperties }];
    })));
  }, [events, scene, duration]);
  return <div className="chip-layer" aria-hidden="true">{flights.map(f => <span key={f.id} className={'chip-flight ' + f.kind} style={f.style}><PokerChips amount={f.amount} /> {f.kind === 'refund' ? '退回 ' : ''}{format(f.amount)}</span>)}</div>;
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

export function DealFlights({event,players,button,scene,duration}:{event?:PublicEvent;players:string[];button:number;scene:RefObject<HTMLDivElement|null>;duration:number}) {
  const [cards,setCards]=useState<{key:string;target:string;style:CSSProperties}[]>([]);
  const ids=players.join(',');
  useLayoutEffect(()=>{
    const root=scene.current;
    if(!root||!event){setCards([]);return;}
    const factor=duration/(players.length*140+420);
    const ordered=[...players.slice(button+1),...players.slice(0,button+1)];
    setCards([0,1].flatMap(round=>ordered.flatMap((id,index)=>{
      const card=root.querySelector<HTMLElement>('[data-player="'+CSS.escape(id)+'"] .seat-cards .card:nth-child('+(round+1)+')');
      if(!card)return [];
      let x=0,y=0,node:HTMLElement|null=card;
      while(node&&node!==root){x+=node.offsetLeft-(node.classList.contains('seat')?node.offsetWidth/2:0);y+=node.offsetTop;node=node.offsetParent as HTMLElement|null;}
      return [{key:event.id+':'+id+':'+round,target:'[data-player="'+CSS.escape(id)+'"] .seat-cards .card:nth-child('+(round+1)+')',style:{'--to-x':x+'px','--to-y':y+'px','--card-angle':round?'7deg':'-7deg',width:card.offsetWidth,height:card.offsetHeight,animationDuration:220*factor+'ms',animationDelay:(round*players.length+index)*70*factor+'ms'} as CSSProperties}];
    })));
  },[event,ids,button,scene,duration]);
  return <div className="deal-layer" aria-hidden="true">{cards.map(card=><CardBack key={card.key} target={card.target} style={card.style} className="deal-card"/>)}</div>;
}
