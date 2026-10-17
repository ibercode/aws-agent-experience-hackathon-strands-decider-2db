import type { Session } from './types';

type ExecutionTimestamps = Pick<Session, 'status' | 'startedAt' | 'endedAt'>;

// Wall-clock duration includes pauses and final model processing. Scenario time
// is a separate simulated clock and must never cap the live execution timer.
export function executionElapsedMs(session: ExecutionTimestamps, now: number): number | null {
  if (!session.startedAt) return session.status === 'ready' ? 0 : null;
  const start = Date.parse(session.startedAt);
  const end = session.status === 'completed'
    ? session.endedAt ? Date.parse(session.endedAt) : NaN
    : now;
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}
