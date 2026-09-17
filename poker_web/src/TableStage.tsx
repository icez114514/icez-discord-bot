import { Children, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
/** Every table object is measured in the same 1520 x 1024 reference canvas. */
export function TableStage({ children }: { children: ReactNode }) {
  const root=useRef<HTMLDivElement>(null), [scale,setScale]=useState(1);
  useLayoutEffect(()=>{
    const element=root.current!;
    const media=matchMedia('(max-width: 899px), (max-height: 599px)');
    const resize=()=>{
      const controls=element.querySelector<HTMLElement>('.table-action-slot');
      const reserved=controls&&getComputedStyle(controls).position==='relative'?controls.offsetHeight+10:0;
      const next=Math.max(.1,media.matches?element.clientWidth/1520:Math.min(element.clientWidth/1520,Math.max(0,element.clientHeight-reserved)/1024));
      setScale(old=>Math.abs(old-next)<.0001?old:next);
    };
    const observer=new ResizeObserver(resize);observer.observe(element);media.addEventListener('change',resize);resize();
    return ()=>{observer.disconnect();media.removeEventListener('change',resize);};
  },[]);
  const content=Children.toArray(children);
  return <div className="table-stage" ref={root} style={{'--table-scale':scale} as CSSProperties}>
    <div className="table-frame"><div className="table-canvas">{content[0]}</div></div>{content.slice(1)}
  </div>;
}
