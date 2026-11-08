import { useEffect, useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { buildInput, describeFailure, fieldsFor, parseJsonInput } from './tryIt.js';

const MAX_SHOWN = 4000;

// Run one read-only operation from the operation panel and show the answer and where it came from.
export default function TryIt({ base, token, op, live }) {
  const fields = useMemo(() => fieldsFor(op.input_schema), [op]);
  const [values, setValues] = useState({});
  const [json, setJson] = useState('{}');
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { setValues({}); setJson('{}'); setOut(null); setError(''); }, [op.tool]);

  const blocked = op.access !== 'read' || op.enabled === false;
  const set = (name, value) => { setValues((v) => ({ ...v, [name]: value })); setError(''); };

  async function run(e) {
    e.preventDefault();
    setError(''); setOut(null);
    const built = fields ? buildInput(fields, values) : parseJsonInput(json);
    if (built.error) return setError(built.error);
    setBusy(true);
    const start = performance.now();
    try {
      const res = await fetch(`${base}/v1/operations/${encodeURIComponent(op.tool)}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: built.input }),
        signal: AbortSignal.timeout(30000),
      });
      const ms = Math.round(performance.now() - start);
      let body = null;
      try { body = await res.json(); } catch { /* not JSON */ }
      if (!res.ok) setError(describeFailure(res.status, typeof body?.detail === 'string' ? body.detail : ''));
      else setOut({ ms, result: body.result, provenance: body.provenance || {} });
    } catch (err) {
      setError(err.name === 'TimeoutError' ? 'The gateway did not respond in time.' : err.message === 'Failed to fetch' ? 'Could not reach the gateway.' : 'The call could not be completed.');
    } finally { setBusy(false); }
  }

  const shown = out && JSON.stringify(out.result, null, 2);
  return (
    <div className="dash-tryit">
      <span className="dash-section-eyebrow">TRY IT</span>
      {!live && <p className="dash-tryit-note">Connect a gateway to run this tool.</p>}
      {live && blocked && <p className="dash-tryit-note">This is a write operation. Write operations are disabled in v1, so it cannot be run.</p>}
      <form onSubmit={run}>
        {fields ? fields.map((f) => (
          <label key={f.name}>{f.name}{f.required ? ' *' : ''}
            {f.kind === 'boolean' ? (
              <select value={values[f.name] === undefined ? '' : String(values[f.name])} onChange={(e) => set(f.name, e.target.value === '' ? undefined : e.target.value === 'true')}>
                <option value="">(not set)</option><option value="true">true</option><option value="false">false</option>
              </select>
            ) : f.kind === 'choice' ? (
              <select value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)}>
                <option value="">{f.required ? 'Pick one' : '(not set)'}</option>{f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            ) : (
              <input value={values[f.name] ?? ''} onChange={(e) => set(f.name, e.target.value)} inputMode={f.kind === 'text' ? undefined : 'decimal'} spellCheck={false} autoComplete="off" />
            )}
          </label>
        )) : (
          <label>Input (JSON)<textarea rows={4} value={json} onChange={(e) => { setJson(e.target.value); setError(''); }} spellCheck={false} /></label>
        )}
        <button className="dash-secondary-button" type="submit" disabled={busy || !live || blocked}><Play size={13} />{busy ? 'Running…' : 'Run'}</button>
      </form>
      {error && <p className="dash-form-error" role="alert">{error}</p>}
      {out && (
        <>
          <pre className="dash-code">{shown.length > MAX_SHOWN ? `${shown.slice(0, MAX_SHOWN)}\n…` : shown}</pre>
          <dl className="dash-provenance">
            <div><dt>Answered by</dt><dd>v{out.provenance.version ?? '?'} · {out.provenance.tier ?? '?'}</dd></div>
            <div><dt>Source</dt><dd><code>{out.provenance.source ?? '?'}</code></dd></div>
            <div><dt>Commit</dt><dd><code>{String(out.provenance.source_commit || '').slice(0, 12) || '?'}</code></dd></div>
            <div><dt>Took</dt><dd>{out.ms} ms</dd></div>
          </dl>
        </>
      )}
    </div>
  );
}
