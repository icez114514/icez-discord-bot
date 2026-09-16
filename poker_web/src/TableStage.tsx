import type { ReactNode } from 'react';

/** The felt fills its container; seats and cards size independently. */
export function TableStage({ children }: { children: ReactNode }) {
  return <div className="table-stage">{children}</div>;
}
