import { useEffect, useRef, useState } from 'react';
import { AppSymbol, ReadbackLegend, ReadbackMonitor } from './Monitor';
import { Activity, Airport, NavIcon, RuntimeMetrics, Transcript, presets, time } from './SessionPresentation';
import { productText } from './presentation';
import { fetchRecording, frameAt, type Recording, type RecordingEntry } from './replay';
import type { Preset } from './types';
import manifest from '../../recordings/public/v3/manifest.json';

// URL-only imports let Vite fingerprint the files without including their JSON
// in JavaScript. Only the selected recording is downloaded and parsed.
const assets = import.meta.glob('../../recordings/public/v3/*.json', { query: '?url', import: 'default', eager: true }) as Record<string, string>;
const entries = manifest.recordings as RecordingEntry[];
const scenarioOrder = ['incorrect-readback', 'words-versus-actions', 'missing-evidence'];
const scenarios = [...new Map(entries.map(entry => [entry.scenarioId, entry])).values()]
  .sort((a, b) => scenarioOrder.indexOf(a.scenarioId) - scenarioOrder.indexOf(b.scenarioId));

export default function RecordedDemoApp() {
  const [scenarioId, setScenarioId] = useState('incorrect-readback');
  const [preset, setPreset] = useState<Preset>('partial');
  const [recording, setRecording] = useState<Recording | null>(null);
  const [activeEntry, setActiveEntry] = useState<RecordingEntry | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const elapsed = useRef(0);
  const request = useRef<AbortController | null>(null);
  const selected = entries.find(entry => entry.scenarioId === scenarioId && entry.preset === preset);
  const totalMs = recording?.frames.at(-1)?.elapsedMs || 0;
  const session = recording ? frameAt(recording.frames, elapsedMs).view : null;
  const finished = Boolean(recording && elapsedMs >= totalMs);

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    const pauseHidden = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', pauseHidden);
    return () => document.removeEventListener('visibilitychange', pauseHidden);
  }, []);
  useEffect(() => {
    if (!playing || !recording) return;
    let previous = performance.now();
    let animation = 0;
    const tick = (now: number) => {
      elapsed.current = Math.min(totalMs, elapsed.current + (now - previous) * speed);
      previous = now;
      setElapsedMs(elapsed.current);
      if (elapsed.current >= totalMs) setPlaying(false);
      else animation = requestAnimationFrame(tick);
    };
    animation = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animation);
  }, [playing, recording, totalMs, speed]);

  function seek(value: number) {
    elapsed.current = Math.max(0, Math.min(totalMs, value));
    setElapsedMs(elapsed.current);
    setPlaying(false);
  }
  function restart() { elapsed.current = 0; setElapsedMs(0); setSelectedTrace(null); setPlaying(true); }
  function choose() {
    request.current?.abort(); setLoading(false); setRecording(null); setActiveEntry(null);
    setPlaying(false); setSelectedTrace(null); setError('');
  }
  async function play() {
    if (!selected) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError('');
    try {
      const asset = assets[`../../recordings/public/v3/${selected.file}`];
      if (!asset) throw new Error('This recording is not in the published catalogue.');
      const result = await fetchRecording(asset, selected, controller.signal);
      if (controller.signal.aborted) return;
      elapsed.current = 0; setElapsedMs(0); setSelectedTrace(null); setActiveEntry(selected);
      setRecording(result); setPlaying(true);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }
  const showingRecording = session;
  return <div className={`app-shell recorded-app ${showingRecording ? 'has-session' : ''}`}>
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Air Traffic Controller Assistant home"><span className="monogram" aria-hidden="true"><AppSymbol className="brand-symbol"/></span><span>Air Traffic Controller Assistant<small>Experimental prototype</small></span></a>
      <span className="nav-label">EXPLORE THE PROJECT</span>
      <nav aria-label="Demo navigation">
        <button className="nav-active" aria-current="page" onClick={choose}><NavIcon kind="monitor"/>Recorded Demo</button>
        <a className="demo-nav-link" href="/live"><NavIcon kind="agent"/>Live Demo</a>
        <a className="demo-nav-link sidebar-home" href="/"><span aria-hidden="true">←</span>Back to home</a>
      </nav>
      {showingRecording && <div className="sidebar-airport"><Airport session={session}/></div>}
      <div className="sidebar-bottom"><div className="identity"><span className="avatar" aria-hidden="true">▶</span><span>Public recorded demo<small>No account needed</small></span></div><p>Original model results.<br/>No inference during playback.</p></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="runtime-banner recorded" role="status"><span className="status-dot"/><span><strong>Recorded demo</strong> · Real Strands Decider 2B + Amazon Bedrock calls from previous live sessions. Model results and measured response times are recorded, not mocked. No models run during playback.</span></div></header>
      <main className={`page ${showingRecording ? 'session-page' : 'home-page'}`}>
        {error && <div role="alert" className="error-banner">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
        {!session ? <div className="exercise-home scroll-region" tabIndex={0} aria-label="Recorded scenario selection">
          <div className="setup-heading"><h1>Choose a recorded example</h1><div className="setup-instructions"><ol><li>Choose a scenario.</li><li>Choose a controller response.</li><li>Press <strong>Play recording</strong>.</li></ol><p>Messages and decisions play automatically. Pause and select an <strong>Agent activity</strong> step to inspect its evidence.</p></div></div>
          <div className="exercise-setup">
            <section className="scenario-section"><h2 className="setup-step-heading"><span>1.</span> Choose a scenario</h2><div className="scenario-list">{scenarios.map((scenario, index) => <button disabled={loading} key={scenario.scenarioId} className={`scenario-card ${scenario.scenarioId === scenarioId ? 'selected' : ''}`} onClick={() => setScenarioId(scenario.scenarioId)} aria-pressed={scenario.scenarioId === scenarioId}><span className="scenario-number">0{index + 1}</span><span className="scenario-copy"><strong>{productText(scenario.title)}</strong><span>{productText(scenario.description)}</span></span><span className="radio-dot"/></button>)}</div><div className="scenario-objective"><span className="eyebrow">WHAT THE ASSISTANT CHECKS</span><p>{productText(selected?.objective || '')}</p></div></section>
            <section className="response-section"><h2 className="setup-step-heading"><span>2.</span> Run and observe</h2><div className="panel setup-panel"><h3>Controller response</h3><p className="muted small">Both human roles are scripted. The AI decisions were recorded live.</p><div className="behaviour-list">{(Object.keys(presets) as Preset[]).map(key => <button disabled={loading} key={key} className={`option ${preset === key ? 'selected' : ''}`} onClick={() => setPreset(key)} aria-pressed={preset === key}><span className="radio-dot"/><span><strong>{presets[key].title}</strong><small>{presets[key].detail}</small></span></button>)}</div>
              <div className="recording-start">
              {selected && <div className="recording-preview"><span>Recording length <strong>{time(selected.recordingDurationMs)}</strong></span><span>{selected.summary.errorTraces > 0 || selected.summary.quality === 'degraded' ? 'Includes retained failures' : 'Original live run'}</span></div>}
              <h3 className="recording-start-heading"><span>3.</span> Press Play recording</h3>
              <button className="primary run-button" disabled={loading || !selected} onClick={play}>{loading ? 'Loading recording…' : 'Play recording'}<span aria-hidden="true">▶</span></button><p className="setup-note">Messages, alerts and decisions advance automatically.<br/>No sign-in, model calls or session creation.</p>
              </div>
            </div></section>
          </div>
        </div> : <>
          <div className="page-heading run-heading"><div className="run-title"><h1>Readback monitoring</h1><p className="subtitle">{productText(session.title)} · {presets[session.preset].title}</p></div><RuntimeMetrics session={session} recorded onInspect={() => setPlaying(false)}/><div className="run-controls"><span className="badge blue">{finished ? 'Recording complete' : playing ? 'Recording playing' : 'Recording paused'}</span><button className="primary" onClick={() => finished ? restart() : setPlaying(value => !value)}>{finished ? 'Play again' : playing ? 'Pause' : 'Resume'}</button><button onClick={restart}>Restart</button><button className="icon-button" onClick={choose} title="Choose another recording" aria-label="Choose another recording"><NavIcon kind="exercises"/></button></div></div>
          <div className="recording-timeline"><label htmlFor="recording-progress">Playback <strong>{time(elapsedMs)} / {time(totalMs)}</strong></label><input id="recording-progress" type="range" min={0} max={totalMs} value={elapsedMs} step="any" onChange={event => seek(Number(event.target.value))} aria-valuetext={`${time(elapsedMs)} of ${time(totalMs)}`}/><label className="speed-control">Speed <select value={speed} onChange={event => setSpeed(Number(event.target.value))}><option value={1}>1×</option><option value={2}>2×</option></select></label><button className="text-button" onClick={() => seek(totalMs)}>View final result</button></div>
          <ReadbackMonitor session={session} connected recorded/>
          <ReadbackLegend/>
          <details className="mobile-airport"><summary>Airport surface · Runway {session.initialSetup?.runway || '—'}</summary><Airport session={session}/></details>
          <div className="workspace" key={recording?.recordingId}><Transcript events={session.events} animateNewMessages={playing}/><Activity session={session} selectedId={selectedTrace} onSelect={setSelectedTrace} recorded paused={!playing} onInspect={() => setPlaying(false)}/></div>
          {activeEntry && <div className="recording-provenance"><span>Recorded live · Fictional scripted scenario · Timeline reconstructed from saved event and decision timestamps</span><span>Scenario clock {time(session.simulationTimeMs)}{session.bedrockUsageIncomplete ? ' · Token usage partial' : ''}{activeEntry.summary.errorTraces > 0 ? ` · ${activeEntry.summary.errorTraces} original runtime errors retained` : ''}</span></div>}
        </>}
        <footer><span>Experimental ATC assistance prototype · Simulated communications</span><span>Public recording · No live inference</span></footer>
      </main>
    </div>
  </div>;
}
