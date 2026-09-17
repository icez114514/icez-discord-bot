import { Children, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { tableSizes, TableGeometryContext } from './tableLayout';
export function TableStage({ children,portrait=false,onLayoutChange }: { children: ReactNode;portrait?:boolean;onLayoutChange?:()=>void }) {
  const root=useRef<HTMLDivElement>(null), viewport=useRef<HTMLDivElement>(null), [scale,setScale]=useState(1);
  const change=useRef(onLayoutChange),previousScale=useRef(1);change.current=onLayoutChange;
  const size=portrait?tableSizes.portrait:tableSizes.landscape;
  useLayoutEffect(()=>{
    const element=root.current!;
    const media=matchMedia('(max-width: 899px), (max-height: 599px)');
    const resize=()=>{
      const controls=element.querySelector<HTMLElement>('.table-action-slot');
      const reserved=controls&&getComputedStyle(controls).position==='relative'?controls.offsetHeight+10:0;
      const available=Math.min(viewport.current?.clientWidth??element.clientWidth,element.clientWidth);
      const next=Math.max(.1,portrait?Math.min(available/size.width,1.25,Math.max(.8,Math.max(0,element.clientHeight-reserved)/size.height)):media.matches?available/size.width:Math.min(available/size.width,Math.max(0,element.clientHeight-reserved)/size.height));
      if(Math.abs(previousScale.current-next)>=.0001){previousScale.current=next;change.current?.();setScale(next);}
    };
    const observer=new ResizeObserver(resize);observer.observe(element);media.addEventListener('change',resize);resize();
    const frame=requestAnimationFrame(()=>{if(portrait&&viewport.current)viewport.current.scrollTop=viewport.current.scrollHeight;});
    return ()=>{cancelAnimationFrame(frame);observer.disconnect();media.removeEventListener('change',resize);};
  },[portrait,size]);
  useLayoutEffect(()=>{
    if(!portrait)return;
    const frame=requestAnimationFrame(()=>{if(viewport.current)viewport.current.scrollTop=viewport.current.scrollHeight;});
    return()=>cancelAnimationFrame(frame);
  },[portrait,scale]);
  const content=Children.toArray(children);
  return <div className="table-stage" ref={root} style={{'--table-scale':scale,'--canvas-width':size.width+'px','--canvas-height':size.height+'px'} as CSSProperties}>
    <div className="table-viewport" ref={viewport}><div className="table-frame"><div className="table-canvas"><TableGeometryContext.Provider value={`${portrait}:${scale}`}>{content[0]}</TableGeometryContext.Provider></div></div></div>{content.slice(1)}
  </div>;
}
