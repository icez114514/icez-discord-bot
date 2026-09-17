import { useEffect, useState } from 'react';
import type { EquityPlayer, EquityResult } from './equity';
export function useEquity(hand: string, board: string[], players: EquityPlayer[], enabled: boolean) {
  // Serialization deliberately strips all fields other than public cards/contributions.
  const payload = enabled ? JSON.stringify({ board, players: players.map(p=>({id:p.id,cards:p.folded?[]:p.cards,paid:p.paid,folded:p.folded})) }) : '';
  const key = hand + ':' + payload;
  const [state,setState] = useState<{key:string;result:EquityResult|null}>({key:'',result:null});
  useEffect(()=>{
    if(!payload) return;
    const worker = new Worker(new URL('./equity.worker.ts',import.meta.url),{type:'module'});
    worker.onmessage = event => { if(event.data.key===key) setState({key,result:event.data.result}); };
    worker.onerror = () => setState({key,result:null});
    worker.postMessage({...JSON.parse(payload),key});
    return ()=>worker.terminate();
  },[key,payload]);
  return { result:state.key===key?state.result:null, pending:!!payload&&state.key!==key };
}
