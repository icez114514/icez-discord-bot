import { useEffect, useRef, useState } from 'react';
import { EventCursor, eventSound, eventVoice, actorVoice, type EventState, type PublicEvent } from './tableAudio';
import { baseline as sceneBaseline, startHand, present, eventDuration, type SceneState, type ShownHand } from './presentationState';
import { sound } from './sound';
export const chips = (value: string) => BigInt(value).toLocaleString('zh-TW');
const actions: Record<string, string> = { small_blind: '小盲', big_blind: '大盲', check: '過牌', fold: '棄牌', call: '跟注', bet: '下注', raise: '加注' };
export function actionLabel(event: PublicEvent, format = chips) {
  const label = event.all_in ? 'ALL-IN 全下' : event.action === 'raise' && (event.bet_level ?? 0) >= 3 ? `${event.bet_level}-BET 再加注` : actions[event.action ?? ''] ?? '';
  if (!event.amount || event.amount === '0') return label;
  return event.action === 'raise' ? label + '至 ' + format(event.raise_to ?? '0') : label + ' ' + format(event.amount);
}
type View = SceneState & {context:string;board?:PublicEvent;deal?:PublicEvent;flights:PublicEvent[];actions:Record<string,PublicEvent>;playing:boolean;celebrating:boolean;played:PublicEvent[];flightDuration:number;boardDuration:number};
type Snapshot = EventState & {control?:boolean;hand?:ShownHand|null;members?:{id:string;seat:number;stack?:string;voice_pack?:import('./sound').VoicePack}[]};
const empty = (context=''):View => ({context,hand:null,revealed:false,resolved:false,wins:{},flights:[],actions:{},playing:false,celebrating:false,played:[],flightDuration:280,boardDuration:500});
export function useTablePresentation(user:string,reduced=false) {
  const [systemReduced,setSystemReduced]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(()=>{const media=matchMedia('(prefers-reduced-motion: reduce)');const change=()=>setSystemReduced(media.matches);media.addEventListener('change',change);return ()=>media.removeEventListener('change',change);},[]);
  const [view,setView]=useState<View>(()=>empty());
  const current=useRef(view), cursor=useRef(new EventCursor()), context=useRef(''), last=useRef<Snapshot|null>(null);
  const timers=useRef(new Set<ReturnType<typeof setTimeout>>()), end=useRef(0), receipts=useRef(new Set<string>()), announced=useRef(new Set<string>());
  const reduce=useRef(reduced);reduce.current=reduced||systemReduced;
  function update(work:(v:View)=>View) {current.current=work(current.current);setView(current.current);}
  function delay(ms:number,work:()=>void) {const t=setTimeout(()=>{timers.current.delete(t);work();},ms);timers.current.add(t);}
  function clear() {for(const t of timers.current)clearTimeout(t);timers.current.clear();end.current=0;announced.current.clear();sound.stop();}
  function sync(state:Snapshot) {
    clear();
    const stacks=Object.fromEntries((state.members??[]).filter(m=>m.stack!==undefined).map(m=>[m.id,m.stack!]));
    update(()=>({...empty(context.current),...sceneBaseline(state.hand??null,stacks)}));
  }
  function reset() {cursor.current.reset();if(last.current)sync(last.current);else {clear();update(()=>empty(context.current));}}
  useEffect(()=>{
    sound.setUser(user);
    const visibility=()=>reset();
    document.addEventListener('visibilitychange',visibility);
    return ()=>{document.removeEventListener('visibilitychange',visibility);clear();};
  },[user]);
  useEffect(()=>{if((reduced||systemReduced)&&last.current)sync(last.current);},[reduced,systemReduced]);
  function receive(state:Snapshot,baseline=false) {
    const previous=last.current, key=state.id+':'+(state.hand?.id??'')+':'+(state.members??[]).map(m=>m.id+'@'+m.seat).sort().join(',');
    const changed=context.current!==key;
    if(changed) {clear();context.current=key;update(()=>empty(key));}
    last.current=state;
    if(baseline||document.hidden)cursor.current.reset();
    const events=cursor.current.consume(state).filter(e=>!e.hand_id||e.hand_id===state.hand?.id);
    const changedBoard=previous?.hand?.board.join(',')!==state.hand?.board.join(',');
    const hasBoard=events.some(e=>e.kind==='board');
    const boardMismatch=hasBoard&&events.filter(e=>e.kind==='board').at(-1)?.board?.join(',')!==state.hand?.board.join(',');
    const gap=previous?.id===state.id&&(state.event_seq??0)>(previous.event_seq??0)&&!events.length;
    if(baseline||document.hidden||gap||boardMismatch||(changedBoard&&!hasBoard&&!events.some(e=>e.kind==='deal'))||!state.hand) {sync(state);return events;}
    if(changed&&!events.some(e=>e.kind==='deal')) {sync(state);return events;}
    if(reduce.current) {
      const actions={...current.current.actions};
      sync(state);
      const winners=new Set<string>();
      for(const event of events) {
        if(event.kind==='action'&&event.user)actions[event.user]=event;
        const cue=eventSound(event,user,!!state.control);
        if(cue)void sound.play(event.kind==='payout'&&winners.has(event.user??'')?'payout':cue);
        if(event.kind==='payout')winners.add(event.user??'');
        const voice=eventVoice(event);if(voice)void sound.play(voice,false,actorVoice(event,state.members??[]));
      }
      update(v=>({...v,actions,played:events}));
      return events;
    }
    if(!events.length) {
      if(!current.current.playing) {
        const stacks=Object.fromEntries((state.members??[]).filter(m=>m.stack!==undefined).map(m=>[m.id,m.stack!]));
        update(v=>({...v,...sceneBaseline(state.hand??null,stacks)}));
      }
      return events;
    }
    const final=structuredClone(state.hand);
    if(events.some(e=>e.kind==='deal')) update(v=>({...v,...startHand(final,user)}));
    const durations=events.map(e=>eventDuration(e,final.players.length)), total=durations.reduce((a,b)=>a+b,0);
    // Finish bursts before the server's five-second next-hand countdown.
    const factor=Math.min(1,4200/Math.max(1,total));
    let at=Math.max(performance.now(),end.current);
    update(v=>({...v,playing:true}));
    for(let index=0;index<events.length;index++) {
      const event=events[index], duration=durations[index]*factor;
      const flight=event.kind==='collect'||['payout','refund'].includes(event.kind)||event.kind==='action'&&BigInt(event.amount??'0')>0n;
      const award=event.kind==='payout'||event.kind==='refund';
      delay(Math.max(0,at-performance.now()),()=>{
        if(document.hidden)return;
        const cue=eventSound(event,user,!!state.control);
        if(cue) {void sound.play(event.kind==='payout'&&announced.current.has(event.user??'')?'payout':cue);if(event.kind==='payout')announced.current.add(event.user??'');}
        const voice=eventVoice(event);if(voice)void sound.play(voice,false,actorVoice(event,state.members??[]));
        update(v=>({...v,...(!award?present(v,event,final,user):{}),board:event.kind==='board'?event:v.board,boardDuration:event.kind==='board'?duration:v.boardDuration,deal:event.kind==='deal'?event:v.deal,flightDuration:duration,celebrating:v.celebrating||event.kind==='showdown'||event.kind==='payout',played:award?v.played:[...v.played,event].slice(-80),
          flights:flight?[...v.flights,event]:v.flights,actions:event.kind==='action'&&event.user?{...v.actions,[event.user]:event}:v.actions}));
      });
      if(flight||event.kind==='deal') delay(Math.max(0,at+duration-performance.now()),()=>{
        update(v=>({...v,...(award?present(v,event,final,user):{}),played:award?[...v.played,event].slice(-80):v.played,flights:v.flights.filter(e=>e.id!==event.id),deal:event.kind==='deal'?undefined:v.deal}));
      });
      at+=duration;
    }
    end.current=at;
    delay(Math.max(0,at-performance.now()),()=>{if(performance.now()+5>=end.current){update(v=>({...v,playing:false}));delay(1400,()=>{if(!current.current.playing)update(v=>({...v,celebrating:false}));});}});
    return events;
  }
  function result(id:string,failed:boolean) {
    if(receipts.current.has(id))return;
    receipts.current.add(id);if(receipts.current.size>128)receipts.current.delete(receipts.current.values().next().value!);
    if(!document.hidden&&failed)void sound.play('error');
  }
  return {view,receive,reset,result};
}
