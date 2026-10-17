import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { AppSymbol } from './Monitor';
import { productText, actorLabel } from './presentation';
import type { Answer, Assessment, Event, Preset, Session, Trace } from './types';

export const presets: Record<Preset, { title: string; detail: string }> = {
  missed: { title: 'No correction', detail: 'No corrective action is scripted.' },
  partial: { title: 'Correction only', detail: 'Corrects the issue; no controller verification check is recorded.' },
  complete: { title: 'Correction + observation', detail: 'Corrects the issue and checks the available observation.' },
};
export const time = (ms: number) => `${Math.floor(ms / 60000).toString().padStart(2, '0')}:${Math.floor(ms / 1000 % 60).toString().padStart(2, '0')}`;
export const duration = (ms?: number) => ms == null ? '—' : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
export const pretty = (value: string) => value.replaceAll('_', ' ');

export function StartupScreen({ unavailable }: { unavailable: boolean }) {
  return <main className="startup-page">
    <header className="page-heading">
      <a className="brand" href="/" aria-label="Air Traffic Controller Assistant home"><span className="monogram" aria-hidden="true"><AppSymbol className="brand-symbol"/></span><span>Air Traffic Controller Assistant<small>Experimental prototype</small></span></a>
      <a className="button-link home-link" href="/"><span aria-hidden="true">←</span>Back to home</a>
    </header>
    {unavailable ? <>
      <section className="service-unavailable panel" role="status" aria-labelledby="service-status-title">
        <div><span className="eyebrow">SERVICE STATUS</span><h2 id="service-status-title">Live Demo temporarily unavailable</h2>
          <p>We can’t reach the live service right now. You can explore the project below or return home for recorded demos.</p></div>
        <div className="service-actions"><button className="primary" onClick={() => window.location.reload()}>Retry</button></div>
      </section>
      <ProjectIntroduction/>
    </> : <p role="status" aria-busy="true">Opening Live Demo…</p>}
  </main>;
}

export function ProjectIntroduction({ recorded = false }: { recorded?: boolean }) {
  return <section className="project-intro" aria-labelledby="project-title">
    <div className="intro-copy"><span className="eyebrow">SIMULATED COMMUNICATIONS · EXPERIMENTAL PROTOTYPE</span><h1 id="project-title">Air Traffic Controller Assistant</h1>
      <p className="project-description">An agent that monitors a human controller’s instruction and a pilot’s readback, flags possible contradictions, and checks the available aircraft observations.</p>
      <p className="project-goal"><strong>Our goal:</strong> make a communication gap visible while keeping the human controller in charge. Assistant replies are advisory; the agent never issues radio commands.</p>
      <p className="agent-explainer"><strong>How it works:</strong> Strands Decider 2B makes <strong>Choice, Yes/No and Score</strong> decisions. Amazon Bedrock prepares an explanation, and Decider checks its factual findings against recorded evidence before publication.</p>
    </div>
    <div className="getting-started"><h2>How to use this demo</h2><ol>
      <li><strong>Choose a scenario</strong><p>Pick a scenario and the scripted controller response.</p></li>
      <li><strong>Run and observe</strong><p>Select <b>{recorded ? 'Play recording' : 'Run live scenario'}</b>. Simulated controller and pilot messages appear automatically as text.</p></li>
      <li><strong>Inspect the assistant</strong><p>Watch the readback status, then select an <b>Activity</b> step or <b>View evidence</b> to understand each decision. Pause at any time.</p></li>
    </ol></div>
  </section>;
}

export function Airport({ session: s }: { session: Session }) {
  const o = s.observation;
  const physical = s.monitor?.physical;
  const setup = s.initialSetup;
  const aircraft = setup?.aircraft || 'AIR123';
  const runway = setup?.runway || '—';
  const reciprocal = setup?.reciprocalRunway || '—';
  const x = Math.max(76, Math.min(203, 126 + o.distanceBeforeHoldM * 1.35));
  const stale = o.status === 'stale';
  const observedDistance = `${Math.abs(o.distanceBeforeHoldM).toFixed(0)} metres ${o.distanceBeforeHoldM >= 0 ? 'before' : 'beyond'} the holding point`;
  const gridId = useId().replaceAll(':', '');
  return <section className="panel airport"><div className="panel-heading"><h2>Airport surface</h2><span className={`badge ${stale || physical?.status === 'runway_entered' ? 'amber' : 'neutral'}`}>{physical?.title || (stale ? 'Position unverified' : 'Recorded observation')}</span></div>
    <div className="map-canvas"><svg viewBox="0 0 240 285" role="img" aria-label={`Runway ${reciprocal} at the top and ${runway} at the bottom. ${aircraft} last observed ${observedDistance}. ${stale ? 'Current position unverified.' : `Observed at ${time(o.observedAtMs)}.`}`}>
      <defs><pattern id={gridId} width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0v20" fill="none" stroke="#dce6f0" strokeWidth=".6"/></pattern></defs>
      <rect width="240" height="285" fill="#edf2f8"/><rect width="240" height="285" fill={`url(#${gridId})`}/>
      <path d="M99 169H240M196 0v169M15 111h38" fill="none" stroke="#d1dce8" strokeWidth="21"/>
      <rect x="47" y="12" width="51" height="232" rx="3" fill="#61758b" stroke="#8b9aab" strokeWidth="3"/>
      <path d="M72.5 65v125" stroke="white" strokeWidth="2" strokeDasharray="14 12"/>
      {[54,61,68,77,84,91].map(px => <path key={px} d={`M${px} 18v14m0 191v14`} stroke="white" strokeWidth="2"/>)}
      <text x="72.5" y="55" textAnchor="middle" className="runway-number">{reciprocal}</text><text x="72.5" y="216" textAnchor="middle" className="runway-number">{runway}</text>
      <path d="M101 169H238" stroke="#6a94c5" strokeWidth="1.5" strokeDasharray="6 5"/>
      <path d="M119 152v34m5-34v34" stroke="#d3a731" strokeWidth="2"/><path d="M113 152v34" stroke="#d3a731" strokeWidth="2" strokeDasharray="4 3"/>
      <text x="126" y="137" className="map-amber">Holding point</text>
      <text x="216" y="105" textAnchor="middle" className="map-muted">{setup?.taxiway ? `TWY ${setup.taxiway}` : 'TAXIWAY'}</text>
      <g transform={`translate(${x} 169) rotate(-90)`} opacity={stale ? .65 : 1}>
        <circle r="20" fill="#fff" fillOpacity=".8" stroke={stale ? '#be8a29' : '#789fcd'} strokeDasharray={stale ? '3 3' : undefined}/>
        <path d="M0-21c3 0 3 5 3 9v7L19 6v5L3 5v11l6 6v3L0 21l-9 4v-3l6-6V5l-16 6V6L-3-5v-7c0-4 0-9 3-9Z" fill="white" stroke="#234e82" strokeWidth="1.4"/>
        <path d="M0-17v37" stroke="#6d9ad0" strokeWidth="1.1"/>
      </g>
      <rect x="110" y="202" width="121" height="61" rx="5" fill="white" stroke="#a1b9d5"/>
      <text x="120" y="219" className="map-label">{aircraft}</text>
      <text x="120" y="236" className="map-detail">{o.distanceBeforeHoldM >= 0 ? `${o.distanceBeforeHoldM.toFixed(0)} m before hold` : 'Beyond hold'}</text>
      <text x="120" y="251" className="map-detail">Observed {time(o.observedAtMs)}</text>
      <text x="12" y="278" className="map-scale">Schematic · Not to scale</text>
    </svg></div>
    <div className={`map-note ${stale ? 'stale' : ''}`}><span aria-hidden="true">{stale ? '!' : '◉'}</span>{stale ? `Observed ${(o.ageMs / 1000).toFixed(0)} s ago · Current position unverified` : physical?.detail || `Observed at ${time(o.observedAtMs)} · ${o.speedMps.toFixed(1)} m/s`}</div>
  </section>;
}

function TypedText({ event, animate }: { event: Event; animate?: boolean }) {
  const full = productText(event.payload.text || '');
  const reducedMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const [length, setLength] = useState(!reducedMotion && (animate ?? Date.now() - new Date(event.recordedAt).getTime() < 2500) ? 0 : full.length);
  useEffect(() => { if (animate === false && length < full.length) { setLength(full.length); return; } if (reducedMotion || length >= full.length) return; const timer = setTimeout(() => setLength(value => Math.min(value + 3, full.length)), 30); return () => clearTimeout(timer); }, [length, full, animate, reducedMotion]);
  const visibleLength = reducedMotion || animate === false ? full.length : length;
  return <span>{full.slice(0, visibleLength)}{visibleLength < full.length && <span className="typing-caret" aria-hidden="true">▍</span>}</span>;
}
export function Transcript({ events, animateNewMessages }: { events: Event[]; animateNewMessages?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const messages = events.filter(e => ['trainee_instruction', 'pilot_readback', 'trainee_observation_check', 'simulator_action'].includes(e.type));
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [messages.length]);
  return <section className="panel radio"><div className="panel-heading"><h2>Communications</h2><span className="badge blue">Automatic replay</span></div><div className="radio-history scroll-region" ref={ref} aria-live="polite" tabIndex={0} aria-label="Simulated communications">
    {!messages.length && <p className="muted waiting">Waiting for the first transmission…</p>}{messages.map(event => <article className={`radio-message ${event.actor}`} key={event.eventId}><div className="radio-meta"><time>{time(event.simulationTimeMs)}</time><strong>{actorLabel(event.actor)}</strong>{event.type === 'trainee_observation_check' && <span className="badge neutral">Observation check</span>}</div><div className="radio-bubble"><TypedText event={event} animate={animateNewMessages}/></div></article>)}
  </div><div className="radio-footer"><span className="status-dot"/>Simulated human controller & pilot · Advisory text stays off the radio</div></section>;
}

function AssistantReview({ session: s, onInspect }: { session: Session; onInspect?: () => void }) {
  const [inspecting, setInspecting] = useState(false);
  const instruction = [...s.events].reverse().find(e => e.type === 'trainee_instruction');
  const readback = [...s.events].reverse().find(e => e.type === 'pilot_readback');
  const feedback = s.events.filter(e => e.type === 'instructor_feedback');
  const latest = feedback.at(-1);
  const findings = latest?.payload.findings as { text: string }[] | undefined;
  const summary = findings?.[0]?.text || latest?.payload.text;
  const advisory = s.monitor?.advisory;
  const earlier = advisory?.isCurrent === false;
  const o = s.observation;
  const verification = s.events.find(e => e.type === 'trainee_observation_check');
  return <>
    <button className="assistant-advisory" onClick={() => { onInspect?.(); setInspecting(true); }}>
      <span className="advisory-icon" aria-hidden="true"><NavIcon kind="agent"/></span>
      <span><strong>{earlier ? 'Earlier advisory · new evidence available' : 'Assistant advisory'}</strong><span>{summary ? productText(summary) : s.status === 'completed' ? 'No advisory published. Inspect Activity for blocked checks or errors.' : 'Explanations appear after the evidence checks.'}</span></span>
      <span className="advisory-link">View evidence ↗</span>
    </button>
    <InspectorDialog open={inspecting} onClose={() => setInspecting(false)} title="ATC assistant · evidence review">
      <p className="dialog-intro">Advisory assistance only. The human controller remains responsible for instructions. Readback alignment and aircraft observations are checked separately.</p>
      <div className="review-feedback"><h3>Published advisory</h3>{earlier && <p className="muted">An earlier explanation is retained below. The current exchange has newer evidence; use the monitor above for its latest status.</p>}{feedback.length ? feedback.map(e => <PublishedFeedback key={e.eventId} event={e}/>) : <p className="muted">{s.status === 'completed' ? 'No advisory was published. Check Activity for errors or blocked checks.' : 'The assistant has not published an advisory yet.'}</p>}</div>
      <Evidence label="CONTROLLER INSTRUCTION" status={instruction ? 'RECORDED' : 'WAITING'} detail={instruction?.payload.text || 'No instruction yet'} reference={instruction ? `Human ATC (simulated) · ${time(instruction.simulationTimeMs)}` : 'Waiting for the automatic script.'}/>
      <Evidence label="PILOT READBACK" status={readback ? 'RECORDED' : 'WAITING'} detail={readback?.payload.text || 'No pilot readback yet'} reference="The monitor above shows the server’s current comparison result."/>
      <Evidence label="AIRCRAFT OBSERVATION" status={o.status === 'stale' ? 'UNVERIFIED' : 'CURRENT'} detail={o.status === 'stale' ? 'No current position observation.' : `${o.distanceBeforeHoldM.toFixed(0)} m before hold · ${o.speedMps.toFixed(1)} m/s`} reference={`Observed ${time(o.observedAtMs)} · ${verification ? 'Controller check recorded' : 'No controller verification check recorded'}`} warning={o.status === 'stale' || o.runwayEntered}/>
      {!!s.monitor?.issues.length && <section className="issue-history" aria-label="Retained issue history"><h3>Issue history</h3>{s.monitor.issues.map(issue => <Evidence key={issue.id} label={productText(issue.title)} status={issue.status === 'communication_resolved' ? 'Readback corrected' : issue.status === 'historical' ? 'Earlier finding' : 'Open'} detail={productText(issue.detail)} reference={`Detected ${time(issue.detectedAtMs)} · ${issue.evidenceEventIds.length} evidence references${issue.resolvedByEventId ? ' · Correcting readback recorded' : ''}`} warning={issue.status === 'open'}/>)}</section>}
      <div className="roles"><h3>Who does what</h3><dl><dt>Human roles</dt><dd>Scripted controller and pilot communications</dd><dt>Simulator</dt><dd>Aircraft motion and available observations</dd><dt>Decider 2B</dt><dd>Choice, Yes/No and Score decisions</dd><dt>Bedrock</dt><dd>Assistant reasoning and advisory explanations</dd></dl></div>
    </InspectorDialog>
  </>;
}

function PublishedFeedback({ event }: { event: Event }) {
  const findings = event.payload.findings as { text: string }[] | null | undefined;
  const nextAction = event.payload.nextAction as string | undefined;
  if (!findings?.length || !nextAction) return <p>{productText(event.payload.text || '')}</p>;
  return <div className="published-feedback"><span className="feedback-label">Checked findings</span>{findings.map((finding, i) => <p key={i}>{productText(finding.text)}</p>)}<div className="next-action"><span className="feedback-label">Suggested next check</span><p>{productText(nextAction)}</p></div></div>;
}

function Evidence({ label, status, detail, reference, warning = false }: { label: string; status: string; detail: string; reference: string; warning?: boolean }) {
  return <div className={`evidence ${warning ? 'warning' : ''}`}><div><span className="eyebrow">{label}</span><span className={`badge ${warning ? 'amber' : 'neutral'}`}>{status}</span></div><p>{detail}</p><small>{reference}</small></div>;
}

export function Activity({ session: s, selectedId, onSelect, recorded = false, paused = false, onInspect }: { session: Session; selectedId: string | null; onSelect: (id: string) => void; recorded?: boolean; paused?: boolean; onInspect?: () => void }) {
  const [inspecting, setInspecting] = useState(false);
  const selected = s.traces.find(t => t.id === selectedId);
  const assessment = selected?.actor === 'decider' ? s.assessments.find(a => a.assessmentId === selected.inputs.assessmentId) : undefined;
  const timelineRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!inspecting && timelineRef.current) timelineRef.current.scrollTop = timelineRef.current.scrollHeight; }, [s.traces.length, inspecting]);
  return <section className="panel activity"><div className="panel-heading"><h2>Agent activity <span className="count">{s.traces.length}</span></h2><span className="activity-label"><span className={`status-dot ${s.status === 'running' && !paused ? 'pulsing' : ''}`}/>{recorded ? s.status === 'completed' ? 'Recording complete' : paused ? 'Recording paused' : 'Recorded activity' : s.status === 'completed' ? 'Run finished' : s.status === 'paused' ? 'Paused' : 'Following agent'}</span></div>
    <div className="capabilities" aria-label="Decider 2B capabilities"><strong className="capability-model">Decider 2B</strong>{[['choice', 'Choice', 'Select one option'], ['noul', 'Yes/No', 'Probability of Yes'], ['score', 'Score', 'Rate ordered levels']].map(([type, name, description]) => { const count = s.assessments.filter(a => Object.values(a.decisionInput.questions)[0].type === type).length; return <span key={type} className={count ? 'used' : ''} title={`${description} · ${count} ${s.providerMode === 'fixture' ? 'fixture operations' : 'requests'}`}><strong>{name}</strong><span>{count}</span></span>; })}</div>
    <div className="trace-list scroll-region" ref={timelineRef} tabIndex={0} aria-label="Agent activity timeline">{!s.traces.length && <p className="waiting muted">Agent actions and decisions will appear here.</p>}{s.traces.map(trace => <button key={trace.id} className={`trace-row ${trace.id === selected?.id ? 'active' : ''} ${trace.status}`} onClick={() => { onInspect?.(); onSelect(trace.id); setInspecting(true); }} aria-label={`${trace.actor}: ${productText(trace.title)}. ${traceResult(trace)}. Inspect details`}>
      <span className={`trace-marker marker-${trace.actor}`} aria-hidden="true"><NavIcon kind={trace.actor === 'decider' ? 'decision' : trace.actor === 'tool' ? 'tool' : 'agent'}/></span><span className="trace-copy"><span className="trace-title">{productText(trace.title)}</span><span className="trace-detail"><span className={`actor actor-${trace.actor}`}>{actorLabel(trace.actor)}</span><span>·</span>{traceResult(trace)}</span></span><span className="trace-time"><time>{time(trace.simulationTimeMs)}</time><small>{trace.status === 'running' ? 'Running…' : trace.status === 'error' ? 'Failed' : duration(trace.roundTripMs)}</small></span>
    </button>)}</div>
    <AssistantReview session={s} onInspect={onInspect}/>
    <InspectorDialog open={inspecting} onClose={() => setInspecting(false)} title={assessment ? 'Decider decision' : 'Agent action'}>
      {assessment ? <DecisionInspector assessment={assessment}/> : selected ? <div className="decision-inspector"><span className="eyebrow">{selected.actor.toUpperCase()} · {selected.status.toUpperCase()}</span><h3>{productText(selected.title)}</h3><p className="muted small">Scenario {time(selected.simulationTimeMs)} · {duration(selected.roundTripMs)}</p><h4>Recorded input and output</h4><pre>{JSON.stringify({ inputs: selected.inputs, output: selected.output }, null, 2)}</pre></div> : <p className="muted">Select an activity to inspect its evidence and result.</p>}
    </InspectorDialog>
  </section>;
}
export function RuntimeMetrics({ session: s, recorded = false, onInspect }: { session: Session; recorded?: boolean; onInspect?: () => void }) {
  const [open, setOpen] = useState(false);
  const latest = (actor: string) => [...s.traces].reverse().find(t => t.actor === actor && t.roundTripMs != null)?.roundTripMs;
  const errors = s.traces.filter(t => t.status === 'error').length;
  return <>
    <section className="metrics header-metrics" aria-label={recorded ? 'Recorded runtime metrics' : s.providerMode === 'fixture' ? 'Fixture runtime metrics' : 'Measured runtime metrics'}><div className="metrics-heading"><span>{recorded ? 'Recorded metrics' : 'Runtime metrics'}</span><span className="metrics-mode">{recorded ? s.bedrockUsageIncomplete ? 'Original run · tokens partial' : 'Original run' : s.providerMode === 'fixture' ? 'Fixture timings' : s.bedrockUsageIncomplete ? 'Measured · token usage partial' : 'Measured'}</span><button className="text-button metrics-more" onClick={() => { onInspect?.(); setOpen(true); }} aria-label="More runtime metrics">More <span aria-hidden="true">↗</span></button></div><div className="metrics-grid">
      <Metric label={s.providerMode === 'fixture' ? 'Fixture checks' : 'Decider calls'} value={String(s.assessments.length)} note={`${s.assessments.filter(a => a.processingStatus === 'completed').length} completed`}/>
      <Metric label={s.providerMode === 'fixture' ? 'Decision RTT' : 'Decider RTT'} value={duration(latest('decider'))} note="Latest request to response"/>
      <Metric label={s.providerMode === 'fixture' ? 'Text RTT' : 'Bedrock RTT'} value={duration(latest('bedrock'))} note="Latest request to response"/>
      <Metric label="Errors" value={String(errors)} note="Runtime failures are retained"/>
    </div></section>
    <InspectorDialog open={open} onClose={() => setOpen(false)} title={recorded ? 'Recorded runtime metrics' : 'Runtime metrics'}>
      <><p className="dialog-intro">{recorded ? 'These measurements come from the original live run. Playing this recording makes no model requests. Activity durations can include queueing and orchestration; they are not isolated model inference times.' : s.providerMode === 'fixture' ? 'These timings measure deterministic development fixtures. No model inference was performed.' : 'Metrics recorded during this run.'}</p><div className="detail-metrics">
        <Metric label={s.providerMode === 'fixture' ? 'Fixture checks' : 'Decider requests'} value={String(s.assessments.length)} note={`${s.assessments.filter(a => a.processingStatus === 'completed').length} completed`}/>
        <Metric label={s.providerMode === 'fixture' ? 'Generative / tool steps' : 'Bedrock / tool calls'} value={`${s.traces.filter(t => t.actor === 'bedrock').length} / ${s.traces.filter(t => t.actor === 'tool').length}`} note="This run"/>
        <Metric label="Decision RTT" value={duration(latest('decider'))} note="Latest request to response"/><Metric label="Text RTT" value={duration(latest('bedrock'))} note="Latest request to response"/>
        <Metric label="Runtime errors" value={String(errors)} note="Failures are retained"/>
        <Metric label={s.bedrockUsageIncomplete ? 'Bedrock tokens (partial)' : 'Bedrock tokens'} value={s.bedrockUsage ? `${s.bedrockUsage.inputTokens ?? '—'} / ${s.bedrockUsage.outputTokens ?? '—'}` : '—'} note={s.providerMode === 'fixture' ? 'Not measured in fixture mode' : s.bedrockUsageIncomplete ? 'Recorded input / output only. Interrupted or failed calls may have additional unreported usage.' : 'Recorded input / output across completed calls'}/>
      </div><p className="cost-note">Estimated cost: —<br/>Pricing comparison has not been configured.</p></>
    </InspectorDialog>
  </>;
}
function InspectorDialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { if (open && !ref.current?.open) ref.current?.showModal(); else if (!open && ref.current?.open) ref.current.close(); }, [open]);
  return <dialog ref={ref} className="inspector-dialog" onClose={onClose} aria-labelledby={titleId}><div className="dialog-heading"><h2 id={titleId}>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Close inspector">×</button></div><div className="dialog-body scroll-region">{children}</div></dialog>;
}
export function NavIcon({ kind }: { kind: 'monitor' | 'exercises' | 'history' | 'decision' | 'tool' | 'agent' }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{kind === 'monitor' ? <><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4m-7-11v10l5 3"/></> : kind === 'exercises' ? <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></> : kind === 'history' ? <><path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/><path d="M12 7v5l3 2"/></> : kind === 'decision' ? <><path d="M12 3 21 12 12 21 3 12Z"/><path d="m8 12 3 3 5-6"/></> : kind === 'tool' ? <><path d="m14 5 5 5M4 20l9-9M16 3l5 5-4 4-5-5Z"/></> : <><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12v2m8-2v2m-7 3h6"/></>}</svg>;
}

function traceResult(t: Trace) {
  if (t.status === 'running') return 'Waiting for response…';
  if (t.status === 'error') return 'Execution failed · inspect details';
  if (t.output?.published === false) return `Blocked: ${pretty(String(t.output.reason || 'review needed'))}`;
  if (t.output?.published === true) return 'Advisory published';
  const answer = t.output?.answer as Answer | undefined;
  if (answer?.type === 'choice') return pretty(answer.choice || '');
  if (answer?.type === 'noul') return `P(Yes) = ${answer.noul?.toFixed(3)}`;
  if (answer?.type === 'score') return `Ordered score: ${answer.score?.toFixed(2)}`;
  if (t.output?.candidate_feedback) return 'Advisory draft prepared';
  if (Array.isArray(t.output?.tools)) return t.output.tools.length ? `Requested: ${t.output.tools.map(name => pretty(String(name))).join(', ')}` : 'No tool selected';
  return 'Recorded result available';
}
function DecisionInspector({ assessment: a }: { assessment: Assessment }) {
  const q = Object.values(a.decisionInput.questions)[0];
  const output = a.decisionOutput;
  return <div className="decision-inspector"><div className="inspector-heading"><span className="eyebrow">SELECTED DECISION · {q.type === 'noul' ? 'YES/NO' : q.type.toUpperCase()}</span><span className="badge neutral">{a.processingStatus}</span></div><h3>{a.assessmentType === 'grounding' ? 'Is this finding supported by its cited evidence?' : a.assessmentType === 'alignment' ? 'Does the readback match the instruction?' : a.assessmentType === 'correction' ? 'Does the controller explicitly correct the issue?' : 'Does the next check say what to inspect and record?'}</h3>
    {output?.type === 'choice' && <div className="decision-options">{Object.keys(q.criteria).map(option => <span className={option === output.choice ? 'chosen' : ''} key={option}>{pretty(option)}{option === output.choice && ' · selected'}</span>)}</div>}
    {output?.type === 'noul' && <p className="decision-value">Probability of Yes: {((output.noul || 0) * 100).toFixed(1)}%</p>}
    {output?.type === 'score' && <p className="decision-value">{output.score?.toFixed(2)} / {Array.isArray(q.criteria) ? q.criteria.length - 1 : '—'} <span className="muted small">next-check coverage</span></p>}
    {output?.confidence != null && <p className="small muted">{output.fixture ? 'Fixture value' : 'Model confidence'}: {output.confidence.toFixed(3)} · Confidence is not an accuracy measurement.</p>}
    {a.error && <p className="error-text">{a.error}</p>}
    <p className="small muted">{a.evidenceRefs.eventIds.length} event references{a.evidenceRefs.snapshotVersion != null ? ` · Snapshot ${a.evidenceRefs.snapshotVersion}` : ''} · {duration(a.roundTripMs)}</p>
    <details><summary>Inspect question, evidence and raw result</summary><pre>{JSON.stringify({ question: q, input: a.decisionInput.state, result: output, evidenceRefs: a.evidenceRefs, model: a.modelVersion }, null, 2)}</pre></details>
  </div>;
}
function Metric({ label, value, note }: { label: string; value: string; note: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>; }
