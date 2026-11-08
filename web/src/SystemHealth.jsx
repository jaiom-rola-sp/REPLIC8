import { useEffect, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { reasonLabel, systemStatus } from './liveEvents.js';

function explain(status) {
  if (status === 401 || status === 403) return 'The gateway did not accept this admin token.';
  if (status === 404) return 'The gateway does not know that system or version.';
  if (status === 429) return 'Too many requests. Wait a moment and try again.';
  if (status === 503) return 'Repairs are not set up on this gateway.';
  return `The gateway returned ${status}.`;
}

const tests = (v) => {
  const all = Object.values(v.tests || {});
  return `${all.filter((t) => t.passed).length}/${all.length} tools tested`;
};

// Version history for one system, with Check for changes, Repair now and Roll back (admin token, in memory only).
export default function SystemHealth({ base, token, adminToken, setAdminToken, system, events, tick, onChanged }) {
  const [history, setHistory] = useState(null);
  const [admin, setAdmin] = useState(adminToken);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let off = false;
    (async () => {
      try {
        const res = await fetch(`${base}/v1/systems/${encodeURIComponent(system)}/versions`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(8000) });
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!off && Array.isArray(data.versions)) setHistory(data);
      } catch { if (!off) setHistory(null); }
    })();
    return () => { off = true; };
  }, [base, token, system, tick]);

  async function act(path, body, done) {
    setError(''); setNote('');
    if (!admin) return setError('Enter the admin token first.');
    setBusy(true);
    try {
      const res = await fetch(`${base}/v1/admin/systems/${encodeURIComponent(system)}/${path}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${admin}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
        signal: AbortSignal.timeout(15000),
      });
      if (!res.ok) throw new Error(explain(res.status));
      setAdminToken(admin);
      done(await res.json());
    } catch (err) {
      setError(err.name === 'TimeoutError' ? 'The gateway did not respond in time.' : err.message === 'Failed to fetch' ? 'Could not reach the gateway.' : err.message);
    } finally { setBusy(false); }
  }

  const current = history?.current;
  const commit = history?.versions.find((v) => v.version === current)?.source_commit?.slice(0, 7);
  const status = systemStatus(events, system);

  return (
    <div className="dash-health">
      <span className="dash-section-eyebrow">VERSIONS AND REPAIR</span>
      {status && <p className={`dash-health-status is-${status.state}`}><b>{status.text}</b>{status.detail && <span>{status.detail}</span>}</p>}
      {history && (
        <ul className="dash-versions">
          {[...history.versions].reverse().map((v) => (
            <li key={v.version} className={v.version === current ? 'is-current' : ''}>
              <div>
                <b>v{v.version}</b>{v.version === current && <em>current</em>}
                <span>{reasonLabel(v.reason)} · {v.source_commit.slice(0, 7)} · {tests(v)}{Object.keys(v.rejected || {}).length ? ` · ${Object.keys(v.rejected).length} rejected` : ''}</span>
              </div>
              {v.version !== current && (
                <button className="dash-quiet-button" disabled={busy} onClick={() => act('rollback', { version: v.version }, () => { setNote(`Rolled back to v${v.version}.`); onChanged(); })}>
                  <RotateCcw size={12} />Roll back
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!adminToken && (
        <label className="dash-health-token">Admin token<input type="password" value={admin} onChange={(e) => { setAdmin(e.target.value); setError(''); }} placeholder="Needed to check, repair or roll back" autoComplete="off" /></label>
      )}
      <div className="dash-health-actions">
        <button className="dash-secondary-button" disabled={busy} onClick={() => act('check', null, (r) => setNote(r.change_detected ? 'Change detected. A repair has started; follow it in Activity.' : `No change since commit ${commit || 'the published one'}.`))}>Check for changes</button>
        <button className="dash-secondary-button" disabled={busy} onClick={() => act('heal', null, () => setNote('Repair started. It stops right away if the legacy code has not changed.'))}>Repair now</button>
      </div>
      {note && <p className="dash-health-note" role="status">{note}</p>}
      {error && <p className="dash-form-error" role="alert">{error}</p>}
    </div>
  );
}
