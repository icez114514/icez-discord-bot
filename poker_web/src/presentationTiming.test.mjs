import test from 'node:test';
import assert from 'node:assert/strict';
import {presentationDurations,RESULT_HOLD_MS} from './presentationState.ts';
test('all-in runout timing survives batches without compressing awards',()=>{
 const first=presentationDurations([{kind:'all_in_reveal'}],6);
 const next=presentationDurations([{kind:'board'},{kind:'board'},{kind:'showdown'},...Array.from({length:18},()=>({kind:'payout'}))],6,first.allInRunout);
 assert.deepEqual(first.durations,[700]);assert.deepEqual(next.durations.slice(0,3),[2000,2000,650]);
 assert(next.durations.slice(3).every(d=>d===320));
 assert.equal(presentationDurations([{kind:'board'}],2).durations[0],650);
 assert.equal(RESULT_HOLD_MS,4400);
});

 test('uncontested result hold is halved, while active, showdown and void remain unchanged',async()=>{
  const {resultHoldMs}=await import('./presentationState.ts');
  const hand={payouts:{a:'100'},players:[{folded:false},{folded:true}],settlement:{void:false}};
  assert.equal(resultHoldMs(hand),2200);
  assert.equal(resultHoldMs({...hand,payouts:null}),4400);
  assert.equal(resultHoldMs({...hand,players:[{folded:false},{folded:false}]}),4400);
  assert.equal(resultHoldMs({...hand,settlement:{void:true}}),4400);
 });
