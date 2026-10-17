import { AppSymbol } from './Monitor';
import hero from './assets/atc-pilot-hero.png';
import './landing.css';

export default function LandingPage() {
  return <div className="landing-page">
    <header className="landing-header">
      <a className="landing-brand" href="/" aria-label="Air Traffic Controller Assistant home"><AppSymbol/><span>Air Traffic Controller<br/>Assistant</span></a>
      <span className="landing-event">Strands Decider 2B hackathon <span>Experimental prototype</span></span>
    </header>
    <main className="landing-main">
      <section className="landing-intro" aria-labelledby="landing-title">
        <span className="eyebrow">HUMAN COMMUNICATION. EVIDENCE-CHECKED ASSISTANCE.</span>
        <h1 id="landing-title">When a correct readback isn’t enough.</h1>
        <p>Spot gaps between a controller’s instruction, a pilot’s reply and the aircraft’s observed response.<br className="landing-wide-break"/> The assistant flags issues and missing evidence, keeping the human controller in charge.</p>
      </section>

      <section className="landing-exchange" aria-label="Illustrative controller, assistant and pilot exchange">
        <img src={hero} width="2172" height="724" alt="Illustrative people: a headset-wearing air traffic controller in an airport tower and a captain beside a cockpit window with blue sky and clouds." fetchPriority="high"/>
        <div className="landing-person landing-controller"><h2>Human ATC</h2><p>“Hold short of runway 36.”</p></div>
        <div className="landing-assistant">
          <AppSymbol/>
          <h2>ATC Assistant</h2>
          <span className="landing-example">ILLUSTRATIVE EXCHANGE</span>
          <p className="landing-alert"><span aria-hidden="true">!</span> Possible readback mismatch</p>
          <p className="landing-model-role"><strong>Strands Decider 2B</strong> checks the reply and evidence.</p>
          <p className="landing-model-role"><strong>Amazon Bedrock</strong> drafts the advisory.</p>
          <span className="landing-capabilities">Choice · Yes/No · Score</span>
        </div>
        <div className="landing-person landing-pilot"><h2>Human Pilot</h2><p>“Lining up runway 36.”</p></div>
      </section>

      <section className="landing-choices" aria-label="Choose how to explore the project">
        <a className="landing-demo-card landing-recorded" href="/recorded">
          <div className="landing-card-top"><span className="landing-card-label">START HERE · NO SIGN-IN</span><span className="landing-card-icon" aria-hidden="true">▶</span></div>
          <h2>Recorded Demo</h2>
          <p>Choose one of nine recordings and press Play. Watch the exchange, alerts and original model decisions. Pause to inspect the evidence.</p>
          <div className="landing-card-bottom"><span>Real recorded results · No new inference</span><strong>Explore recordings <span aria-hidden="true">→</span></strong></div>
        </a>
        <a className="landing-demo-card landing-live" href="/live">
          <div className="landing-card-top"><span className="landing-card-label">INVITED JUDGES & TESTERS</span><span className="landing-card-icon" aria-hidden="true">↗</span></div>
          <h2>Live Demo</h2>
          <p>Sign in with your invited account, choose a scenario and start. Follow new Decider and Bedrock decisions as the conversation plays automatically.</p>
          <div className="landing-card-bottom"><span>Live model calls · Decider 2B + Amazon Bedrock</span><strong>Open live demo <span aria-hidden="true">→</span></strong></div>
        </a>
      </section>
    </main>
    <footer className="landing-footer"><span>Fictional scripted communications · AI-generated illustrative people · Advisory prototype</span><span>Reusable pattern: evidence-checked advisory guard</span></footer>
  </div>;
}
