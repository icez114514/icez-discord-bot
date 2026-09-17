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
