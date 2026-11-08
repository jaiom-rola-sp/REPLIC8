import { useState } from 'react';
import { Check, Copy, LockKeyhole } from 'lucide-react';
import { TOKEN_PLACEHOLDER, gatewayAddress, isLocalAddress, sampleCall, snippets } from './connectSnippets.js';

function Block({ title, hint, code }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { setCopied(false); }
  }
  return (
    <section className="dash-connect-block">
      <div className="dash-connect-head">
        <div><h3>{title}</h3>{hint && <p>{hint}</p>}</div>
        <button className="dash-secondary-button" onClick={copy}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}</button>
      </div>
      <pre className="dash-code">{code}</pre>
    </section>
  );
}

// How a parent company's agents and apps use the gateway. The token is only ever a placeholder here.
export default function ConnectAgent({ base, live, operations, onOpenSettings }) {
  const address = gatewayAddress(live ? base : '', window.location.origin);
  const s = snippets(address, sampleCall(operations));
  const systems = new Set(operations.map((o) => o.tool.split('.')[0])).size;
  return (
    <div className="dash-connect">
      {!live && (
        <div className="dash-demo-notice"><span>Connect your gateway to fill in your own address. The commands below use a placeholder.</span>
          <button className="dash-quiet-button" onClick={onOpenSettings}>Connect your gateway</button></div>
      )}
      {live && isLocalAddress(address) && (
        <div className="dash-demo-notice"><span>This address only works on this computer. Anyone else needs the gateway's public address.</span></div>
      )}
      <p className="dash-connect-lead">
        Agents use <b>MCP</b> at <code>{address}/mcp</code>. Ordinary apps can call the same tools over <b>REST</b>.
        {live && <> Your token can see {operations.length} {operations.length === 1 ? 'tool' : 'tools'} across {systems} {systems === 1 ? 'system' : 'systems'}.</>}
      </p>
      <Block title="Claude Code" hint="Run this once in a terminal. Add --scope user to keep it for every project." code={s.claude} />
      <Block title="Any MCP client" hint="Most clients accept the same url and headers under their own settings key." code={s.config} />
      <Block title="curl: list the tools your token can use" code={s.curlList} />
      <Block title="curl: call one tool" hint="Read-only calls only. Write operations are disabled." code={s.curlCall} />
      <div className="dash-inline-note"><LockKeyhole size={16} /><p>Replace {TOKEN_PLACEHOLDER} with your gateway token.<span>A token only sees the systems it is scoped to. The admin token, which imports and repairs systems, never goes in an agent.</span></p></div>
    </div>
  );
}
