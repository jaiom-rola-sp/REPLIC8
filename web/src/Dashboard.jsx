import { useEffect, useMemo, useRef, useState } from 'react';
import { ReactFlow, Background, Controls, Handle, Position } from '@xyflow/react';
import { Activity, ArrowRight, ArrowUpRight, Box, Check, CheckCheck, ChevronDown, ChevronRight, Code2, Copy, Database, GitBranch, Globe2, Layers3, LayoutGrid, LockKeyhole, Menu, Network, Plus, Search, Settings2, ShieldCheck, Sparkles, Terminal, Workflow, X, Zap, AlertTriangle, Wrench, Plug } from 'lucide-react';
import '@xyflow/react/dist/style.css';
import './dashboard.css';
import BrandLogo, { BrandMark } from './BrandLogo.jsx';
import AddSystem from './AddSystem.jsx';
import SystemHealth from './SystemHealth.jsx';
import ConnectAgent from './ConnectAgent.jsx';
import TryIt from './TryIt.jsx';
import { describeEvent, needsRefresh } from './liveEvents.js';
import { graphData } from './graphLayout.js';
import WorkspaceAccess, { BlankWorkspace } from './WorkspaceAccess.jsx';
import { defaultGateway, describeWorkspace, normalizeGateway, workspaceLabel } from './workspace.js';

const TONE_ICON = { ok: CheckCheck, warn: AlertTriangle, work: Wrench, info: Activity };
const PAGE = 50; // rows or buttons shown at a time in long lists

const NAV = [
  { id: 'overview', label: 'Overview', icon: LayoutGrid },
  { id: 'systems', label: 'Systems', icon: Layers3 },
  { id: 'operations', label: 'Operations', icon: Terminal },
  { id: 'activity', label: 'Activity', icon: Activity },
  { id: 'connect', label: 'Connect', icon: Plug },
];

function sessionRead(key, fallback) {
  try { return sessionStorage.getItem(key) || fallback; } catch { return fallback; }
}

function Signal({ children = 'Connected', pulse = false }) {
  return <span className={`dash-signal${pulse ? ' dash-signal--pulse' : ''}`}><i />{children}</span>;
}

function SystemNode({ data, selected }) {
  const Icon = data.icon || Box;
  return <div className={`dash-system-node ${data.kind === 'gateway' ? 'dash-system-node--gateway' : ''} ${data.kind === 'operation' ? 'dash-system-node--operation' : ''} ${data.kind === 'group' || data.kind === 'more' ? 'dash-system-node--group' : ''} ${selected ? 'is-selected' : ''} ${data.active ? 'is-tracing' : ''}`}>
    <Handle type="target" position={Position.Top} isConnectable={false} />
    <div className="dash-node-top"><span className="dash-node-icon">{data.kind === 'gateway' ? <BrandMark size={34} /> : <Icon size={18} strokeWidth={1.5} />}</span><span className="dash-node-eyebrow">{data.eyebrow}</span><span className="dash-node-dot" /></div>
    <strong>{data.label}</strong><span className="dash-node-subtitle">{data.subtitle}</span>
    {data.footer && <div className="dash-node-footer"><span>{data.footer}</span><ArrowUpRight size={12} /></div>}
    <Handle type="source" position={Position.Bottom} isConnectable={false} />
  </div>;
}

const NODE_TYPES = { system: SystemNode };

function GraphPanel({ operations, isLive, traceStep, links, expanded, onToggle, onMore, onSelect, established = [], large = false }) {
  const graph = useMemo(() => graphData(operations, isLive, traceStep, links, expanded, established), [operations, isLive, traceStep, links, expanded, established]);
  const press = node => node.data.kind === 'group' ? onToggle(node.data.system) : node.data.kind === 'more' ? onMore(node.data.system) : onSelect(node);
  return <section className={`dash-graph-panel ${large ? 'dash-graph-panel--large' : ''}`}>
    <div className="dash-panel-header"><div><span className="dash-section-eyebrow">THE BIG PICTURE</span><h2>System constellation <span>{isLive ? 'Registry view' : 'Preview'}</span></h2></div><div className="dash-graph-legend"><i /> {isLive ? 'Registered tools' : 'Simulated connections'}</div></div>
    <div className="dash-graph-stage">
      <div className="dash-graph-orbit dash-graph-orbit--one" /><div className="dash-graph-orbit dash-graph-orbit--two" />
      <ReactFlow key={`${isLive ? 'live' : 'demo'}:${[...expanded].sort().join(',')}`} nodes={graph.nodes} edges={graph.edges} nodeTypes={NODE_TYPES} fitView fitViewOptions={{ padding: .15, maxZoom: .78 }} minZoom={.25} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false} elementsSelectable onNodeClick={(_, node) => press(node)} onNodeDoubleClick={(_, node) => { if (!['group', 'more'].includes(node.data.kind)) onSelect(node); }} preventScrolling={false} colorMode="dark" aria-label="Interactive graph of REPLIC8 system connections">
        <Background gap={27} size={.7} color="#3e3e3e" />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
      <div className="dash-graph-caption"><span><LockKeyhole size={11} /> READ-ONLY BY DEFAULT</span><span>Scroll to zoom · drag to explore</span></div>
    </div>
  </section>;
}

export default function Dashboard({ onBack }) {
  const [view, setView] = useState('overview');
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [modal, setModal] = useState(null);
  const [events, setEvents] = useState([]);
  const [traceStep, setTraceStep] = useState(-1);
  const [traceComplete, setTraceComplete] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [liveOperations, setLiveOperations] = useState([]);
  const [liveLinks, setLiveLinks] = useState([]);
  const [liveEstablished, setLiveEstablished] = useState([]); // modern systems listed from their API file, never called
  const [liveFeed, setLiveFeed] = useState([]);
  const [rawEvents, setRawEvents] = useState([]);
  const [healTick, setHealTick] = useState(0);
  const [expandedSystems, setExpandedSystems] = useState(() => new Set());
  const [opLimit, setOpLimit] = useState(PAGE);
  const [connectionError, setConnectionError] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [gateway, setGateway] = useState(() => sessionRead('replic8.gateway', defaultGateway(import.meta.env)));
  const [token, setToken] = useState(() => sessionRead('replic8.token', ''));
  const [copied, setCopied] = useState(false);
  const [adminToken, setAdminToken] = useState(''); // memory only, never stored
  const [wsInfo, setWsInfo] = useState(null); // which workspace the token opened (GET /v1/workspace)
  const traceTimers = useRef([]);
  const operations = isLive ? liveOperations : [];
  const feed = isLive ? liveFeed : events;
  const established = isLive ? liveEstablished : [];
  const page = isLive ? view : null; // nothing is shown until a workspace or gateway is open
  const ownerToken = wsInfo?.kind === 'workspace' ? token : adminToken; // a workspace token runs admin actions in its own workspace
  const gatewayBase = sessionRead('replic8.gateway', gateway.trim().replace(/\/$/, ''));
  const namespaces = useMemo(() => [...new Set(operations.map(o => o.tool.split('.')[0]))], [operations]);
  const filteredOperations = operations.filter(o => `${o.tool} ${o.description} ${o.tier}`.toLowerCase().includes(query.toLowerCase()));
  const filteredSystems = namespaces.filter(n => n.includes(query.toLowerCase()));

  useEffect(() => () => traceTimers.current.forEach(clearTimeout), []);
  // While connected, follow the gateway's real event log. Events that change what is published reload the lists.
  useEffect(() => {
    if (!isLive) { setLiveFeed([]); setRawEvents([]); return undefined; }
    let stop = false, timer, cursor = 0;
    const poll = async () => {
      try {
        const res = await fetch(`${sessionRead('replic8.gateway', gateway.trim().replace(/\/$/, ''))}/v1/events?after=${cursor}&limit=100`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(8000) });
        const batch = res.ok ? (await res.json()).events : null;
        if (!stop && Array.isArray(batch) && batch.length) {
          cursor = batch.reduce((max, e) => Math.max(max, e.id), cursor);
          setRawEvents(prev => [...prev, ...batch].slice(-300));
          const fresh = batch.map(describeEvent).filter(Boolean).map(d => ({ ...d, icon: TONE_ICON[d.tone] })).reverse();
          setLiveFeed(prev => [...fresh, ...prev].slice(0, 60));
          if (batch.some(needsRefresh)) { refreshOperations(); setHealTick(t => t + 1); }
        }
      } catch { /* the gateway may be busy; try again */ }
      if (!stop) timer = setTimeout(poll, 2000);
    };
    poll();
    return () => { stop = true; clearTimeout(timer); };
  }, [isLive, token]); // a new token (another workspace) restarts the feed
  useEffect(() => { setOpLimit(PAGE); }, [query, operations]);
  useEffect(() => {
    const close = e => { if (e.key === 'Escape') { setModal(null); setSelected(null); setMenuOpen(false); } };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, []);
  useEffect(() => {
    if (!modal && !selected) return;
    const previousFocus = document.activeElement;
    const dialog = document.querySelector('.dash-overlay [role="dialog"]');
    const getFocusable = () => [...(dialog?.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]') || [])];
    getFocusable()[0]?.focus();
    const trapFocus = event => {
      if (event.key !== 'Tab') return;
      const controls = getFocusable();
      const first = controls[0];
      const last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', trapFocus);
    return () => {
      document.removeEventListener('keydown', trapFocus);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [modal, selected]);

  function toggleSystem(name) {
    setExpandedSystems(prev => { const next = new Set(prev); next.has(name) ? next.delete(name) : next.add(name); return next; });
  }

  function showSystemOperations(name) { changeView('operations'); setQuery(`${name}.`); }

  function changeView(next) { setView(next); setQuery(''); setMenuOpen(false); setSelected(null); }

  function runDemo() {
    if (traceStep >= 0) return;
    if (isLive) { setIsLive(false); setLiveOperations([]); }
    traceTimers.current.forEach(clearTimeout);
    setTraceComplete(false);
    setTraceStep(0);
    setView('overview');
    const steps = [
      { title: 'Maintenance request retrieved', detail: 'maintenance.get_request → pump replacement · demo', icon: Database },
      { title: 'Inventory availability checked', detail: 'inventory.check_stock → 3 matching parts · demo', icon: Box },
      { title: 'Connected answer assembled', detail: 'Two example systems. One read-only workflow.', icon: CheckCheck },
    ];
    steps.forEach((event, index) => {
      traceTimers.current.push(setTimeout(() => {
        setTraceStep(index === 2 ? -1 : index + 1);
        setEvents(previous => [{ ...event, id: Date.now() + index, time: 'Just now · simulated' }, ...previous].slice(0, 12));
        if (index === 2) setTraceComplete(true);
      }, (index + 1) * 1500));
    });
  }

  function connectGateway(e) {
    e.preventDefault();
    try { connectWith(normalizeGateway(gateway), token); } catch (error) { setConnectionError(error.message); }
  }

  async function connectWith(base, token) {
    setConnectionError(''); setConnecting(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const [health, registry] = await Promise.all([fetch(`${base}/health`, { signal: AbortSignal.timeout(8000) }), fetch(`${base}/v1/operations`, { headers, signal: AbortSignal.timeout(8000) })]);
      if (!health.ok) throw new Error('Gateway health check failed. Check the address and try again.');
      if (!registry.ok) throw new Error(registry.status === 401 ? 'The gateway rejected this token. Check it and try again.' : `The operation registry returned ${registry.status}.`);
      const healthData = await health.json();
      const registryData = await registry.json();
      if (healthData.status !== 'ok' || !Array.isArray(registryData.operations) || !registryData.operations.every(op => typeof op.tool === 'string')) throw new Error('This address did not return a REPLIC8 operation registry.');
      sessionStorage.setItem('replic8.gateway', base); sessionStorage.setItem('replic8.token', token);
      setGateway(base); setToken(token); setWsInfo(await describeWorkspace(base, token)); setLiveFeed([]); setRawEvents([]);
      setLiveOperations(registryData.operations); loadLinks(base, token); setIsLive(true); setModal(null); setView('operations');
      setEvents([{ id: Date.now(), title: 'Gateway registry connected', detail: `${registryData.operations.length} operations loaded from your gateway`, time: 'Just now', icon: Network }]);
    } catch (error) { setConnectionError(error.name === 'TimeoutError' ? 'The gateway did not respond in time. Check that it is running.' : error.message === 'Failed to fetch' ? 'Could not reach the gateway. Check its address and browser access settings.' : error.message); }
    finally { setConnecting(false); }
  }

  // Leave: the dashboard goes blank. The work stays on the gateway under the workspace token.
  function leaveWorkspace() {
    setIsLive(false); setToken(''); setAdminToken(''); setWsInfo(null); setLiveOperations([]); setLiveLinks([]); setLiveEstablished([]);
    setEvents([]); setSelected(null); setModal(null); setView('overview');
    try { sessionStorage.removeItem('replic8.token'); } catch { /* storage may be blocked */ }
  }

  async function loadEstablished(base, bearer) {
    try {
      const res = await fetch(`${base}/v1/established`, { headers: { Authorization: `Bearer ${bearer}` }, signal: AbortSignal.timeout(8000) });
      const data = res.ok ? await res.json() : null;
      const ok = e => e && typeof e.system === 'string' && Array.isArray(e.operations) && e.operations.every(o => typeof o.tool === 'string');
      setLiveEstablished(data && Array.isArray(data.systems) ? data.systems.filter(ok) : []);
    } catch { setLiveEstablished([]); }
  }

  async function loadLinks(base, bearer) {
    loadEstablished(base, bearer);
    try {
      const res = await fetch(`${base}/v1/graph`, { headers: { Authorization: `Bearer ${bearer}` }, signal: AbortSignal.timeout(8000) });
      const data = res.ok ? await res.json() : null;
      const strings = list => Array.isArray(list) && list.every(v => typeof v === 'string');
      if (data && Array.isArray(data.system_links)) {
        setLiveLinks(data.system_links.filter(l => typeof l.source === 'string' && typeof l.target === 'string' && strings(l.fields)).map(({ source, target, fields, evidence }) => ({ source, target, fields, evidence })));
      } else {
        const pairs = new Map();
        for (const e of (data && Array.isArray(data.edges) ? data.edges : [])) {
          if (e.type !== 'data' || ![e.source, e.target, e.field].every(v => typeof v === 'string')) continue;
          const from = e.source.split('.')[0], to = e.target.split('.')[0], key = `${from}>${to}`;
          const link = pairs.get(key) || { source: from, target: to, fields: [], evidence: e.evidence };
          if (!link.fields.includes(e.field)) link.fields.push(e.field);
          pairs.set(key, link);
        }
        setLiveLinks([...pairs.values()]);
      }
    } catch { setLiveLinks([]); }
  }

  async function refreshOperations() {
    try {
      const base = sessionRead('replic8.gateway', gateway.trim().replace(/\/$/, ''));
      const res = await fetch(`${base}/v1/operations`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(8000) });
      const data = res.ok ? await res.json() : null;
      if (data && Array.isArray(data.operations)) setLiveOperations(data.operations);
      loadLinks(base, token);
    } catch { /* the next connect or import refreshes it */ }
  }

  async function copyOperation(operation) {
    try { await navigator.clipboard.writeText(operation.tool); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { setCopied(false); }
  }

  const headings = { overview: ['Your integration universe.', 'Every system. One connected view.'], systems: ['Connected systems.', 'The software you have. Ready for what comes next.'], operations: ['Tools, with a source.', 'Inspect every operation and the code behind it.'], activity: ['Every connection leaves a trace.', 'Follow the events that keep your systems in sync.'], connect: ['Bring your agent.', 'Give any MCP client a tested, read-only door into these systems.'] };
  const selectedEst = selected && established.find(e => e.system === selected.id);
  const selectedOp = selected && !selectedEst && operations.find(o => o.tool === selected.id);
  const selectedNamespace = selected?.id;
  const selectedOps = selectedOp ? [selectedOp] : operations.filter(o => o.tool.startsWith(`${selectedNamespace}.`));

  return <div className="dashboard">
    {menuOpen && <button className="dash-sidebar-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <aside className={`dash-sidebar ${menuOpen ? 'is-open' : ''}`}>
      <button className="dash-brand" onClick={onBack} aria-label="Back to REPLIC8 landing page"><BrandLogo /></button>
      <button className="dash-workspace" onClick={() => setModal('workspace')}><span className="dash-workspace-icon"><Workflow size={17} /></span><span>{workspaceLabel(wsInfo, isLive).title}<small>{workspaceLabel(wsInfo, isLive).subtitle}</small></span><ChevronDown size={13} /></button>
      <span className="dash-nav-label">WORKSPACE</span>
      <nav aria-label="Dashboard navigation">{NAV.map(item => <button key={item.id} className={`dash-nav-item ${view === item.id ? 'is-active' : ''}`} onClick={() => changeView(item.id)}><item.icon size={17} strokeWidth={1.6} /><span>{item.label}</span>{item.id === 'systems' && <small>{namespaces.length + established.length}</small>}{item.id === 'overview' && view === 'overview' && <span className="dash-nav-dot" />}</button>)}</nav>
      <div className="dash-sidebar-bottom"><div className="dash-sidebar-callout"><BrandMark size={31} /><p>Built for what’s next.<br /><span>Connected to what’s here.</span></p><button onClick={onBack}>Explore the story <ArrowUpRight size={13} /></button></div><button className="dash-nav-item" onClick={() => setModal('settings')}><Settings2 size={17} strokeWidth={1.6} /><span>Settings</span></button><div className="dash-user"><span className="dash-avatar">Y</span><span>Your workspace<small>Design preview</small></span><span className="dash-user-dot" /></div></div>
    </aside>

    <main className="dash-main">
      <header className="dash-topbar"><div className="dash-breadcrumb"><button className="dash-menu" onClick={() => setMenuOpen(v => !v)} aria-label="Open navigation"><Menu size={20} /></button><span>Workspace</span><ChevronRight size={12} /><strong>{NAV.find(n => n.id === view)?.label}</strong></div><div className="dash-topbar-right"><span className="dash-preview-pill"><i />{wsInfo?.kind === 'workspace' ? 'Workspace open' : isLive ? 'Gateway connected' : 'No workspace'}</span><button className="dash-icon-button" aria-label="Open gateway settings" onClick={() => setModal('settings')}><Settings2 size={16} /></button><span className="dash-avatar dash-avatar--small">Y</span></div></header>
      <div className="dash-content">
        <div className="dash-page-header"><div><span className="dash-section-eyebrow">{wsInfo?.kind === 'workspace' ? 'YOUR WORKSPACE' : isLive ? 'YOUR GATEWAY' : 'WELCOME TO REPLIC8'}</span><h1>{headings[view][0]}</h1><p>{headings[view][1]}</p></div><button className="dash-primary-button" onClick={() => setModal('add')}><Plus size={16} />Connect a system</button></div>
        <div className="dash-demo-notice"><Sparkles size={13} /><span>{isLive ? 'Registry data is connected. Solid lines show registration. A dashed line is a link the gateway saw in real data.' : 'Nothing is open. Start a new workspace, or open a saved one with its token.'}</span><button onClick={() => setModal('workspace')}>{wsInfo?.kind === 'workspace' ? 'Leave or switch workspace' : isLive ? 'Manage connection' : 'Open a workspace'}<ArrowRight size={12} /></button></div>
        {!isLive && <BlankWorkspace onStart={() => setModal('workspace-new')} onOpen={() => setModal('workspace')} />}

        {page === 'overview' && <>
          <div className="dash-stats"><Metric label="Connected systems" value={String(namespaces.length).padStart(2, '0')} detail={isLive ? 'Registered namespaces' : 'One unified gateway'} icon={Layers3} spark="M0 20 L10 20 L15 16 L24 16 L29 12 L41 12 L48 7 L62 7 L70 2" /><Metric label="Available operations" value={String(operations.length).padStart(2, '0')} detail="Source-linked & namespaced" icon={Terminal} spark="M0 22 L8 22 L16 18 L26 18 L30 14 L42 14 L48 8 L57 8 L65 2 L70 2" /><Metric label="Access policy" value="Read only" detail="Write operations stay disabled" icon={LockKeyhole} spark={null} /></div>
          <div className="dash-overview-grid"><GraphPanel operations={operations} isLive={isLive} traceStep={traceStep} links={isLive ? liveLinks : []} expanded={expandedSystems} onToggle={toggleSystem} onMore={showSystemOperations} onSelect={setSelected} established={established} /><div className="dash-right-column"><section className="dash-activity-panel"><div className="dash-panel-header"><h2>Recent activity</h2><Activity size={15} /></div><div className="dash-activity-list">{feed.slice(0, 4).map(event => <EventRow key={event.id} event={event} />)}</div><button className="dash-panel-link" onClick={() => changeView('activity')}>View all activity<ArrowRight size={13} /></button></section><section className="dash-walkthrough"><span className="dash-section-eyebrow">TAKE IT FOR A SPIN</span><h3>Two systems.<br />One answer.</h3><p>Follow a maintenance request from field services to inventory.</p><div className="dash-demo-route"><Database size={17} /><span /><BrandMark size={28} /><span /><Box size={17} /></div>{!isLive && <button className="dash-secondary-button" onClick={runDemo} disabled={traceStep >= 0}>{traceStep >= 0 ? <><span className="dash-loading-dot" />Tracing connections…</> : <>{traceComplete ? <Check size={14} /> : <Zap size={14} />}{traceComplete ? 'Run demo again' : 'Run demo'}<ArrowUpRight size={14} /></>}</button>}<small>Simulated · no operations executed</small></section></div></div>
          <section className="dash-operations-panel"><div className="dash-panel-header"><div><span className="dash-section-eyebrow">READY TO CALL</span><h2>Your operations</h2></div><button className="dash-quiet-button" onClick={() => changeView('operations')}>View all operations<ArrowRight size={13} /></button></div><OperationTable operations={operations.slice(0, 3)} onSelect={op => setSelected({ id: op.tool, data: { label: op.tool, eyebrow: 'OPERATION' } })} /></section>
        </>}

        {page === 'systems' && <><div className="dash-view-toolbar"><SearchInput query={query} setQuery={setQuery} placeholder="Find a system…" /><span>{namespaces.length} registered{established.length ? ` · ${established.length} listed` : ''}</span></div><div className="dash-systems-grid">{filteredSystems.map((namespace, i) => <button className="dash-system-card" key={namespace} onClick={() => setSelected({ id: namespace, data: { label: namespace, eyebrow: 'SYSTEM' } })}><div className="dash-system-card-top"><span className="dash-large-icon">{i % 2 ? <Box size={24} strokeWidth={1.3} /> : <Database size={24} strokeWidth={1.3} />}</span><Signal>{isLive ? 'Registered' : 'Example system'}</Signal></div><h2>{namespace === 'maintenance' ? 'Field services' : namespace === 'inventory' ? 'Industrial logistics' : namespace}</h2><p>{namespace}</p><div className="dash-system-card-bottom"><span>{operations.filter(o => o.tool.startsWith(namespace + '.')).length} operations</span><span>Inspect system <ArrowUpRight size={13} /></span></div></button>)}{established.filter(e => e.system.includes(query.toLowerCase())).map(e => <button className="dash-system-card" key={`est-${e.system}`} onClick={() => setSelected({ id: e.system, data: { label: e.title || e.system, eyebrow: e.parent ? 'PARENT COMPANY · ESTABLISHED' : 'ESTABLISHED SYSTEM', kind: 'established' } })}><div className="dash-system-card-top"><span className="dash-large-icon"><Globe2 size={24} strokeWidth={1.3} /></span><Signal>{e.parent ? 'Parent company' : 'Listed only'}</Signal></div><h2>{e.title || e.system}</h2><p>{e.system}</p><div className="dash-system-card-bottom"><span>{e.operations.length} operations · never called</span><span>Inspect system <ArrowUpRight size={13} /></span></div></button>)}<button className="dash-add-system-card" onClick={() => setModal('add')}><Plus size={25} strokeWidth={1.2} /><span>Bring another system<br />into your orbit.</span><small>Import from GitHub</small></button></div><GraphPanel operations={operations} isLive={isLive} traceStep={traceStep} links={isLive ? liveLinks : []} expanded={expandedSystems} onToggle={toggleSystem} onMore={showSystemOperations} onSelect={setSelected} established={established} large /></>}

        {page === 'operations' && <><div className="dash-view-toolbar"><SearchInput query={query} setQuery={setQuery} placeholder="Search tools, descriptions, tiers…" /><span>{filteredOperations.length} operations <span className="dash-separator">/</span> <LockKeyhole size={12} />Read-only access</span></div><section className="dash-operations-panel"><OperationTable operations={filteredOperations.slice(0, opLimit)} onSelect={op => setSelected({ id: op.tool, data: { label: op.tool, eyebrow: 'OPERATION' } })} />{filteredOperations.length > opLimit && <div className="dash-load-more"><span>Showing {opLimit} of {filteredOperations.length}</span><button className="dash-secondary-button" onClick={() => setOpLimit(n => n + PAGE)}>Show {Math.min(PAGE, filteredOperations.length - opLimit)} more</button></div>}{!filteredOperations.length && <div className="dash-empty"><Search size={24} /><h3>No operations found</h3><p>{operations.length ? 'Try a different name or ingestion tier.' : 'Your gateway has no published operations yet.'}</p></div>}</section><div className="dash-inline-note"><ShieldCheck size={16} /><p>Every tool has a trail.<span>Source location, version, and ingestion tier stay attached to every operation.</span></p></div></>}

        {page === 'connect' && <ConnectAgent base={gatewayBase} live={isLive} operations={operations} onOpenSettings={() => setModal('settings')} />}
        {page === 'activity' && <section className="dash-full-activity"><div className="dash-panel-header"><h2>{isLive ? 'Gateway activity' : 'Example event stream'}</h2>{!isLive && <button className="dash-secondary-button" onClick={runDemo} disabled={traceStep >= 0}><Zap size={14} />{traceStep >= 0 ? 'Demo running…' : 'Run demo workflow'}</button>}</div><div className="dash-activity-list">{feed.map(event => <EventRow key={event.id} event={event} />)}</div><div className="dash-inline-note"><LockKeyhole size={15} /><p>Outbound events, clear provenance.<span>{isLive ? 'Events from your gateway appear here, newest first.' : 'These example events illustrate the planned integration lifecycle. No messages are sent.'}</span></p></div></section>}

        <footer className="dash-footer"><span><BrandMark size={18} /> A new dimension for legacy software.</span><span>{isLive ? 'Connected registry' : 'DESIGN PREVIEW'}<i />REPLIC8</span></footer>
      </div>
    </main>

    {selected && <div className="dash-overlay" onMouseDown={e => { if (e.target === e.currentTarget) setSelected(null); }}><aside className="dash-inspector" role="dialog" aria-modal="true" aria-label="System details"><div className="dash-modal-top"><span className="dash-section-eyebrow">{selected.data.eyebrow || 'CONNECTION DETAILS'}</span><button className="dash-icon-button" onClick={() => setSelected(null)} aria-label="Close details"><X size={18} /></button></div><div className="dash-inspector-icon">{selected.id === 'gateway' ? <BrandMark size={57} /> : selectedEst ? <Globe2 size={29} strokeWidth={1.2} /> : <Database size={29} strokeWidth={1.2} />}</div><h2>{selected.data.label}</h2><p>{selectedOp?.description || selected.data.subtitle || 'Inspect the operations registered to this system.'}</p><Signal>{isLive ? 'Gateway data' : 'Example data'}</Signal><div className="dash-inspector-rule" />{selectedEst ? <EstablishedDetails entry={selectedEst} /> : selectedOp ? <><dl className="dash-provenance"><div><dt>Access</dt><dd><LockKeyhole size={12} />{selectedOp.access} · {selectedOp.enabled ? 'enabled' : 'disabled'}</dd></div><div><dt>Ingestion tier</dt><dd>{selectedOp.tier}</dd></div><div><dt>Version</dt><dd>v{selectedOp.version}</dd></div><div><dt>Source</dt><dd><code>{selectedOp.source}</code></dd></div><div><dt>Source commit</dt><dd><code>{selectedOp.source_commit?.slice(0, 12) || '—'}</code></dd></div></dl><TryIt base={gatewayBase} token={token} op={selectedOp} live={isLive} /><span className="dash-section-eyebrow">INPUT SCHEMA</span><pre className="dash-code">{JSON.stringify(selectedOp.input_schema, null, 2)}</pre><button className="dash-secondary-button" onClick={() => copyOperation(selectedOp)}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied tool name' : 'Copy tool name'}</button></> : <>{isLive && selectedNamespace !== 'gateway' && <SystemHealth base={sessionRead('replic8.gateway', gateway.trim().replace(/\/$/, ''))} token={token} adminToken={ownerToken} setAdminToken={setAdminToken} system={selectedNamespace} events={rawEvents} tick={healTick} onChanged={() => { refreshOperations(); setHealTick(t => t + 1); }} />}<span className="dash-section-eyebrow">REGISTERED OPERATIONS</span>{selectedOps.length ? <>{selectedOps.slice(0, PAGE).map(op => <button key={op.tool} className="dash-inspector-operation" onClick={() => setSelected({ id: op.tool, data: { label: op.tool, eyebrow: 'OPERATION' } })}><Code2 size={15} /><span>{op.tool}<small>{op.tier} · v{op.version} · {op.access}</small></span><ChevronRight size={14} /></button>)}{selectedOps.length > PAGE && <button className="dash-secondary-button" onClick={() => showSystemOperations(selectedNamespace)}>Show all {selectedOps.length} in Operations</button>}</> : <p className="dash-inspector-note">{selected.id === 'gateway' ? `${operations.length} namespaced tools form the unified gateway. Select a legacy system to inspect its tools.` : 'This node shows the modern parent platform in the demo scenario. Its agents access legacy tools through REPLIC8.'}</p>}</>}<div className="dash-inspector-bottom"><ShieldCheck size={15} /><span>{isLive ? 'Data read from your authenticated gateway.' : 'Illustrative preview. No legacy code is executed.'}</span></div></aside></div>}

    {modal && <div className="dash-overlay dash-overlay--center" onMouseDown={e => { if (e.target === e.currentTarget) setModal(null); }}><section className="dash-modal" role="dialog" aria-modal="true" aria-labelledby="dash-modal-title"><div className="dash-modal-top"><span className="dash-section-eyebrow">{modal === 'add' ? 'EXPAND YOUR ORBIT' : modal === 'settings' ? 'WORKSPACE SETTINGS' : 'YOUR WORKSPACE'}</span><button className="dash-icon-button" onClick={() => setModal(null)} aria-label="Close dialog"><X size={18} /></button></div>
      {modal === 'add' && <AddSystem base={sessionRead('replic8.gateway', gateway.trim().replace(/\/$/, ''))} token={token} adminToken={ownerToken} setAdminToken={setAdminToken} live={isLive} onOpenSettings={() => setModal('workspace')} onPublished={refreshOperations} onClose={() => { setModal(null); setView('systems'); }} />}
      {modal === 'settings' && <><div className="dash-modal-symbol"><Network size={27} strokeWidth={1.3} /></div><h2 id="dash-modal-title">Connect your gateway.</h2><p>Read your published operation registry from an existing REPLIC8 backend. Your token stays in this browser session.</p><form onSubmit={connectGateway}><label>Gateway address<input required value={gateway} onChange={e => setGateway(e.target.value)} placeholder="/gateway" spellCheck={false} /></label><label>Gateway access token<input type="password" required value={token} onChange={e => setToken(e.target.value)} placeholder="Your bearer token" autoComplete="off" /></label>{connectionError && <p className="dash-form-error" role="alert">{connectionError}</p>}<div className="dash-form-note"><ShieldCheck size={15} /><span>This connects read-only registry data. Ingest, repair, and history require additional backend endpoints.</span></div><button type="submit" className="dash-primary-button" disabled={connecting}>{connecting ? 'Checking gateway…' : 'Connect gateway'}<ArrowRight size={15} /></button>{isLive && <button className="dash-quiet-button dash-disconnect" type="button" onClick={leaveWorkspace}>Disconnect</button>}</form></>}
      {modal?.startsWith('workspace') && <WorkspaceAccess key={modal} initialTab={modal === 'workspace-new' ? 'new' : 'open'} gateway={gateway} setGateway={setGateway} isLive={isLive} info={wsInfo} token={token} connecting={connecting} error={connectionError} onOpen={connectWith} onLeave={leaveWorkspace} />}
    </section></div>}
  </div>;
}

// An established system: REPLIC8 read its API file and lists the operations. It never calls them.
function EstablishedDetails({ entry }) {
  return <>
    <dl className="dash-provenance">
      <div><dt>Kind</dt><dd>Established · {entry.parent ? 'parent company' : 'listed system'}</dd></div>
      <div><dt>Called by REPLIC8</dt><dd><LockKeyhole size={12} />Never</dd></div>
      <div><dt>Repository</dt><dd><code>{entry.repo}</code></dd></div>
      <div><dt>API file</dt><dd><code>{entry.spec_file}</code>{entry.api_version ? ` · v${entry.api_version}` : ''}</dd></div>
      <div><dt>Source commit</dt><dd><code>{entry.source_commit?.slice(0, 12) || '—'}</code></dd></div>
    </dl>
    <span className="dash-section-eyebrow">LISTED OPERATIONS</span>
    {entry.operations.slice(0, PAGE).map(op => <div key={op.tool} className="dash-listed-op"><code>{op.method}</code><span>{op.path}<small>{op.summary}</small></span></div>)}
    {entry.operations.length > PAGE && <p className="dash-inspector-note">And {entry.operations.length - PAGE} more in the API file.</p>}
    <p className="dash-inspector-note">Read from the system's API file. {entry.parent ? 'Its agents use REPLIC8 to reach the legacy systems; ' : ''}REPLIC8 never calls this system. Import it again to refresh the list.</p>
  </>;
}

function Metric({ label, value, detail, icon: Icon, spark }) {
  return <article className="dash-metric"><div className="dash-metric-label">{label}<Icon size={15} strokeWidth={1.5} /></div><div className={`dash-metric-value ${value === 'Read only' ? 'dash-metric-value--text' : ''}`}>{value}{spark && <svg viewBox="0 0 72 26" aria-hidden="true"><path d={spark} fill="none" stroke="currentColor" strokeWidth="1.25" /></svg>}</div><p><span className="dash-small-dot" />{detail}</p></article>;
}

function EventRow({ event }) {
  const Icon = event.icon || Activity;
  return <article className="dash-event"><span className="dash-event-icon"><Icon size={15} strokeWidth={1.5} /></span><div><h3>{event.title}</h3><p>{event.detail}</p><time>{event.time}</time></div></article>;
}

function SearchInput({ query, setQuery, placeholder }) {
  return <label className="dash-search"><Search size={15} /><input aria-label={placeholder} placeholder={placeholder} value={query} onChange={e => setQuery(e.target.value)} />{query && <button onClick={() => setQuery('')} aria-label="Clear search"><X size={12} /></button>}</label>;
}

function OperationTable({ operations, onSelect }) {
  return <div className="dash-table-scroll"><table className="dash-table"><thead><tr><th>Operation</th><th>Source</th><th>Ingestion</th><th>Version</th><th>Access</th><th><span className="dash-sr-only">Inspect</span></th></tr></thead><tbody>{operations.map(op => <tr key={op.tool} onClick={() => onSelect(op)} tabIndex={0} role="button" onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(op); } }} aria-label={`Inspect ${op.tool}`}><td><span className="dash-tool"><Code2 size={14} /><code>{op.tool}</code></span></td><td><code className="dash-source">{op.source}</code></td><td><span className="dash-tag">{op.tier}</span></td><td><span className="dash-version">v{op.version}</span></td><td><span className="dash-read"><LockKeyhole size={11} />{op.access}</span></td><td><ArrowUpRight size={13} /></td></tr>)}</tbody></table></div>;
}
