import { Children, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { tableSizes, TableGeometryContext } from './tableLayout';
export function TableStage({ children,portrait=false,onLayoutChange }: { children: ReactNode;portrait?:boolean;onLayoutChange?:()=>void }) {
  const root=useRef<HTMLDivElement>(null), viewport=useRef<HTMLDivElement>(null), [scale,setScale]=useState(1), [canvasWidth,setCanvasWidth]=useState(portrait?390:1520);
  const change=useRef(onLayoutChange),previousScale=useRef(1),previousWidth=useRef(canvasWidth);change.current=onLayoutChange;
  const size=portrait?tableSizes.portrait:tableSizes.landscape;
  useLayoutEffect(()=>{
    const element=viewport.current!;
    const resize=()=>{
      const available=element.clientWidth;
      const next=Math.max(.1,portrait?Math.min(available/size.width,1.25,Math.max(.8,element.clientHeight/size.height)):Math.min(available/size.width,element.clientHeight/size.height));
      const width=portrait?size.width:Math.max(size.width,available/next);
      if(Math.abs(previousScale.current-next)>=.0001||Math.abs(previousWidth.current-width)>=.01){previousScale.current=next;previousWidth.current=width;change.current?.();setScale(next);setCanvasWidth(width);}
    };
    const observer=new ResizeObserver(resize);observer.observe(element);resize();
    return ()=>observer.disconnect();
  },[portrait,size]);
  useLayoutEffect(()=>{
    if(!portrait)return;
    const frame=requestAnimationFrame(()=>{if(viewport.current)viewport.current.scrollTop=viewport.current.scrollHeight;});
    return()=>cancelAnimationFrame(frame);
  },[portrait,scale]);
  const content=Children.toArray(children);
  return <div className="table-stage" ref={root} style={{'--table-scale':scale,'--canvas-width':canvasWidth+'px','--canvas-height':size.height+'px'} as CSSProperties}>
    <div className="table-viewport" ref={viewport}><div className="table-frame"><div className="table-canvas"><TableGeometryContext.Provider value={`${portrait}:${scale}:${canvasWidth}`}>{content[0]}</TableGeometryContext.Provider></div></div></div>{content.slice(1)}
  </div>;
}
