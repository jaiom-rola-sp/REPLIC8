// Helpers for workspaces: separate, token-opened spaces on one REPLIC8 gateway.
// A workspace token starts with "r8w_" and is shown once when the workspace is created.
// Pure functions where possible, so `node --test src/workspace.test.js` covers them.

export const WORKSPACE_TOKEN = /^r8w_[A-Za-z0-9_-]{20,120}$/;

// "https://x.ts.net/" -> "https://x.ts.net"; "/gateway" stays (the dev proxy). Throws on anything else.
export function normalizeGateway(address) {
  const raw = (address || '').trim().replace(/\/+$/, '');
  if (raw === '/gateway') return raw;
  let parsed;
  try { parsed = new URL(raw); } catch { throw new Error('Enter the gateway address, like https://replic8.example.ts.net'); }
  if (!['https:', 'http:'].includes(parsed.protocol)) throw new Error('Use an HTTP or HTTPS gateway address.');
  return parsed.href.replace(/\/+$/, '');
}

// The address the dashboard starts with: VITE_REPLIC8_GATEWAY when the site is built with it (e.g. on Vercel),
// otherwise the dev proxy "/gateway". It is an address, not a secret.
export function defaultGateway(env = {}) {
  const value = (env.VITE_REPLIC8_GATEWAY || '').trim();
  if (!value) return '/gateway';
  try { return normalizeGateway(value); } catch { return '/gateway'; }
}

export function checkWorkspaceToken(token) {
  return WORKSPACE_TOKEN.test((token || '').trim())
    ? ''
    : 'That is not a workspace token. Workspace tokens start with r8w_ and were shown when the workspace was created.';
}

// Sidebar label for what is open.
export function workspaceLabel(info, isLive) {
  if (!isLive) return { title: 'No workspace open', subtitle: 'Start or open one' };
  if (info && info.kind === 'workspace') return { title: info.name || `Workspace ${info.id}`, subtitle: 'Your saved workspace' };
  return { title: 'Shared gateway', subtitle: 'Gateway token' };
}

// POST /v1/workspaces with the admin token. Returns { id, name, token, created_at }.
export async function createWorkspace(base, adminToken, name, fetchImpl = fetch) {
  const res = await fetchImpl(`${base}/v1/workspaces`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: (name || '').slice(0, 60) }),
    signal: AbortSignal.timeout(10000),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 || res.status === 403) throw new Error('The gateway did not accept this admin token.');
  if (res.status === 503) throw new Error('This gateway does not have workspaces turned on.');
  if (!res.ok || !WORKSPACE_TOKEN.test(data.token || '')) throw new Error(data.detail || `The gateway returned ${res.status}.`);
  return data;
}

// GET /v1/workspace: which space a token opens. Returns null if the gateway doesn't support it.
export async function describeWorkspace(base, token, fetchImpl = fetch) {
  try {
    const res = await fetchImpl(`${base}/v1/workspace`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(8000) });
    return res.ok ? await res.json() : null;
  } catch { return null; }
}
