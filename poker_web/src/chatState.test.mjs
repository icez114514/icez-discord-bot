import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeChat, chatLength } from './chatState.ts';
const message=sequence=>({id:String(sequence),sequence,author:{id:'a',display_name:'A'},created_at:0,text:'hello',client_message_id:String(sequence)});
const update=(sequence,extra={})=>({type:'chat',table_id:'main',messages:[message(sequence)],sequence,closed:false,...extra});
test('independent ordered history deduplicates and retains 100',()=>{let state=null;for(let i=1;i<=101;i++)state=mergeChat(state,update(i));state=mergeChat(state,update(101));assert.equal(state.messages.length,100);assert.equal(state.messages[0].sequence,2);assert.equal(state.sequence,101);});
test('new table, reconnect and closure replace old history',()=>{const old=update(1);assert.equal(mergeChat(old,update(2,{table_id:'other'})).messages.length,1);assert.equal(mergeChat(old,update(3,{initial:true})).messages[0].sequence,3);assert.deepEqual(mergeChat(old,update(2,{closed:true})).messages,[]);});
test('Unicode codepoints rather than UTF16 units',()=>{assert.equal(chatLength('  🃏你好  '),3);assert.equal(chatLength('😀'.repeat(200)),200);assert.equal(chatLength('   '),0);});
