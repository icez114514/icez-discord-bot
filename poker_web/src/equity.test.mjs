import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {calculateEquity,strength,bestFive,eligiblePots} from './equity.ts';
const player=(id,cards,paid='100',folded=false)=>({id,cards,paid,folded});
test('river ties share each eligible pot and exclude unmatched refunds',()=>{
 const result=calculateEquity({key:'tie',board:['As','Ks','Qs','Js','Ts'],players:[player('a',['2c','3c'],'100'),player('b',['4c','5c'],'200'),player('c',['6c','7c'],'300')]});
 assert.deepEqual(result.pots.map(p=>p.amount),['300','200']);
 assert.equal(result.pots[1].shares.a,undefined);
 assert.equal(result.pots[1].shares.b,50);assert.equal(result.samples,1);
 assert(Math.abs(result.pots[0].shares.a-100/3)<1e-8);
});
test('turn enumerates exactly public unknown cards, folded secrets cannot affect result',()=>{
 const input={key:'turn',board:['As','Ad','2h','3h'],players:[player('a',['Ac','Ah']),player('b',['Ks','Kd']),player('fold',['Qh','Jh'],'100',true)]};
 const result=calculateEquity(input);
 assert.equal(result.samples,44);assert.equal(result.pots[0].shares.a,100);assert.equal(result.approximate,false);
 input.players[2].cards=['4c','5c'];assert.deepEqual(calculateEquity(input),result);
});
test('unrevealed, duplicate and invalid public cards never produce equity',()=>{
 for(const cards of [[],['As','As'],['xx','Kd']]) assert.equal(calculateEquity({key:'invalid',board:[],players:[player('a',['Ac','Ah']),player('b',cards)]}),null);
});
test('preflop is repeatable 20000-sample public estimate independent of future fields',()=>{
 const input={key:'pre',board:[],players:[player('a',['Ac','Ah']),player('b',['Ks','Kd'])]};
 const a=calculateEquity(input),b=calculateEquity({...input,deck:['As'],futureBoard:['As','Ad','2h','3h','4h']});
 assert.deepEqual(a,b);assert.equal(a.samples,20000);assert.equal(a.approximate,true);
 assert(a.pots[0].shares.a>79&&a.pots[0].shares.a<84);
});
test('evaluator agrees with authoritative Python oracle on deterministic 5/7-card hands',()=>{
 const root=path.resolve('..');
 const source="import json,random; from poker.rules import CARDS,strength; rng=random.Random(917); hands=[rng.sample(CARDS,n) for n in (5,7) for _ in range(160)]; print(json.dumps([[h,list(strength(h))] for h in hands]))";
 const data=JSON.parse(execFileSync(path.join(root,'poker/.venv/Scripts/python.exe'),['-c',source],{cwd:root,encoding:'utf8',windowsHide:true}));
 for(const [cards,score] of data) {
  const packed=[...score,...Array(6).fill(0)].slice(0,6).reduce((n,v)=>n*15+v,0);
  assert.equal(strength(cards),packed,cards.join(' '));
  assert.equal(strength(bestFive(cards)),packed);
 }
 assert.deepEqual(eligiblePots([player('a',[],'100'),player('b',[],'200')]).map(p=>p.amount),['200']);
});
