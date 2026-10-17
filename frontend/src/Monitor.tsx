import humanPortraits from './assets/atc-pilot-hero.png';
import type { RadioRef, ReadbackStatus, Session } from './types';
import { productText } from './presentation';

const clock = (ms: number) => `${Math.floor(ms / 60000).toString().padStart(2, '0')}:${Math.floor(ms / 1000 % 60).toString().padStart(2, '0')}`;
const elapsed = (ms: number) => ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;

export function ReadbackMonitor({ session, connected, recorded = false }: { session: Session; connected: boolean; recorded?: boolean }) {
  const communication = session.monitor?.communication;
  const status: ReadbackStatus = !connected ? 'unclear' : communication?.status || 'waiting';
  const title = !connected ? 'Connection interrupted' : communication?.title || 'Waiting for monitor';
  const detail = !connected ? 'Reconnecting. The latest readback result cannot be confirmed.' : communication?.detail || 'The server’s comparison will appear here when available.';
  const previousReadback = communication && !communication.readback ? [...session.events].reverse().find(event => event.type === 'pilot_readback') : undefined;
  const pilotMessage = communication?.readback || (previousReadback ? { eventId: previousReadback.eventId, text: previousReadback.payload.text || '', simulationTimeMs: previousReadback.simulationTimeMs } : null);
  const openIssues = session.monitor?.issues.filter(issue => issue.status === 'open').length || 0;
  return <section className="communication-monitor" aria-label="Controller, assistant and pilot communication monitor">
    <CommunicationCard role="controller" message={communication?.instruction || null}/>
    <section className={`panel assistant-card monitor-${status}`} aria-labelledby="assistant-title">
      <div className="assistant-heading"><AppSymbol/><div><h2 id="assistant-title">ATC Assistant</h2><p>{recorded ? 'Recorded exchange analysis' : 'Monitoring the exchange'}</p></div></div>
      <div className="monitor-result" role="status" aria-live="polite" aria-atomic="true">
        <div className="monitor-status"><StatusIcon status={status}/><strong>{title}</strong></div>
        <p className="monitor-detail">{productText(detail).split(/(?<=[.!?])\s+(?=[A-Z])/u).map((sentence, index) => <span className="monitor-sentence" key={index}>{sentence}</span>)}</p>
      </div>
      <div className="monitor-bottom">
        <span className="monitor-scope">Readback only · Aircraft state checked separately</span>
        {connected && communication?.roundTripMs != null ? <div className="monitor-timing"><span>Decider · Choice · <strong>{elapsed(communication.roundTripMs)}</strong></span>{communication.alertLatencyMs != null && <span title="Time from recorded readback to the completed decision">Result after <strong>{elapsed(communication.alertLatencyMs)}</strong></span>}</div> : <div className="monitor-timing">{status === 'checking' ? 'Decider comparison pending' : 'Awaiting a current comparison'}</div>}
        <span className="monitor-footnote">Advisory only{openIssues > 0 ? ` · ${openIssues} open ${openIssues === 1 ? 'finding' : 'findings'}` : ''}</span>
      </div>
    </section>
    <CommunicationCard role="pilot" aircraft={session.initialSetup?.aircraft || 'AIR123'} message={pilotMessage} previous={Boolean(previousReadback)}/>
  </section>;
}

function CommunicationCard({ role, message, previous = false, aircraft = 'AIR123' }: { role: 'controller' | 'pilot'; message: RadioRef | null; previous?: boolean; aircraft?: string }) {
  return <section className={`panel communication-card human-${role} ${previous ? 'previous-message' : ''}`} aria-label={role === 'controller' ? 'Latest human controller instruction' : 'Latest human pilot readback'}>
    <HeadsetPortrait role={role}/>
    <div className="communication-copy"><div><h2>{role === 'controller' ? 'Human ATC' : 'Human Pilot'}</h2><p className="human-role">{role === 'controller' ? 'Tower controller · simulated' : `${aircraft} · simulated`}</p></div>
      <span className={`message-label ${role}`}>{role === 'controller' ? 'Instruction' : previous ? 'Previous readback' : 'Readback'}</span>{previous && <span className="awaiting-reply">Awaiting a reply to the current instruction</span>}
      <p className={`latest-message ${!message ? 'empty' : ''}`}>{message ? <HighlightedMessage text={message.text}/> : role === 'controller' ? 'Waiting for the controller’s instruction…' : 'Waiting for the pilot’s readback…'}</p>
      <time className="message-time">{message ? clock(message.simulationTimeMs) : '—'}</time>
    </div>
  </section>;
}

// These highlights identify phrases for readability; they never classify alignment.
function HighlightedMessage({ text }: { text: string }) {
  return <>{text.split(/(hold short|hold position|lining up|line up|stop immediately)/gi).map((part, i) => /^(hold short|hold position|lining up|line up|stop immediately)$/i.test(part) ? <mark key={i}>{part}</mark> : part)}</>;
}

export function ReadbackLegend() {
  return <div className="readback-legend" aria-label="Readback status legend"><strong>Readback status</strong>{([
    ['matches', 'Matches'], ['mismatch', 'Possible mismatch'], ['unclear', 'Unclear'], ['checking', 'Checking'],
  ] as [ReadbackStatus, string][]).map(([status, label]) => <span className={`legend-item monitor-${status}`} key={status}><StatusIcon status={status}/>{label}</span>)}</div>;
}

export function StatusIcon({ status }: { status: ReadbackStatus }) {
  return <svg className="status-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    {status === 'matches' ? <><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="m7 12 3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></> : status === 'mismatch' ? <><path d="M10.3 3.6a2 2 0 0 1 3.4 0l8 14.3a2 2 0 0 1-1.7 3H4a2 2 0 0 1-1.7-3Z" fill="currentColor"/><path d="M12 8v5m0 3v.1" stroke="white" strokeWidth="2.3" strokeLinecap="round"/></> : status === 'unclear' ? <><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M9.3 9a2.8 2.8 0 1 1 4.5 2.2c-1 .7-1.8 1.1-1.8 2.3m0 3v.1" stroke="white" strokeWidth="2" strokeLinecap="round"/></> : <><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2"/><path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></>}
  </svg>;
}

export function AppSymbol({ className = 'assistant-symbol' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 44 44" aria-hidden="true" fill="none"><path d="M22 8v28M8 22h28" stroke="currentColor" strokeWidth="2.5"/><path d="m12 12 20 20m0-20L12 32" stroke="currentColor" strokeWidth="1" opacity=".4"/><circle cx="22" cy="22" r="6" fill="currentColor"/>{[[22,5],[22,39],[5,22],[39,22]].map(([x,y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="4.5" fill="currentColor"/>)}</svg>;
}

// Frame the same fictional people used on the landing page, without changing
// the source image or making a second request for a separate portrait asset.
function HeadsetPortrait({ role }: { role: 'controller' | 'pilot' }) {
  return <img className={`headset-portrait ${role}-portrait`} src={humanPortraits} width="150" height="180"
    alt={role === 'controller'
      ? 'Illustrative female air traffic controller wearing a headset in an airport control tower'
      : 'Illustrative captain wearing a headset and four gold shoulder stripes beside a cockpit window with blue sky and clouds'}/>;
}
