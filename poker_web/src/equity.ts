/** Public-card-only evaluator. This module never accepts a private deck or future board. */
export type EquityPlayer = { id: string; cards: string[]; paid: string; folded: boolean };
import { wildBest, deckFor, jokers, type GameMode } from "./wildcards.ts";
export type EquityInput = { game_mode?: GameMode; key: string; board: string[]; players: EquityPlayer[] };
export type EquityResult = { key: string; approximate: boolean; samples: number; pots: { amount: string; shares: Record<string, number> }[] };
const ranks = '23456789TJQKA';
const rank = (card: string) => ranks.indexOf(card[0]) + 2;
function straight(values: number[]) {
  const unique = new Set(values);
  if (unique.has(14)) unique.add(1);
  for (let high = 14; high >= 5; high--) if ([0,1,2,3,4].every(n => unique.has(high - n))) return high;
  return 0;
}
function pack(category: number, values: number[]) {
  return [category, ...values, ...Array(5).fill(0)].slice(0, 6).reduce((n, v) => n * 15 + v, 0);
}
export function strength(cards: string[]): number {
  if(cards.some(c=>jokers.includes(c))) return wildBest(cards,false).score;
  const values = cards.map(rank).sort((a,b) => b-a);
  const groups = [...new Set(values)].map(r => [values.filter(v => v === r).length, r]).sort((a,b) => b[0]-a[0] || b[1]-a[1]);
  const flush = [...'cdhs'].map(s => cards.filter(c => c[1] === s).map(rank).sort((a,b) => b-a)).find(v => v.length >= 5);
  if (flush && straight(flush)) return pack(8, [straight(flush)]);
  const four = groups.find(g => g[0] === 4);
  if (four) return pack(7, [four[1], values.find(v => v !== four[1])!]);
  const triple = groups.find(g => g[0] >= 3), pair = groups.find(g => g[0] >= 2 && g !== triple);
  if (triple && pair) return pack(6, [triple[1], pair[1]]);
  if (flush) return pack(5, flush.slice(0,5));
  if (straight(values)) return pack(4, [straight(values)]);
  if (triple) return pack(3, [triple[1], ...values.filter(v => v !== triple[1]).slice(0,2)]);
  const pairs = groups.filter(g => g[0] === 2).map(g => g[1]);
  if (pairs.length >= 2) return pack(2, [...pairs.slice(0,2), values.find(v => !pairs.slice(0,2).includes(v))!]);
  if (pairs.length) return pack(1, [pairs[0], ...values.filter(v => v !== pairs[0]).slice(0,3)]);
  return pack(0, values.slice(0,5));
}
export function bestFive(cards: string[]): string[] {
  if(cards.some(c=>jokers.includes(c))) return wildBest(cards).cards;
  let best = -1, chosen: string[] = [];
  for (let a=0;a<cards.length-4;a++) for(let b=a+1;b<cards.length-3;b++) for(let c=b+1;c<cards.length-2;c++) for(let d=c+1;d<cards.length-1;d++) for(let e=d+1;e<cards.length;e++) {
    const five = [cards[a],cards[b],cards[c],cards[d],cards[e]], score = strength(five);
    if (score > best) { best=score; chosen=five; }
  }
  return chosen;
}
export function handLabel(cards: string[]): string {
  if (cards.length < 5) return '';
  return ['高牌','一對','兩對','三條','順子','同花','葫蘆','四條','同花順'][Math.floor(strength(cards) / 15 ** 5)];
}
/** Evaluate only the hole cards and board already visible to this viewer. */
export function currentHandLabel(hole: string[], board: string[]): string {
  const cards = [...hole, ...board];
  if (hole.length !== 2 || ![0,3,4,5].includes(board.length) || new Set(cards).size !== cards.length || cards.some(card => !deckFor("double_joker").includes(card))) return '';
  if (!board.length) return hole.some(c=>jokers.includes(c)) || hole[0][0] === hole[1][0] ? '一對' : '高牌';
  return handLabel(cards);
}
export function eligiblePots(players: EquityPlayer[]) {
  let floor = 0n;
  return [...new Set(players.map(p => p.paid))].map(BigInt).filter(n => n>0n).sort((a,b) => a<b?-1:a>b?1:0).flatMap(level => {
    const contributors=players.filter(p => BigInt(p.paid)>=level), amount=(level-floor)*BigInt(contributors.length);
    floor=level;
    return contributors.length>1 ? [{ amount: amount.toString(), eligible: contributors.filter(p=>!p.folded).map(p=>p.id) }] : [];
  });
}
export function calculateEquity(input: EquityInput): EquityResult | null {
  const deck = deckFor(input.game_mode);
  const live = input.players.filter(p=>!p.folded);
  if (live.length<2 || live.some(p=>p.cards.length!==2) || ![0,3,4,5].includes(input.board.length)) return null;
  const known = [...input.board, ...live.flatMap(p=>p.cards)];
  if (new Set(known).size!==known.length || known.some(c=>!deck.includes(c))) return null;
  const remaining=deck.filter(c=>!known.includes(c)), missing=5-input.board.length;
  const pots=eligiblePots(input.players);
  if (!pots.length || pots.some(p=>!p.eligible.length)) return null;
  const totals=pots.map(p=>Object.fromEntries(p.eligible.map(id=>[id,0])));
  let samples=0;
  function visit(extra: string[]) {
    const scores=Object.fromEntries(live.map(p=>[p.id,strength([...p.cards,...input.board,...extra])]));
    pots.forEach((p,index)=>{
      const best=Math.max(...p.eligible.map(id=>scores[id])), winners=p.eligible.filter(id=>scores[id]===best);
      winners.forEach(id=>{totals[index][id]+=1/winners.length;});
    });
    samples++;
  }
  if(missing<=2) {
    if(missing===0) visit([]);
    else for(let a=0;a<remaining.length;a++) {
      if(missing===1) visit([remaining[a]]);
      else for(let b=a+1;b<remaining.length;b++) visit([remaining[a],remaining[b]]);
    }
  } else {
    // Seed only public information, never the authoritative deck or future cards.
    let seed=2166136261;
    for(const c of JSON.stringify([input.game_mode??"standard",input.board,live.map(p=>[p.id,p.cards])])) seed=Math.imul(seed^c.charCodeAt(0),16777619);
    function random() { seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296; }
    if(!seed) seed=1;
    for(let n=0;n<20000;n++) {
      const pool=remaining.slice();
      for(let i=0;i<missing;i++) { const j=i+Math.floor(random()*(pool.length-i));[pool[i],pool[j]]=[pool[j],pool[i]]; }
      visit(pool.slice(0,missing));
    }
  }
  return {key:input.key,approximate:missing>2,samples,pots:pots.map((p,i)=>({amount:p.amount,shares:Object.fromEntries(Object.entries(totals[i]).map(([id,n])=>[id,n/samples*100]))}))};
}
