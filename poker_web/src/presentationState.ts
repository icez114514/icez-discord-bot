import type { PublicEvent } from './tableAudio';
export type ShownPlayer = {id:string;cards:string[];stack:string;paid:string;bet:string;folded:boolean};
export type ShownHand = {id:string;board:string[];players:ShownPlayer[];pot:string;street:string;button?:number;payouts:Record<string,string>|null;settlement?:{void:boolean;pots:{id:string;amount:string;winners:string[];awards:Record<string,string>}[];refunds:Record<string,string>}|null};
export type Outcome = {amount:string};
export type SceneState = {hand:ShownHand|null;revealed:boolean;resolved:boolean;wins:Record<string,Outcome>};
export function baseline(hand:ShownHand|null, stacks:Record<string,string>={}):SceneState {
  const copy=hand?structuredClone(hand):null;
  if(copy) copy.players.forEach(p=>{p.stack=stacks[p.id]??(BigInt(p.stack)+BigInt(copy.payouts?.[p.id]??'0')).toString();});
  const wins:Record<string,Outcome>={};
  if(copy?.payouts && !copy.settlement?.void) for(const pot of copy.settlement?.pots??[]) for(const [id,amount] of Object.entries(pot.awards)) wins[id]={amount:(BigInt(wins[id]?.amount??'0')+BigInt(amount)).toString()};
  return {hand:copy,revealed:!!copy?.payouts&&copy.players.filter(p=>!p.folded).length>1,resolved:!!copy?.payouts,wins};
}
export function startHand(final:ShownHand,user:string):SceneState {
  const hand=structuredClone(final);
  hand.board=[];hand.street='preflop';hand.pot='0';hand.payouts=null;hand.settlement=null;
  hand.players.forEach(p=>{p.stack=(BigInt(p.stack)+BigInt(p.paid)).toString();p.paid='0';p.bet='0';p.folded=false;if(p.id!==user)p.cards=[];});
  return {hand,revealed:false,resolved:false,wins:{}};
}
export function present(scene:SceneState,event:PublicEvent,final:ShownHand,user:string):SceneState {
  if(event.kind==='deal') return startHand(final,user);
  const next:SceneState={hand:scene.hand?structuredClone(scene.hand):null,revealed:scene.revealed,resolved:scene.resolved,wins:{...scene.wins}}, h=next.hand;
  if(!h)return next;
  const p=h.players.find(p=>p.id===event.user);
  if(event.kind==='action'&&p) {
    const amount=BigInt(event.amount??'0');
    p.stack=(BigInt(p.stack)-amount).toString();p.paid=(BigInt(p.paid)+amount).toString();p.bet=(BigInt(p.bet)+amount).toString();
    if(event.action==='fold'){p.folded=true;if(p.id!==user)p.cards=[];}
    h.pot=h.players.reduce((n,p)=>n+BigInt(p.paid),0n).toString();
  }
  if(event.kind==='collect') h.players.forEach(p=>{p.bet='0';});
  if(event.kind==='board') {h.board=[...event.board??[]];h.street=({3:'flop',4:'turn',5:'river'} as Record<number,string>)[h.board.length]??'preflop';}
  if(event.kind==='all_in_reveal'||event.kind==='showdown') {
    for(const p of h.players) if(!p.folded) p.cards=[...(event.kind==='all_in_reveal'?event.cards?.[p.id]:final.players.find(f=>f.id===p.id)?.cards)??[]];
    next.revealed=true;
  }
  if(event.kind==='showdown') {
    next.resolved=true;
    for(const pot of final.settlement?.pots??[]) for(const id of pot.winners) next.wins[id]??={amount:'0'};
  }
  if((event.kind==='payout'||event.kind==='refund')&&p) {
    const amount=BigInt(event.amount??'0');
    p.stack=(BigInt(p.stack)+amount).toString();
    if(event.kind==='payout') {
      next.resolved=true;
      next.wins[p.id]={amount:(BigInt(next.wins[p.id]?.amount??'0')+amount).toString()};
    }
  }
  if(event.kind==='complete') {
    h.payouts=final.payouts;h.settlement=final.settlement;next.resolved=true;
  }
  return next;
}
export const RESULT_HOLD_MS = 4400;
export function resultHoldMs(hand: Pick<ShownHand, "payouts" | "players" | "settlement">) {
  const uncontested = hand.payouts !== null && !hand.settlement?.void && hand.players.filter(p=>!p.folded).length === 1;
  return uncontested ? RESULT_HOLD_MS / 2 : RESULT_HOLD_MS;
}
export function eventDuration(event:PublicEvent,players:number,allInRunout=false) {
  return ({deal:players*140+420,action:120,collect:220,all_in_reveal:700,board:allInRunout?2000:650,showdown:650,payout:320,refund:320,complete:0} as Record<string,number>)[event.kind]??0;
}

export function presentationDurations(events:PublicEvent[],players:number,allInRunout=false) {
  let runout=allInRunout;
  return {durations:events.map(event=>{if(event.kind==='all_in_reveal')runout=true;return eventDuration(event,players,runout);}),allInRunout:runout};
}
