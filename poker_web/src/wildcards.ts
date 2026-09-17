/** Same category-first wildcard rules as poker/wildcards.py. */
export type GameMode = 'standard' | 'double_joker';
export const ranks = '23456789TJQKA';
export const jokers = ['Xr','Xb'];
export const normalDeck = [...ranks].flatMap(r=>[...'cdhs'].map(s=>r+s));
export const deckFor = (mode: GameMode = 'standard') => mode === 'double_joker' ? [...normalDeck,...jokers] : normalDeck;
export const modeLabel = (mode?: GameMode) => mode === 'double_joker' ? '雙鬼牌德州' : '標準德州';
export const cardLabel = (c:string) => c==='Xr'?'紅鬼牌':c==='Xb'?'黑鬼牌':(c[0]==='T'?'10':c[0])+({c:'♣',d:'♦',h:'♥',s:'♠'}[c[1]]??'');
export const pack = (category:number, values:number[]) => [category,...values,...Array(5).fill(0)].slice(0,6).reduce((n,v)=>n*15+v,0);
export function wildBest(cards:string[], details=true) {
  const ordinary=cards.filter(c=>!jokers.includes(c)), wild=cards.filter(c=>jokers.includes(c));
  const counts=Array(15).fill(0) as number[];
  for(const c of ordinary) counts[ranks.indexOf(c[0])+2]++;
  const n=wild.length, descending=Array.from({length:13},(_,i)=>14-i);
  function finish(category:number,target:number[],keys:number[],suit?:string) {
    const score=pack(category,keys), originals:string[]=[], substitutions:Record<string,string>={};
    if(!details) return {score,cards:originals,substitutions};
    const available=[...ordinary],selected:string[]=[],missing:number[]=[];
    for(const r of target) {
      const index=available.findIndex(c=>ranks.indexOf(c[0])+2===r&&(!suit||c[1]===suit));
      if(index>=0) {const [c]=available.splice(index,1);originals.push(c);selected.push(c);} else missing.push(r);
    }
    missing.forEach((r,i)=>{const c=[...(suit??'cdhs')].map(s=>ranks[r-2]+s).find(c=>!selected.includes(c))!; originals.push(wild[i]);selected.push(c);substitutions[wild[i]]=c;});
    return {score,cards:originals,substitutions};
  }
  function straight(suit?:string) {
    const present=new Set(ordinary.filter(c=>!suit||c[1]===suit).map(c=>ranks.indexOf(c[0])+2));
    for(let high=14;high>=5;high--) {const target=high===5?[5,4,3,2,14]:Array.from({length:5},(_,i)=>high-i);if(target.filter(r=>!present.has(r)).length<=n)return {high,target};}
    return null;
  }
  const runs=[...'cdhs'].map(suit=>({suit,run:straight(suit)})).filter(x=>x.run).sort((a,b)=>b.run!.high-a.run!.high);
  if(runs.length) return finish(8,runs[0].run!.target,[runs[0].run!.high],runs[0].suit);
  function groups(required:number[][]) {
    let left=n-required.reduce((sum,[r,k])=>sum+Math.max(0,k-counts[r]),0);
    if(left<0)return null;
    const target=required.flatMap(([r,k])=>Array(k).fill(r) as number[]);
    if(target.length===5)return target;
    for(const r of descending) if(!required.some(([v])=>v===r)&&(counts[r]||left)) {target.push(r);if(!counts[r])left--;if(target.length===5)return target;}
    return null;
  }
  for(const r of descending) {if(counts[r]+n<4)continue;const t=groups([[r,4]]);if(t)return finish(7,t,[r,t[4]]);}
  for(const r of descending) for(const p of descending) if(p!==r&&counts[r]+n>=3&&counts[p]+n>=2) {const t=groups([[r,3],[p,2]]);if(t)return finish(6,t,[r,p]);}
  const flushes=[];
  for(const suit of 'cdhs') {
    const present=new Set(ordinary.filter(c=>c[1]===suit).map(c=>ranks.indexOf(c[0])+2));
    if(present.size+n<5)continue;
    let left=n;const target=[];
    for(const r of descending)if(present.has(r)||left){target.push(r);if(!present.has(r))left--;if(target.length===5)break;}
    flushes.push(finish(5,target,target,suit));
  }
  if(flushes.length)return flushes.sort((a,b)=>b.score-a.score)[0];
  const run=straight();if(run)return finish(4,run.target,[run.high]);
  for(const r of descending){if(counts[r]+n<3)continue;const t=groups([[r,3]]);if(t)return finish(3,t,[r,...t.slice(3)]);}
  for(const r of descending)for(const p of descending)if(p<r&&counts[r]+n>=2&&counts[p]+n>=2){const t=groups([[r,2],[p,2]]);if(t)return finish(2,t,[r,p,t[4]]);}
  for(const r of descending){const t=groups([[r,2]]);if(t)return finish(1,t,[r,...t.slice(2)]);}
  const t=groups([]);if(!t)throw Error('five_cards_required');return finish(0,t,t);
}