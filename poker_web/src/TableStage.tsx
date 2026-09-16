import { useLayoutEffect, useRef, type ReactNode } from 'react';

/** Fit the whole desktop table without distorting cards or moving the controls. */
export function TableStage({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const stage = ref.current;
    if (!stage) return;
    const fit = () => {
      if (!stage.clientWidth || !stage.clientHeight) return;
      const scale = Math.min(stage.clientWidth / 1100, stage.clientHeight / 620, 1.2);
      stage.style.setProperty('--table-scale', String(scale));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(stage);
    fit();
    return () => observer.disconnect();
  }, []);
  return <div className="table-stage" ref={ref}>{children}</div>;
}
