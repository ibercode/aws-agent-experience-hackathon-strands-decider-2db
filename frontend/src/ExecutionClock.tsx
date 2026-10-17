import { useEffect, useState } from 'react';
import { executionElapsedMs } from './executionTime';
import { time } from './SessionPresentation';
import type { Session } from './types';

export function ExecutionClock({ session }: { session: Session }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setNow(Date.now());
    if (!session.startedAt || session.status === 'completed') return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [session.sessionId, session.startedAt, session.status]);

  const elapsed = executionElapsedMs(session, now);
  return <span className="run-time" role="timer" aria-label="Elapsed execution time"
    title="Time since this run started, including pauses and model processing.">
    <span className="muted">Elapsed </span>{elapsed === null ? '—' : time(elapsed)}
  </span>;
}
