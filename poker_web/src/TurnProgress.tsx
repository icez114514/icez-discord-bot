import { useMemo } from 'react';
/** The browser animates the bar; React only refreshes its accessible seconds. */
export function TurnProgress({deadline,now,duration}:{deadline:number;now:number;duration:number}) {
  const initial=useMemo(()=>Math.min(duration,Math.max(0,deadline-now)),[deadline,duration]);
  const remaining=Math.min(duration,Math.max(0,deadline-now));
  return <div className="turn-progress" role="progressbar" aria-label={`剩餘 ${Math.ceil(remaining)} 秒`} aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Math.ceil(remaining)}>
    <span key={deadline} style={{animationDuration:`${duration}s`,animationDelay:`-${duration-initial}s`,transform:`scaleX(${remaining/duration})`}} />
  </div>;
}
