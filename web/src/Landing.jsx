import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, ArrowDown, ArrowRight, GitBranch, Command, ShieldCheck, Code2, Box, Radio, Check, Play, Pause, X, Menu, ChevronRight, Network, RotateCcw, Terminal, Braces, Cpu } from 'lucide-react';
import InfinityScene from './InfinityScene.jsx';
import Starfield from './Starfield.jsx';

const chapters = ['Origin', 'Discover', 'The jump', 'Connect', 'Evolve', 'Your universe'];
const chapterIds = ['origin', 'discover', 'threshold', 'connect', 'evolve', 'universe'];

function Mark({ small = false }) { return <svg className={small ? 'brand-symbol small' : 'brand-symbol'} viewBox="0 0 64 32" fill="none" aria-hidden="true"><path d="M32 16C8-15 3 39 26 22L38 10C61-7 56 47 32 16Z" stroke="currentColor" strokeWidth="4" /></svg>; }

function NetworkPreview({ onOpenApp, compact = false }) {
  const [selected, setSelected] = useState('gateway');
  const [tracing, setTracing] = useState(false);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  const run = () => { setTracing(true); clearTimeout(timer.current); timer.current = setTimeout(() => setTracing(false), 4000); };
  const items = {
    parent: { name: 'Modern platform', detail: 'Company A · Agent orchestration', icon: Cpu },
    gateway: { name: 'REPLIC8 gateway', detail: 'One interface. Every system.', icon: Command },
    maintenance: { name: 'Field operations', detail: 'Company B · maintenance.get_request', icon: Box },
    inventory: { name: 'Parts & logistics', detail: 'Company C · inventory.check_stock', icon: Braces },
  };
  return <div className={`network-preview ${compact ? 'compact' : ''}`}>
    <div className="network-topline"><span><span className="status-pulse" />{compact ? 'THE NETWORK, REIMAGINED' : 'A CONNECTED UNIVERSE'}</span><span className="demo-label">DEMO</span></div>
    <div className={`network-map ${tracing ? 'is-tracing' : ''}`}>
      <svg className="network-lines" viewBox="0 0 700 330" preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id={compact ? 'line-mini' : 'line-big'}><stop stopColor="#444951"/><stop offset=".5" stopColor="#e1e4eb"/><stop offset="1" stopColor="#444951"/></linearGradient></defs>
        <path d="M350 58V134 M350 175C350 215 140 185 140 253 M350 175C350 215 560 185 560 253 M210 281C280 310 420 310 490 281" />
        <path className="flow-dash" d="M350 58V134 M350 175C350 215 140 185 140 253 M350 175C350 215 560 185 560 253 M210 281C280 310 420 310 490 281" />
      </svg>
      {Object.entries(items).map(([key, item]) => { const Icon = item.icon; return <button key={key} className={`map-node node-${key} ${selected === key ? 'selected' : ''}`} onClick={() => setSelected(key)} aria-label={`Inspect ${item.name}`} aria-pressed={selected === key}><span className="map-icon">{key === 'gateway' ? <Mark small /> : <Icon size={15} />}</span><span>{item.name}</span><i /></button>; })}
      {!compact && <><span className="edge-label edge-label-left">REST + MCP</span><span className="edge-label edge-label-right">REST + MCP</span><span className="edge-label edge-label-bottom">SHARED PART SCHEMA</span></>}
    </div>
    <div className="network-bottom"><span>{tracing ? 'Tracing a simulated request…' : items[selected].detail}</span>{compact ? <button onClick={onOpenApp} aria-label="Open the full graph"><ArrowUpRight size={17}/></button> : <button onClick={run} disabled={tracing}><Play size={11} fill="currentColor"/>{tracing ? 'Tracing' : 'Trace a request'}</button>}</div>
  </div>;
}

export default function Landing({ onOpenApp }) {
  const [progress, setProgress] = useState(0);
  const [chapter, setChapter] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [motionPaused, setMotionPaused] = useState(false);
  const [prefersReduced, setPrefersReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [assetOpen, setAssetOpen] = useState(false);
  const container = useRef(null);
  const portal = useRef(null);
  useEffect(() => {
    if (!assetOpen) return;
    const previous = document.activeElement;
    const dialog = document.querySelector('.design-notes');
    const controls = () => [...dialog.querySelectorAll('button, a[href]')];
    controls()[0]?.focus();
    const keyboard = (event) => {
      if (event.key === 'Escape') setAssetOpen(false);
      if (event.key !== 'Tab') return;
      const list = controls();
      if (event.shiftKey && document.activeElement === list[0]) { event.preventDefault(); list.at(-1)?.focus(); }
      else if (!event.shiftKey && document.activeElement === list.at(-1)) { event.preventDefault(); list[0]?.focus(); }
    };
    document.addEventListener('keydown', keyboard);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', keyboard);document.body.style.overflow = overflow;previous?.focus(); };
  }, [assetOpen]);
  const reducedMotion = motionPaused || prefersReduced;
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setPrefersReduced(query.matches);
    query.addEventListener('change', change);
    let frame;
    const scroll = () => { if(frame) return; frame = requestAnimationFrame(() => {
      const h = container.current?.scrollHeight || 1;
      setProgress(Math.min(1, Math.max(0, window.scrollY / (h - window.innerHeight))));
      const sections = chapterIds.map((id) => document.getElementById(id));
      let active = 0;
      sections.forEach((el, i) => { if (el && el.getBoundingClientRect().top < window.innerHeight * .5) active = i; });
      setChapter(active);
      if (portal.current) {
        const stage = portal.current;
        const top = stage.getBoundingClientRect().top + window.scrollY;
        const viewport = window.innerHeight;
        const jump = Math.min(1, Math.max(0, (window.scrollY - top + viewport * .35) / Math.max(1, stage.offsetHeight - viewport * .25)));
        stage.style.setProperty('--portal-progress', jump);
        stage.style.setProperty('--portal-copy-opacity', Math.max(0, Math.min(1, (.5 - jump) / .22)));
        stage.style.setProperty('--portal-hint-opacity', Math.max(0, Math.min(1, (.62 - jump) / .2)));
        stage.style.setProperty('--portal-reticle-opacity', Math.max(0, Math.min(.55, (jump - .12) * 4, (.7 - jump) * 3)));
        stage.style.setProperty('--portal-arrival-opacity', Math.max(0, Math.min(1, (jump - .91) / .09)));
      }
      frame = null;
    }); };
    const observer = new IntersectionObserver((entries) => entries.forEach(e => { if(e.isIntersecting) e.target.classList.add('revealed'); }), { threshold: .15 });
    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
    window.addEventListener('scroll', scroll, { passive: true });scroll();
    return () => { window.removeEventListener('scroll', scroll);cancelAnimationFrame(frame);observer.disconnect();query.removeEventListener('change', change); };
  }, []);
  const goTo = (index) => { document.getElementById(chapterIds[index])?.scrollIntoView({ behavior: reducedMotion ? 'instant' : 'smooth' });setMenuOpen(false); };
  return <div className={`landing ${reducedMotion ? 'motion-reduced' : ''} ${chapter === 2 ? 'in-jump' : ''}`} ref={container}>
    <a className="skip-link" href="#discover">Skip the introduction</a>
    <Starfield reducedMotion={reducedMotion} />
    <div className="space-haze" aria-hidden="true" />
    <InfinityScene progress={progress} reducedMotion={reducedMotion} />
    <div className="orbital-grid" aria-hidden="true"><span/><span/><span/><span/></div>
    <header className="site-header">
      <button className="wordmark" onClick={() => goTo(0)} aria-label="REPLIC8 home"><Mark /><span>REPLIC8</span></button>
      <nav className={menuOpen ? 'main-nav open' : 'main-nav'} aria-label="Main navigation"><button onClick={() => goTo(1)}>The story</button><button onClick={() => goTo(3)}>The network</button><button onClick={() => goTo(5)}>The platform</button></nav>
      <div className="header-actions"><button className="app-link" onClick={onOpenApp}>Launch app<ArrowUpRight size={15}/></button><button className="mobile-menu icon-button" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen}>{menuOpen ? <X/> : <Menu/>}</button></div>
    </header>
    <aside className="chapter-nav" aria-label="Story chapters">{chapters.map((label, index) => <button className={chapter === index ? 'active' : ''} key={label} onClick={() => goTo(index)} aria-current={chapter === index ? 'step' : undefined}><span className="chapter-line"/><span className="chapter-number">0{index+1}</span><span className="chapter-name">{label}</span></button>)}</aside>
    <main>
      <section id="origin" className="hero story-section">
        <div className="hero-content">
          <p className="eyebrow hero-eyebrow"><span className="tiny-line"/> EVERY SYSTEM. INFINITE POSSIBILITY.</p>
          <h1 className="hero-title" aria-label="REPLIC8"><span>REPLIC</span><span className="hero-eight" style={{ opacity: Math.max(0, 1-progress*35) }}>8</span></h1>
          <div className="hero-bottom-copy"><p>Your legacy.<br/><span>A new dimension.</span></p><div className="hero-description"><p>Turn the software you have into<br/>the possibilities you haven’t imagined.</p><button className="text-link" onClick={() => goTo(1)}>Follow the connection<ArrowDown size={14}/></button></div></div>
        </div>
        <div className="hero-mini-network"><NetworkPreview compact onOpenApp={onOpenApp}/></div>
        <div className="hero-footnote"><span className="coordinate">LEGACY → API → MCP → POSSIBILITY</span><button onClick={() => goTo(1)} className="scroll-invitation"><span className="scroll-mouse"><i/></span>SCROLL TO EXPLORE</button><span className="hero-edition">BUILT FOR WHAT’S NEXT<span>001 — ∞</span></span></div>
      </section>
      <section id="discover" className="story-section discover-section">
        <div className="section-copy reveal">
          <p className="eyebrow"><span className="chapter-tag">01 / DISCOVER</span> THE ORIGIN OF SOMETHING MORE</p>
          <h2>Old code.<br/>New <span className="silver-text">possibilities.</span></h2>
          <p className="section-description">Years of business logic. Decades of knowledge. Your legacy software isn’t the end of the story. It’s where the next chapter begins.</p>
          <div className="story-detail"><Code2 size={18}/><div><strong>Start with the source.</strong><p>A GitHub repository becomes the starting point for an agent-ready interface.</p></div></div>
          <button className="text-link" onClick={onOpenApp}>Explore the workspace<ArrowUpRight size={14}/></button>
        </div>
        <div className="source-fragment reveal"><div className="fragment-title"><GitBranch size={13}/><span>maintenance / legacy</span><span className="fragment-badge">SOURCE</span></div><pre><span className="code-muted">// Knowledge, waiting to connect.</span>{'\n'}<span className="code-white">get_request</span>(request_id){'\n'}{'  '}<span className="code-muted">return</span> maintenance.find({'\n'}{'    '}request_id{'\n'}{'  '})</pre><div className="source-line"><span className="status-pulse"/>YOUR BUSINESS LOGIC, PRESERVED</div></div>
        <span className="section-axis" aria-hidden="true">SOURCE / SIGNAL / SYSTEM</span>
      </section>
      <section id="threshold" className="portal-section" data-warp-stage ref={portal} aria-labelledby="portal-title">
        <div className="portal-stage">
          <div className="portal-copy">
            <p className="eyebrow"><span className="tiny-line"/> THE SPACE BETWEEN SYSTEMS</p>
            <h2 id="portal-title">A new dimension.<br/><span className="silver-text">Just a connection away.</span></h2>
          </div>
          <div className="portal-reticle" aria-hidden="true"><i/><i/><i/><i/></div>
          <div className="portal-caption"><span className="portal-travel-line"/><p>FOLLOW THE LOOP</p><span>Keep scrolling. There’s more on the other side.</span><ArrowDown size={15}/></div>
          <p className="portal-arrival" aria-hidden="true"><span className="status-pulse"/> A NEW CONNECTION. A NEW POSSIBILITY.</p>
        </div>
      </section>
      <section id="connect" className="story-section connect-section">
        <div className="section-heading reveal"><p className="eyebrow"><span className="chapter-tag">02 / CONNECT</span> DISTANCE IS JUST AN INTERFACE</p><h2>Separate systems.<br/><span className="silver-text">One universe.</span></h2><p className="section-description">Give your agents a way in. APIs and MCP tools connect inherited systems to a modern platform—and to each other.</p></div>
        <div className="connection-orbits reveal"><div className="orbit-system orbit-system-left"><div className="orbit-icon"><Box size={24}/></div><p>FIELD OPERATIONS</p><span>Legacy system / B</span><div className="orbit-tool"><Terminal size={12}/>maintenance.get_request</div></div><div className="orbit-system orbit-system-right"><div className="orbit-icon"><Braces size={24}/></div><p>PARTS & LOGISTICS</p><span>Legacy system / C</span><div className="orbit-tool"><Terminal size={12}/>inventory.check_stock</div></div><div className="orbit-connection-line left"/><div className="orbit-connection-line right"/><span className="orbit-center-label">THE REPLIC8 GATEWAY</span></div>
        <div className="connection-facts reveal"><div><span>01</span><p>Read the source</p></div><i/><div><span>02</span><p>Verify the contract</p></div><i/><div><span>03</span><p>Open the connection</p></div></div>
      </section>
      <section id="evolve" className="story-section evolve-section">
        <div className="section-copy reveal"><p className="eyebrow"><span className="chapter-tag">03 / EVOLVE</span> A CONNECTION THAT KEEPS UP</p><h2>Software changes.<br/><span className="silver-text">Keep moving.</span></h2><p className="section-description">An integration should move with your code. REPLIC8’s repair workflow is designed to detect a broken contract, diagnose the change, and verify the way forward.</p><div className="repair-steps"><div><span>01</span><p>Detect the change</p><Radio size={15}/></div><div><span>02</span><p>Regenerate the wrapper</p><RotateCcw size={15}/></div><div><span>03</span><p>Verify before publishing</p><ShieldCheck size={15}/></div></div><p className="muted-caption">No change is published without a passing contract test.</p></div>
        <div className="repair-fragment reveal"><div className="fragment-title"><GitBranch size={13}/><span>source changed</span><span className="fragment-badge">WORKFLOW</span></div><div className="diff-line removed"><span>−</span>get_request(id)</div><div className="diff-line added"><span>+</span>find_request(id)</div><div className="repair-resolution"><ShieldCheck size={15}/><span>Test the contract. Then reconnect.</span><ArrowRight size={14}/></div></div>
      </section>
      <section id="universe" className="universe-section">
        <div className="universe-intro reveal"><p className="eyebrow"><span className="chapter-tag">04 / YOUR UNIVERSE</span> THE BIG PICTURE. EVERY CONNECTION.</p><h2>See how it all<br/><span className="silver-text">comes together.</span></h2><p className="section-description">A workspace for your systems, their tools,<br/>and everything that connects them.</p></div>
        <div className="platform-preview reveal"><div className="preview-window-header"><div className="window-dots"><i/><i/><i/></div><span><Mark small/> REPLIC8 / WORKSPACE</span><button className="text-link" onClick={onOpenApp}>Enter workspace<ArrowUpRight size={13}/></button></div><div className="preview-platform-body"><div className="preview-side"><span className="preview-active"><Network size={15}/>Universe</span><span><Box size={15}/>Systems</span><span><Terminal size={15}/>Operations</span><span><Radio size={15}/>Activity</span><div className="preview-side-bottom">READ-ONLY BY DEFAULT<ShieldCheck size={14}/></div></div><div className="preview-main"><div className="preview-main-heading"><div><span className="eyebrow">WORKSPACE OVERVIEW</span><h3>Your integration universe.</h3></div><span className="demo-pill">Illustrative demo</span></div><div className="preview-metrics"><div><span>CONNECTED SYSTEMS</span><strong>03 <small>/ one gateway</small></strong></div><div><span>EXPOSED OPERATIONS</span><strong>04 <small>/ read only</small></strong></div><div><span>INFINITE POSSIBILITIES</span><strong className="infinity-metric">∞</strong></div></div><NetworkPreview onOpenApp={onOpenApp}/></div></div></div>
        <div className="universe-cta reveal"><div><h3>Your software has more to give.</h3><p>Let’s see where it can go.</p></div><button className="button-primary" onClick={onOpenApp}>Launch the workspace<ArrowUpRight size={16}/></button></div>
      </section>
    </main>
    <footer className="site-footer"><button className="wordmark" onClick={() => goTo(0)}><Mark/><span>REPLIC8</span></button><span>YOUR LEGACY. A NEW DIMENSION.</span><button onClick={() => setAssetOpen(true)}>Design notes<ArrowUpRight size={12}/></button><span>© {new Date().getFullYear()} REPLIC8</span></footer>
    <div className="journey-hud"><div className="journey-counter"><span>0{chapter+1} <i>/ {String(chapters.length).padStart(2, '0')}</i></span><span>{chapters[chapter].toUpperCase()}</span></div><div className="journey-progress"><i style={{width:`${progress*100}%`}}/></div></div>
    <button className="motion-control icon-button" onClick={() => setMotionPaused(!motionPaused)} aria-label={motionPaused ? 'Resume ambient motion' : 'Pause ambient motion'} title={motionPaused ? 'Resume ambient motion' : 'Pause ambient motion'}>{reducedMotion ? <Play size={13}/> : <Pause size={13}/>}<span>MOTION {reducedMotion ? 'OFF' : 'ON'}</span></button>
    {assetOpen && <div className="modal-scrim" onClick={() => setAssetOpen(false)}><section className="design-notes" role="dialog" aria-modal="true" aria-labelledby="design-title" onClick={e=>e.stopPropagation()}><button className="icon-button close-modal" onClick={()=>setAssetOpen(false)} aria-label="Close design notes"><X size={18}/></button><p className="eyebrow">DESIGN PREVIEW / 001</p><h2 id="design-title">A silver thread<br/>through your universe.</h2><p>The 8 leaves the wordmark, becomes an infinity loop, and follows the story into a connected workspace. The silver sculpture and deep-space texture were generated with Higgsfield. Scroll-driven motion and a separate layer of drifting stars bring them to life.</p><div className="asset-review-grid"><a href="/assets/silver-eight.png" target="_blank" rel="noreferrer"><img src="/assets/silver-eight.png" alt="Higgsfield-generated polished silver figure eight sculpture"/><span>Chrome 8 / infinity<ArrowUpRight size={12}/></span></a><a href="/assets/starfield.jpg" target="_blank" rel="noreferrer"><img src="/assets/starfield.jpg" alt="Higgsfield-generated monochrome starfield"/><span>Deep-space backdrop<ArrowUpRight size={12}/></span></a></div><p>The dashboard opens in a labeled demo mode. Existing gateway operations can be loaded through the configured development proxy; graph relationships in the preview are illustrative.</p><button className="button-primary" onClick={()=>setAssetOpen(false)}>Back to the story<ArrowRight size={15}/></button></section></div>}
  </div>;
}
