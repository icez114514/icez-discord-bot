import test from 'node:test';
import assert from 'node:assert/strict';
import {baseline,startHand,present} from './presentationState.ts';
const final={id:'h',street:'river',board:['2c','3d','4h','8s','9c'],players:[{id:'a',cards:['As','Ad'],stack:'0',paid:'100',bet:'0',folded:false},{id:'b',cards:['Ks','Kd'],stack:'0',paid:'100',bet:'0',folded:false}],pot:'200',payouts:{a:'200',b:'0'},settlement:{void:false,pots:[{id:'p',amount:'200',winners:['a'],awards:{a:'200'}}],refunds:{}}};
const event=(kind,extra={})=>({id:kind,seq:1,at:0,kind,...extra});
test('final snapshot cannot leak future board, cards, payout or stack before their events',()=>{
 let s=startHand(final,'a');
 assert.deepEqual(s.hand.board,[]);assert.deepEqual(s.hand.players[1].cards,[]);assert.equal(s.hand.payouts,null);assert.equal(s.hand.players[0].stack,'100');
 for(const user of ['a','b'])s=present(s,event('action',{user,amount:'100'}),final,'a');
 s=present(s,event('all_in_reveal',{cards:{a:['As','Ad'],b:['Ks','Kd']}}),final,'a');
 assert.equal(s.revealed,true);assert.equal(s.resolved,false);assert.deepEqual(s.hand.board,[]);
 s=present(s,event('board',{board:final.board.slice(0,3)}),final,'a');
 assert.equal(s.hand.board.length,3);assert.equal(s.hand.players[0].stack,'0');assert.deepEqual(s.wins,{});
 s=present(s,event('board',{board:final.board}),final,'a');
 s=present(s,event('showdown'),final,'a');
 assert.equal(s.wins.a.amount,'0');assert.equal(s.hand.players[0].stack,'0');
 s=present(s,event('payout',{user:'a',amount:'200'}),final,'a');
 assert.equal(s.hand.players[0].stack,'200');assert.equal(s.wins.a.amount,'200');
 s=present(s,event('complete'),final,'a');assert.deepEqual(s.hand.settlement,final.settlement);
});
test('side-pot awards accumulate; refunds never create winners; snapshots are not mutated',()=>{
 let s=startHand(final,'a');
 for(const amount of ['100','50'])s=present(s,event('payout',{user:'a',amount}),final,'a');
 s=present(s,event('refund',{user:'b',amount:'30'}),final,'a');
 assert.equal(s.wins.a.amount,'150');assert.equal(s.wins.b,undefined);
 assert.equal(final.players[0].stack,'0');
 const b=baseline(final,{a:'200',b:'0'});assert.equal(b.hand.players[0].stack,'200');assert.equal(b.resolved,true);
});

test('scene updates do not clone UI queues or mutate the prior hand',()=>{
 const before=startHand(final,'a');
 // An unrelated UI callback is deliberately not cloneable.
 const scene={...before,uiCallback:()=>{},played:Array(80).fill(event('action'))};
 const next=present(scene,event('action',{user:'a',amount:'10'}),final,'a');
 assert.equal(next.hand.players[0].stack,'90');assert.equal(before.hand.players[0].stack,'100');
 assert.equal('played' in next,false);assert.equal('uiCallback' in next,false);
});
