import assert from 'node:assert/strict';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { wildBest, deckFor } from './wildcards.ts';
import { bestFive, strength, calculateEquity, currentHandLabel } from './equity.ts';
const root=fileURLToPath(new URL('../../',import.meta.url));
test('wildcard scores and selected cards agree with Python across 450 deterministic hands',()=>{
 const script=`import json,random
from poker.wildcards import CARDS,JOKERS,evaluate
rng=random.Random(391)
result=[]
for n in (0,1,2):
 for _ in range(150):
  cards=rng.sample(CARDS,7-n)+list(JOKERS[:n])
  result.append([cards,evaluate(cards,True)])
print(json.dumps(result))`;
 const samples=JSON.parse(execFileSync(root+'poker/.venv/Scripts/python.exe',['-c',script],{cwd:root,encoding:'utf8'}));
 for(const [cards,expected] of samples){
  const got=wildBest(cards);
  const packed=[...expected.score,...Array(6).fill(0)].slice(0,6).reduce((n,v)=>n*15+v,0);
  assert.equal(got.score,packed,JSON.stringify(cards));
  assert.deepEqual(got.cards,expected.cards);
  assert.deepEqual(got.substitutions,expected.substitutions);
  const concrete=got.cards.map(c=>got.substitutions[c]??c);
  assert.equal(new Set(concrete).size,5);
  assert.equal(strength(concrete),packed);
  assert.equal(strength(cards),packed);
 }
});
test('mode-specific equity validates deck and handles shared jokers without hidden cards',()=>{
 const input={key:'j',game_mode:'double_joker',board:['Xr','Ts','Js','Qs','Ks'],players:[{id:'a',cards:['2h','3h'],paid:'100',folded:false},{id:'b',cards:['2c','3c'],paid:'100',folded:false}]};
 const result=calculateEquity(input);assert.equal(result.pots[0].shares.a,50);assert.equal(result.pots[0].shares.b,50);
 assert.equal(calculateEquity({...input,game_mode:'standard'}),null);
 const hidden={id:'fold',cards:['Xb','As'],paid:'100',folded:true};
 assert.deepEqual(calculateEquity({...input,players:[...input.players,hidden]}),calculateEquity({...input,players:[...input.players,{...hidden,cards:['Ac','Ad']}]}));
 assert.equal(deckFor('double_joker').length,54);assert.equal(deckFor().length,52);
 assert.equal(currentHandLabel(['Xr','As'],[]),'一對');
 assert.ok(bestFive(['Xr','2d','Ts','Js','Qs','Ks','3h']).includes('Xr'));
});
test('six-player preflop joker equity remains bounded and includes ties',()=>{
 const players=[['Xr','Xb'],['As','Ah'],['Ks','Kh'],['Qs','Qh'],['Js','Jh'],['Ts','Th']].map((cards,i)=>({id:String(i),cards,paid:'100',folded:false}));
 const started=performance.now();const result=calculateEquity({key:'performance',game_mode:'double_joker',board:[],players});
 assert.equal(result.samples,20000);assert.equal(result.approximate,true);
 assert.ok(Math.abs(Object.values(result.pots[0].shares).reduce((a,b)=>a+b,0)-100)<1e-7);
 assert.ok(performance.now()-started<15000,'equity must finish within 15s in its worker');
});