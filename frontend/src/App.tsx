import { useEffect, useState } from 'react';
import { ReadbackMonitor, ReadbackLegend, AppSymbol } from './Monitor';
import { productText } from './presentation';
import { Activity, Airport, NavIcon, ProjectIntroduction, RuntimeMetrics, StartupScreen, Transcript, presets, pretty, time } from './SessionPresentation';
import { api, AUTH_EXPIRED_EVENT, configureAuth, signIn, signOut } from './api';
import type { Config, Preset, Scenario, Session } from './types';

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [identity, setIdentity] = useState<{ name: string } | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState('incorrect-readback');
  const [preset, setPreset] = useState<Preset>('partial');
  const [session, setSession] = useState<Session | null>(null);
  const [history, setHistory] = useState<Session[] | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(true);

  useEffect(() => {
    const expired = () => {
      setIdentity(null); setSession(null); setHistory(null); setSelectedTrace(null);
      setConnected(true);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  }, []);

  useEffect(() => {
    (async () => {
      const value = await api<Config>('/config');
      setConfig(value);
      await configureAuth(value);
      try { setIdentity(await api('/me')); }
      catch { return; }
      setScenarios(await api('/scenarios'));
      const saved = sessionStorage.getItem('clearance-gap-session');
      if (saved) {
        const active = await api<Session>(`/sessions/${saved}`);
        setSession(active);
      }
    })().catch(e => setError(e.message));
  }, []);

  useEffect(() => {
    if (!session || session.status === 'completed') return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<Session>(`/sessions/${session.sessionId}`);
        if (!stopped) { setSession(next); setConnected(true); }
      } catch { if (!stopped) setConnected(false); }
      if (!stopped) timer = setTimeout(poll, 500);
    };
    timer = setTimeout(poll, 350);
    return () => { stopped = true; clearTimeout(timer); };
  }, [session?.sessionId, session?.status]);

  async function run(id = scenarioId, behaviour = preset) {
    setBusy(true); setError(''); setHistory(null); setSelectedTrace(null);
    try {
      const scenario = scenarios.find(item => item.id === id);
      if (!scenario) throw new Error('The scenario catalogue is unavailable. Reload and try again.');
      const created = await api<Session>('/sessions', { scenarioId: id, scenarioVersion: scenario.version, preset: behaviour, playback: 'typed' }, crypto.randomUUID());
      sessionStorage.setItem('clearance-gap-session', created.sessionId);
      setSession(await api<Session>(`/sessions/${created.sessionId}/start`, {}, crypto.randomUUID()));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function control(operation: 'start' | 'pause' | 'resume') {
    if (!session) return;
    setBusy(true); setError('');
    try {
      setSession(await api<Session>(`/sessions/${session.sessionId}/${operation}`, {}, crypto.randomUUID()));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function choose() {
    setSession(null); setHistory(null);
    sessionStorage.removeItem('clearance-gap-session');
  }

  if (!config) return <StartupScreen unavailable={Boolean(error)}/>;
  const displayedMode = session && !history ? session.providerMode : config.providerMode;
  const identityLabel = identity ? config.authMode === 'cognito' ? 'Signed-in observer' : 'Local developer' : 'Sign in required';
  return <div className={`app-shell ${session && !history ? 'has-session' : ''}`}>
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Air Traffic Controller Assistant home"><span className="monogram" aria-hidden="true"><AppSymbol className="brand-symbol"/></span><span>Air Traffic Controller Assistant<small>Experimental prototype</small></span></a>
      <span className="nav-label">WORKSPACE</span>
      <nav aria-label="Main navigation">
        <a className="demo-nav-link" href="/recorded"><NavIcon kind="monitor"/>Recorded Demo</a>
        <button className={!history ? 'nav-active' : ''} aria-current={!history ? 'page' : undefined} onClick={() => setHistory(null)}><NavIcon kind="monitor"/>Live Demo</button>
        <a className="demo-nav-link sidebar-home" href="/"><span aria-hidden="true">←</span>Back to home</a>
        <button disabled={!identity} className={history ? 'nav-active' : ''} aria-current={history ? 'page' : undefined} onClick={() => api<Session[]>('/sessions').then(setHistory).catch(e => setError(e.message))}><NavIcon kind="history"/>My sessions</button>
      </nav>
      {session && !history && <div className="sidebar-airport"><Airport session={session}/></div>}
      <div className="sidebar-bottom"><div className="identity"><span className="avatar">{identity ? config.authMode === 'cognito' ? 'O' : 'L' : '·'}</span><span>{identityLabel}<small>{config.authMode === 'local' ? 'Local workspace' : 'Private sessions'}</small></span></div>
        {config.authMode === 'cognito' && <button className="text-button" onClick={() => identity ? signOut(config) : signIn()}>{identity ? 'Sign out' : 'Sign in'}</button>}
        <p>Simulated communications.<br/>Advisory assistance only.</p>
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <div className={`runtime-banner ${displayedMode === 'fixture' ? 'fixture' : 'live'}`} role="status"><span className="status-dot"/>{displayedMode === 'fixture' ? <span><strong>Fixture mode</strong> · Decider and Bedrock are not connected.</span> : <span><strong>Live providers</strong> · Strands Decider 2B + Amazon Bedrock</span>}</div>
        <div className="topbar-actions"><span className="badge neutral">Experimental</span>{config.authMode === 'cognito' && <button className="text-button mobile-auth" onClick={() => identity ? signOut(config) : signIn()}>{identity ? 'Sign out' : 'Sign in'}</button>}</div>
      </header>
      <main className={`page ${session && !history ? 'session-page' : !history ? 'home-page' : ''}`}>
        {error && <div role="alert" className="error-banner">{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
        {!connected && <div role="status" className="error-banner">Connection interrupted. Reconnecting to the saved session…</div>}
        {!identity ? <div className="exercise-home scroll-region" tabIndex={0} aria-label="About Air Traffic Controller Assistant and getting started"><ProjectIntroduction/><section className="signin panel"><h2>Live Demo · sign in to run a scenario</h2><p>For invited AWS hackathon judges and testers. This mode calls the deployed models and saves private sessions to your account.</p><button className="primary" onClick={signIn}>Sign in</button></section></div>
          : history ? <><div className="page-heading"><div><h1>My sessions</h1><p className="subtitle">Return to a saved live session and inspect its decisions.</p></div><button onClick={choose}>New live scenario</button></div><div className="history-list scroll-region" tabIndex={0} aria-label="Saved sessions">{!history.length && <p className="muted">No sessions yet.</p>}{history.map(s => <button className="panel history-item" key={s.sessionId} onClick={() => api<Session>(`/sessions/${s.sessionId}`).then(value => { setSession(value); setHistory(null); setSelectedTrace(null); sessionStorage.setItem('clearance-gap-session', value.sessionId); }).catch(e => setError(e.message))}><strong>{pretty(s.scenarioId.replaceAll('-', ' '))}</strong><span>{presets[s.preset]?.title}</span><span className="badge neutral">{s.status}</span><small>{new Date(s.createdAt).toLocaleString()}</small></button>)}</div></>
          : !session ? <div className="exercise-home scroll-region" tabIndex={0} aria-label="Project introduction and scenario setup">
            <ProjectIntroduction/>
            <div className="setup-heading"><h2>Choose a scenario</h2><p>Suggested first run: <strong>Incorrect readback</strong> + <strong>Correction only</strong></p></div>
            <div className="exercise-setup">
              <section className="scenario-section"><h2 className="setup-step-heading"><span>1.</span> Choose a scenario</h2><div className="scenario-list">{scenarios.map((scenario, index) => <button key={scenario.id} className={`scenario-card ${scenario.id === scenarioId ? 'selected' : ''}`} onClick={() => setScenarioId(scenario.id)} aria-pressed={scenario.id === scenarioId}>
                <span className="scenario-number">0{index + 1}</span><span className="scenario-copy"><strong>{productText(scenario.title)}</strong><span>{productText(scenario.description)}</span></span><span className="radio-dot"/>
              </button>)}</div><div className="scenario-objective"><span className="eyebrow">WHAT THE ASSISTANT CHECKS</span><p>{productText(scenarios.find(s => s.id === scenarioId)?.objective || '')}</p></div></section>
              <section className="response-section"><h2 className="setup-step-heading"><span>2.</span> Run and observe</h2><div className="panel setup-panel"><h3>Controller response</h3><p className="muted small">Human roles are simulated. Both sides are scripted.</p><div className="behaviour-list">{(Object.keys(presets) as Preset[]).map(key => <button key={key} className={`option ${preset === key ? 'selected' : ''}`} onClick={() => setPreset(key)} aria-pressed={preset === key}><span className="radio-dot"/><span><strong>{presets[key].title}</strong><small>{presets[key].detail}</small></span></button>)}</div>
                <button className="primary run-button" disabled={busy || !scenarios.length} onClick={() => run()}>{busy ? 'Creating session…' : 'Run live scenario'}<span aria-hidden="true">→</span></button><p className="setup-note">All messages and actions advance automatically.</p>
              </div></section>
            </div>
          </div> : <>
            <div className="page-heading run-heading"><div className="run-title"><h1>Readback monitoring</h1><p className="subtitle">{productText(session.title)} <span>·</span> {session.initialSetup?.aircraft || 'AIR123'} · Runway {session.initialSetup?.runway || '—'}</p></div><RuntimeMetrics session={session}/><div className="run-controls"><span className="run-time" aria-label="Scenario time">{time(session.simulationTimeMs)} <span className="muted">/ {time(session.durationMs)}</span></span><span className={`badge ${session.status === 'running' ? 'green' : session.status === 'paused' ? 'purple' : 'neutral'}`}>{session.simulationFinished && session.status === 'running' ? 'Reviewing evidence' : session.status === 'running' ? 'Live scenario running' : session.status === 'completed' ? 'Live scenario complete' : session.status}</span>
              {session.status !== 'completed' && <button className="primary" disabled={busy} onClick={() => control(session.status === 'running' ? 'pause' : session.status === 'ready' ? 'start' : 'resume')}>{session.status === 'running' ? 'Pause' : session.status === 'ready' ? 'Run live scenario' : 'Resume'}</button>}
              <button disabled={busy} onClick={() => run(session.scenarioId, session.preset)}>Run again (live)</button>
              <button className="icon-button" onClick={choose} title="Change scenario" aria-label="Change scenario"><NavIcon kind="exercises"/></button>
            </div></div>
            <div className="timeline-bar"><progress aria-label="Scenario timeline" value={session.simulationTimeMs} max={session.durationMs}/></div>
            <ReadbackMonitor session={session} connected={connected}/>
            <ReadbackLegend/>
            <details className="mobile-airport"><summary>Airport surface · Runway {session.initialSetup?.runway || '—'}</summary><Airport session={session}/></details>
            <div className="workspace"><Transcript events={session.events}/><Activity session={session} selectedId={selectedTrace} onSelect={setSelectedTrace}/></div>
          </>}
        <footer><span>Experimental ATC assistance prototype · Simulated communications</span><span>{displayedMode === 'fixture' ? 'Development fixtures · No model inference' : 'Experimental model results'}</span></footer>
      </main>
    </div>
  </div>;
}

