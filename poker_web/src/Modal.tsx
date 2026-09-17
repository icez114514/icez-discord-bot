import { useEffect, useId, useRef, type ReactNode } from 'react';

export function Modal({ title, onClose, children, dismissOnBackdrop = false, className, fitVisualViewport = false }: { title: string; onClose: () => void; children: ReactNode; dismissOnBackdrop?: boolean; className?: string; fitVisualViewport?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    dialog.showModal();
    return () => { dialog.close(); previous?.focus(); };
  }, []);
  useEffect(()=>{
    if(!fitVisualViewport||!window.visualViewport)return;
    const viewport=window.visualViewport,dialog=ref.current!;
    const resize=()=>{dialog.style.bottom=Math.max(0,innerHeight-viewport.height-viewport.offsetTop)+'px';dialog.style.maxHeight=Math.max(120,viewport.height-12)+'px';};
    viewport.addEventListener('resize',resize);viewport.addEventListener('scroll',resize);resize();
    return()=>{viewport.removeEventListener('resize',resize);viewport.removeEventListener('scroll',resize);};
  },[fitVisualViewport]);
  return <dialog className={className} ref={ref} aria-labelledby={id} onClick={event => { if (dismissOnBackdrop && event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }} onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="panel-top"><h2 id={id}>{title}</h2><button className="text" aria-label="關閉對話框" onClick={onClose}>關閉</button></div>
    {children}
  </dialog>;
}
