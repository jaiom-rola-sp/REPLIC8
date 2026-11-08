import { useState } from 'react';
import { ArrowRight, Check, Copy, Eye, EyeOff, KeyRound, LockKeyhole, LogOut, Plus, Workflow } from 'lucide-react';
import { checkWorkspaceToken, createWorkspace, normalizeGateway } from './workspace.js';
import './workspace.css';

// Start a new workspace, open a saved one with its token, or leave the current one.
// The admin token (needed only to create a workspace) is held in this component's memory, never stored.
export default function WorkspaceAccess({ gateway, setGateway, isLive, info, token: openToken, connecting, error, onOpen, onLeave, initialTab = 'open' }) {
  const [tab, setTab] = useState(initialTab);
  const [token, setToken] = useState('');
  const [admin, setAdmin] = useState('');
  const [name, setName] = useState('');
  const [created, setCreated] = useState(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [shown, setShown] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const inWorkspace = isLive && info && info.kind === 'workspace';

  async function open(e) {
    e.preventDefault(); setProblem('');
    const bad = checkWorkspaceToken(token);
    if (bad) return setProblem(bad);
    try { onOpen(normalizeGateway(gateway), token.trim()); } catch (err) { setProblem(err.message); }
  }

  async function create(e) {
    e.preventDefault(); setProblem(''); setBusy(true);
    try {
      const base = normalizeGateway(gateway);
      const ws = await createWorkspace(base, admin.trim(), name);
      setCreated({ ...ws, base }); setAdmin(''); setSaved(false);
    } catch (err) {
      setProblem(err.name === 'TimeoutError' ? 'The gateway did not respond in time.' : err.message === 'Failed to fetch' ? 'Could not reach the gateway. Check its address.' : err.message);
    } finally { setBusy(false); }
  }

  async function copy(value) {
    try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { setCopied(false); }
  }

  // The token box: hidden until Show is pressed (unless `open`), always copyable.
  const tokenBox = (value, open) => (
    <div className="dash-ws-token">
      <code aria-label="Workspace token">{open || shown ? value : `r8w_${'•'.repeat(24)}`}</code>
      {!open && <button type="button" className="dash-secondary-button" onClick={() => setShown(v => !v)} aria-label={shown ? 'Hide token' : 'Show token'}>{shown ? <EyeOff size={14} /> : <Eye size={14} />}{shown ? 'Hide' : 'Show'}</button>}
      <button type="button" className="dash-secondary-button" onClick={() => copy(value)}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}</button>
    </div>
  );

  const header = <><div className="dash-modal-symbol"><Workflow size={28} strokeWidth={1.3} /></div><h2 id="dash-modal-title">{inWorkspace ? (info.name || 'Your workspace') : 'Your workspace.'}</h2></>;

  if (created) {
    return (<>{header}
      <p>Your new workspace is ready. Save this token now: it opens this workspace later, and it can't be shown again.</p>
      {tokenBox(created.token, true)}
      <label className="dash-check"><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} /><span>I've saved this token somewhere safe<small>Anyone with it can open this workspace. Without it, the workspace can't be reopened.</small></span></label>
      <button type="button" className="dash-primary-button" disabled={!saved || connecting} onClick={() => onOpen(created.base, created.token)}>{connecting ? 'Opening…' : 'Open this workspace'}<ArrowRight size={15} /></button>
      {error && <p className="dash-form-error" role="alert">{error}</p>}
    </>);
  }

  if (leaving && inWorkspace) {
    return (<>{header}
      <p>Before you leave, save this token. It is the only way back into this workspace, and everything you did here comes back with it.</p>
      {tokenBox(openToken, true)}
      <button type="button" className="dash-primary-button" onClick={onLeave}><LogOut size={15} />I've saved it, leave workspace</button>
      <button type="button" className="dash-quiet-button dash-disconnect" onClick={() => setLeaving(false)}>Stay in this workspace</button>
    </>);
  }

  return (<>{header}
    {inWorkspace && openToken && <><span className="dash-section-eyebrow">YOUR WORKSPACE TOKEN</span>{tokenBox(openToken, false)}</>}
    {inWorkspace
      ? <p>Everything you import, call, repair or roll back here is saved in this workspace. Leave it to return to a blank screen; open it again later with its token.</p>
      : <p>Start a new, empty workspace, or open one you saved. Your work is kept on the gateway under its workspace token.</p>}
    {isLive && <button type="button" className="dash-quiet-button dash-disconnect" onClick={() => (inWorkspace ? setLeaving(true) : onLeave())}><LogOut size={14} />Leave {inWorkspace ? 'workspace' : 'gateway'}</button>}
    <div className="dash-tabs dash-ws-tabs" role="tablist" aria-label="Workspace">
      <button type="button" role="tab" aria-selected={tab === 'open'} className="dash-tab" onClick={() => { setTab('open'); setProblem(''); }}><KeyRound size={13} />Open a workspace</button>
      <button type="button" role="tab" aria-selected={tab === 'new'} className="dash-tab" onClick={() => { setTab('new'); setProblem(''); }}><Plus size={13} />Start a new workspace</button>
    </div>
    <label>Gateway address<input required value={gateway} onChange={e => setGateway(e.target.value)} placeholder="https://replic8.example.ts.net" spellCheck={false} /></label>
    {tab === 'open'
      ? <form onSubmit={open}>
          <label>Workspace token<input type="password" required value={token} onChange={e => { setToken(e.target.value); setProblem(''); }} placeholder="r8w_…" autoComplete="off" /></label>
          {(problem || error) && <p className="dash-form-error" role="alert">{problem || error}</p>}
          <button type="submit" className="dash-primary-button" disabled={connecting}>{connecting ? 'Opening…' : 'Open workspace'}<ArrowRight size={15} /></button>
        </form>
      : <form onSubmit={create}>
          <label>Workspace name <span>optional</span><input value={name} onChange={e => setName(e.target.value)} maxLength={60} placeholder="e.g. Judges demo" /></label>
          <label>Admin token<input type="password" required value={admin} onChange={e => { setAdmin(e.target.value); setProblem(''); }} placeholder="Needed only to create a workspace" autoComplete="off" /></label>
          {problem && <p className="dash-form-error" role="alert">{problem}</p>}
          <div className="dash-form-note"><LockKeyhole size={14} /><span>The admin token stays in this tab's memory and is never saved. The new workspace gets its own token.</span></div>
          <button type="submit" className="dash-primary-button" disabled={busy}>{busy ? 'Creating…' : 'Create workspace'}<ArrowRight size={15} /></button>
        </form>}
  </>);
}

// What the dashboard shows when no workspace is open: nothing from anyone else, just the two ways in.
export function BlankWorkspace({ onStart, onOpen }) {
  return (
    <section className="dash-ws-blank">
      <Workflow size={30} strokeWidth={1.2} />
      <h2>No workspace open.</h2>
      <p>Start a new workspace and import your own repositories, or open one you saved with its workspace token. Everything you did there comes back.</p>
      <div className="dash-ws-blank-actions">
        <button type="button" className="dash-primary-button" onClick={onStart}><Plus size={15} />Start a new workspace</button>
        <button type="button" className="dash-secondary-button" onClick={onOpen}><KeyRound size={14} />Open a workspace</button>
      </div>
    </section>
  );
}
