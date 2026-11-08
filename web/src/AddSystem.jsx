import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, GitBranch, LockKeyhole } from 'lucide-react';
import { ESTABLISHED_STAGES, STAGES, checkGithubUrl, checkSpecPath, checkSystemName, parseKnownValues, progress } from './onboarding.js';

const TABS = [
  ['legacy', 'Legacy system'],
  ['established', 'Established system'],
];
// How each kind of import is followed: its stages and the event that means "done".
const FLOW = { legacy: [STAGES, 'published'], established: [ESTABLISHED_STAGES, 'listed'] };
const POLL_MS = 1000;
const GIVE_UP_MS = 10 * 60 * 1000;

async function getEvents(base, token, after) {
  const res = await fetch(`${base}/v1/events?after=${after}&limit=500`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`events ${res.status}`);
  const data = await res.json();
  if (!Array.isArray(data.events)) throw new Error('unexpected events response');
  return data.events;
}

function explain(status) {
  if (status === 401 || status === 403 || status === 404) return 'The gateway did not accept this admin token, or the admin API is switched off.';
  if (status === 409) return 'This system is already being imported, or the name is used by another kind of system.';
  if (status === 422) return 'The gateway did not accept that system name or repository URL.';
  if (status === 429) return 'Too many requests. Wait a moment and try again.';
  if (status === 503) return 'Importing is not set up on this gateway yet (it needs admin tokens and the pipeline).';
  return `The gateway returned ${status}.`;
}

// Import a system from GitHub through the gateway's admin API and follow its progress.
// The admin token is held in memory only (never in browser storage).
export default function AddSystem({ base, token, adminToken, setAdminToken, live, onOpenSettings, onPublished, onClose }) {
  const [tab, setTab] = useState('legacy');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [admin, setAdmin] = useState(adminToken);
  const [known, setKnown] = useState('');
  const [mode, setMode] = useState('auto');
  const [specPath, setSpecPath] = useState('');
  const [parent, setParent] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState(null);
  const timer = useRef(null);
  const alive = useRef(true);

  useEffect(() => () => { alive.current = false; clearTimeout(timer.current); }, []);

  function follow(system, kind, afterId, startedAt) {
    const tick = async () => {
      if (!alive.current) return;
      try {
        const p = progress(await getEvents(base, token, afterId), system, afterId, ...FLOW[kind]);
        setRun({ system, kind, progress: p });
        if (p.status === 'published') { onPublished(); return; }
        if (p.status === 'failed') return;
      } catch { /* the gateway may be busy; keep trying */ }
      if (Date.now() - startedAt > GIVE_UP_MS) { setError('This import has run for over 10 minutes. Check the gateway.'); return; }
      timer.current = setTimeout(tick, POLL_MS);
    };
    tick();
  }

  async function start(e) {
    e.preventDefault();
    setError('');
    const system = name.trim();
    const nameError = checkSystemName(system);
    if (nameError) return setError(nameError);
    const repo = checkGithubUrl(url);
    if (repo.error) return setError(repo.error);
    const established = tab === 'established';
    const values = established ? { values: {} } : parseKnownValues(known);
    if (values.error) return setError(values.error);
    const spec = established ? checkSpecPath(specPath) : { path: '' };
    if (spec.error) return setError(spec.error);
    if (!admin) return setError('Enter the admin token to import a repository.');
    setBusy(true);
    try {
      const before = await getEvents(base, token, 0); // remember where the log is, so older runs are ignored
      const afterId = before.reduce((max, ev) => Math.max(max, ev.id), 0);
      const body = established
        ? { system, repo_url: repo.url, parent, ...(spec.path ? { spec_path: spec.path } : {}) }
        : { system, repo_url: repo.url, ...(mode !== 'auto' ? { mode } : {}), ...(Object.keys(values.values).length ? { known_values: values.values } : {}) };
      const res = await fetch(`${base}${established ? '/v1/admin/established' : '/v1/admin/systems'}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${admin}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(15000),
      });
      if (res.status !== 202) throw new Error(explain(res.status));
      setAdminToken(admin);
      setRun({ system, kind: tab, progress: progress([], system, afterId, ...FLOW[tab]) });
      follow(system, tab, afterId, Date.now());
    } catch (err) {
      setError(err.name === 'TimeoutError' ? 'The gateway did not respond in time.' : err.message === 'Failed to fetch' ? 'Could not reach the gateway. Check its address.' : err.message);
    } finally { setBusy(false); }
  }

  const header = (
    <>
      <div className="dash-modal-symbol"><GitBranch size={27} strokeWidth={1.3} /></div>
      <h2 id="dash-modal-title">{run ? `Importing ${run.system}` : 'Import from GitHub.'}</h2>
    </>
  );

  if (!live) {
    return (<>{header}<p>Connect your gateway first. Importing runs on the gateway, so the dashboard needs its address and token.</p>
      <button className="dash-primary-button" type="button" onClick={onOpenSettings}>Connect your gateway<ArrowRight size={15} /></button></>);
  }

  if (run) {
    const p = run.progress;
    return (<>{header}
      <p>{p.status === 'published' ? (run.kind === 'established' ? 'Done. The system is in your graph. REPLIC8 listed its operations and will never call it.' : 'Done. The tested operations are live on your gateway.') : p.status === 'failed' ? 'The import stopped.' : 'Running on your gateway. This page updates every second.'}</p>
      <ol className="dash-stages" aria-live="polite">
        {p.stages.map((s) => <li key={s.key} data-state={s.state}><i />{s.label}</li>)}
      </ol>
      {p.status === 'failed' && <p className="dash-form-error" role="alert">{p.reason || 'The gateway reported a failure.'}</p>}
      {p.failingTools.length > 0 && <p className="dash-form-error">Contract tests failed for: {p.failingTools.join(', ')}</p>}
      {error && <p className="dash-form-error" role="alert">{error}</p>}
      {p.status === 'published' && <div className="dash-form-note"><Check size={14} /><span>{run.kind === 'established' ? `${p.operations} operations listed from the API file.` : `Version ${p.version}: ${p.operations} operations published, ${p.rejected} rejected.`}</span></div>}
      {p.status === 'published' && <button className="dash-primary-button" type="button" onClick={onClose}>See the systems<ArrowRight size={15} /></button>}
      {p.status === 'failed' && <button className="dash-secondary-button" type="button" onClick={() => { setRun(null); setError(''); }}>Try again</button>}
    </>);
  }

  return (<>{header}
    <div className="dash-tabs" role="tablist" aria-label="What are you importing?">
      {TABS.map(([id, label]) => (
        <button key={id} role="tab" type="button" aria-selected={tab === id} className="dash-tab" onClick={() => { setTab(id); setError(''); }}>{label}</button>
      ))}
    </div>
    {tab === 'legacy'
      ? <p>Paste a public GitHub repository of old code. REPLIC8 imports it, finds its functions, and publishes only the operations that pass their tests.</p>
      : <p>Paste a public GitHub repository of a modern system that already has its own API. REPLIC8 reads its OpenAPI file (YAML or JSON) and shows its operations in the graph. It never runs the code or calls the system.</p>}
    <form onSubmit={start}>
      <label>System name<input value={name} onChange={(e) => { setName(e.target.value); setError(''); }} placeholder={tab === 'legacy' ? 'e.g. maintenance' : 'e.g. company_a'} maxLength={32} spellCheck={false} autoComplete="off" required /></label>
      <label>GitHub repository URL<input type="url" value={url} onChange={(e) => { setUrl(e.target.value); setError(''); }} placeholder="https://github.com/owner/repository" required /></label>
      {tab === 'legacy' && <>
        <label>Known-good values <span>optional</span><textarea value={known} onChange={(e) => { setKnown(e.target.value); setError(''); }} rows={3} spellCheck={false} placeholder={'request_id=R-1001\nwell_id=W-17'} /></label>
        <p className="dash-field-hint">Real IDs from the system's own data, one <code>field=value</code> per line. The contract tests use them to check real records. Without them, the model invents IDs that usually come back as "not found".</p>
        <label>How to read this repo <span>optional</span>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="auto">Automatic (functions and command-line programs)</option>
            <option value="functions">Functions only</option>
            <option value="programs">Command-line programs only</option>
          </select>
        </label>
      </>}
      {tab === 'established' && <>
        <label>API file path <span>optional</span><input value={specPath} onChange={(e) => { setSpecPath(e.target.value); setError(''); }} placeholder="docs/openapi.yaml" maxLength={200} spellCheck={false} autoComplete="off" /></label>
        <p className="dash-field-hint">Leave empty to look for <code>openapi.yaml</code>, <code>openapi.json</code>, <code>swagger.yaml</code> or <code>swagger.json</code> in the top three folders.</p>
        <label className="dash-check"><input type="checkbox" checked={parent} onChange={(e) => setParent(e.target.checked)} /><span>This is the parent company<small>Its agents use REPLIC8 to reach the legacy systems, so the graph draws a line from it into REPLIC8.</small></span></label>
      </>}
      <label>Admin token<input type="password" value={admin} onChange={(e) => { setAdmin(e.target.value); setError(''); }} placeholder="Needed to import" autoComplete="off" required /></label>
      {error && <p className="dash-form-error" role="alert">{error}</p>}
      <div className="dash-form-note"><LockKeyhole size={14} /><span>Public repositories only. The admin token stays in this tab's memory and is never saved.</span></div>
      <button className="dash-primary-button" type="submit" disabled={busy}>{busy ? 'Starting…' : 'Import from GitHub'}<ArrowRight size={15} /></button>
    </form>
  </>);
}
