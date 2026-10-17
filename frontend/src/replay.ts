import type { InitialSetup, Preset, Session } from './types';

export interface RecordingSummary {
  quality: string;
  errorTraces: number;
  runtimeErrors: number;
  bedrockUsageIncomplete: boolean;
  verifiedLiveInference: boolean;
}
export interface RecordingEntry {
  id: string;
  recordingId: string;
  file: string;
  sha256: string;
  scenarioId: string;
  scenarioVersion: string;
  title: string;
  description: string;
  objective: string;
  initialSetup: InitialSetup;
  preset: Preset;
  durationMs: number;
  recordingDurationMs: number;
  summary: RecordingSummary;
}
export interface RecordingFrame { elapsedMs: number; view: Session }
export interface Recording {
  schemaVersion: 'atc-assistant-public-replay/1';
  recordingId: string;
  timelineVersion: string;
  frames: RecordingFrame[];
  summary: RecordingSummary;
}

// Use the original wall-clock timeline. The simulation clock can stop while a
// model request is pending; substituting it would reveal final results early.
export function frameAt(frames: RecordingFrame[], elapsedMs: number): RecordingFrame {
  if (!frames.length) throw new Error('This recording has no frames.');
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (frames[middle].elapsedMs <= elapsedMs) low = middle;
    else high = middle - 1;
  }
  return frames[low];
}

export function validateRecording(value: unknown, entry: RecordingEntry): Recording {
  const recording = value as Recording;
  if (recording?.schemaVersion !== 'atc-assistant-public-replay/1'
      || recording.recordingId !== entry.recordingId || !Array.isArray(recording.frames)
      || !recording.frames.length || recording.frames[0].elapsedMs !== 0) {
    throw new Error('The recording format is unavailable. Please reload the page.');
  }
  let previous = -1;
  for (const frame of recording.frames) {
    const session = frame.view;
    if (!Number.isFinite(frame.elapsedMs) || frame.elapsedMs < previous || !session
        || session.providerMode !== 'live' || session.scenarioId !== entry.scenarioId
        || session.scenarioVersion !== entry.scenarioVersion || session.preset !== entry.preset
        || !Array.isArray(session.events) || !Array.isArray(session.traces)
        || !Array.isArray(session.assessments) || !session.observation) {
      throw new Error('This recording has an invalid timeline. Choose another recording.');
    }
    previous = frame.elapsedMs;
  }
  return recording;
}

export async function fetchRecording(assetUrl: string, entry: RecordingEntry, signal: AbortSignal): Promise<Recording> {
  const url = new URL(assetUrl, location.origin);
  if (url.origin !== location.origin || url.username || url.password || url.pathname.startsWith('/api/')) {
    throw new Error('The recording asset address is invalid.');
  }
  // Public playback must never attach a live-session token or browser cookies.
  const response = await fetch(url, { signal, credentials: 'omit', mode: 'same-origin', referrerPolicy: 'no-referrer' });
  if (!response.ok) throw new Error('The recording could not be loaded. Please try again.');
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  if (hash !== entry.sha256) throw new Error('The recording did not match the published catalogue. Reload and try again.');
  return validateRecording(JSON.parse(new TextDecoder().decode(bytes)), entry);
}
