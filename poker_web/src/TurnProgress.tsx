import { useMemo } from 'react';
/** A CSS-driven SVG ring keeps the countdown smooth without frame-by-frame renders. */
export function TurnProgress({deadline,now,duration}:{deadline:number;now:number;duration:number}) {
  const initial=useMemo(()=>Math.min(duration,Math.max(0,deadline-now)),[deadline,duration]);
  const remaining=Math.min(duration,Math.max(0,deadline-now));
  return <div className="turn-progress" role="progressbar" aria-label={`剩餘 ${Math.ceil(remaining)} 秒`} aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Math.ceil(remaining)}>
    <svg viewBox="0 0 100 100" aria-hidden="true"><circle className="timer-track" cx="50" cy="50" r="47"/><circle key={deadline} className="timer-ring" cx="50" cy="50" r="47" pathLength="100" style={{animationDuration:`${duration}s`,animationDelay:`-${duration-initial}s`,strokeDashoffset:100*(1-remaining/duration)}}/></svg>
    <b aria-hidden="true">{Math.ceil(remaining)}</b>
  </div>;
}
