import { useLayoutEffect, useRef, type ReactNode } from 'react';

/** Fit the whole desktop table without distorting cards or moving the controls. */
export function TableStage({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const stage = ref.current;
    if (!stage) return;
    const fit = () => {
      if (!stage.clientWidth || !stage.clientHeight) return;
      const width = Math.max(1, stage.clientWidth - 24);
      const height = Math.max(1, stage.clientHeight - 16);
      const canvasWidth = Math.min(1600, Math.max(1100, width / height * 620));
      const scale = Math.min(width / canvasWidth, height / 620, 1.2);
      stage.style.setProperty('--table-width', canvasWidth + 'px');
      stage.style.setProperty('--table-scale', String(scale));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(stage);
    fit();
    return () => observer.disconnect();
  }, []);
  return <div className="table-stage" ref={ref}>{children}</div>;
}
