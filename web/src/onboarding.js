// Pure helpers for the "Add a system" flow. The rules mirror backend/replic8/ingest.py
// and gateway.py so mistakes are caught before a request is sent; the backend still
// checks everything again.

export const STAGES = [
  ['fetch', 'Import from GitHub'],
  ['detect', 'Detect the language'],
  ['build', 'Build in the sandbox'],
  ['extract', 'Find the functions'],
  ['propose', 'Propose operations'],
  ['test', 'Run contract tests'],
  ['publish', 'Publish'],
];

const SYSTEM_NAME = /^[a-z][a-z0-9_]{0,31}$/;
const OWNER = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/;
const REPO = /^[A-Za-z0-9._-]{1,100}$/;

export function checkSystemName(name) {
  return SYSTEM_NAME.test(name) ? '' : 'Use lowercase letters, numbers and underscores, starting with a letter (up to 32). It becomes the tool prefix, like "maintenance".';
}

// Returns { url } with the canonical form, or { error }.
export function checkGithubUrl(input) {
  const fail = (error) => ({ error });
  if (typeof input !== 'string' || input.length > 300) return fail('Enter a short GitHub repository URL.');
  let parsed;
  try { parsed = new URL(input.trim()); } catch { return fail('Enter a GitHub repository URL: https://github.com/owner/repository'); }
  if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || parsed.username || parsed.password || parsed.port) {
    return fail('Only public https://github.com repositories can be imported.');
  }
  if (parsed.search || parsed.hash) return fail('Remove the ? and # parts from the URL.');
  const parts = parsed.pathname.split('/').filter(Boolean);
  if (parts.length !== 2) return fail('Use the repository root: https://github.com/owner/repository');
  const owner = parts[0];
  const repo = parts[1].replace(/\.git$/, '');
  if (!OWNER.test(owner) || !REPO.test(repo) || repo === '.' || repo === '..') return fail('That owner or repository name is not valid.');
  return { url: `https://github.com/${owner}/${repo}` };
}

// Parses the optional "known-good values" box: one field=value per line, e.g. request_id=R-1001.
// Returns { values } (possibly empty) or { error }.
const FIELD = /^[a-z][a-z0-9_]{0,30}$/;
export function parseKnownValues(text) {
  const values = {};
  for (const [i, raw] of String(text || '').split('\n').entries()) {
    const line = raw.trim();
    if (!line) continue;
    const eq = line.indexOf('=');
    const field = eq < 0 ? '' : line.slice(0, eq).trim();
    const value = eq < 0 ? '' : line.slice(eq + 1).trim();
    if (!FIELD.test(field)) return { error: `Line ${i + 1}: write it as field=value, with a lowercase field name like request_id.` };
    if (!value || value.length > 64 || value.includes('=') || /[\u0000-\u001f]/.test(value)) return { error: `Line ${i + 1}: the value must be 1 to 64 characters and cannot contain "=".` };
    values[field] = [...(values[field] || []), value];
    if (values[field].length > 5) return { error: `Line ${i + 1}: use at most 5 values for ${field}.` };
    if (Object.keys(values).length > 20) return { error: 'Use at most 20 different fields.' };
  }
  return { values };
}

// Turns the gateway's event log into per-stage state for one import.
// `afterId` is the last event id seen before the import started, so older runs are ignored.
export function progress(events, system, afterId = 0) {
  const mine = events.filter((e) => e.system === system && e.id > afterId);
  const seen = mine.filter((e) => e.kind === 'onboard_stage').map((e) => e.detail);
  const failed = [...mine].reverse().find((e) => e.kind === 'onboard_failed');
  const published = [...mine].reverse().find((e) => e.kind === 'published');
  const status = failed ? 'failed' : published ? 'published' : mine.some((e) => e.kind === 'onboard_started') ? 'running' : 'starting';
  const current = seen.length ? STAGES.findIndex(([key]) => key === seen[seen.length - 1]) : -1;

  const stages = STAGES.map(([key, label], i) => {
    let state = 'pending';
    if (status === 'published' || i < current) state = 'done';
    else if (i === current) state = status === 'failed' ? 'failed' : 'active';
    return { key, label, state };
  });
  return {
    status,
    stages,
    reason: failed ? failed.detail : '',
    operations: published ? published.operations ?? 0 : 0,
    rejected: published ? published.rejected ?? 0 : 0,
    version: published ? published.version : null,
    failingTools: [...new Set(mine.filter((e) => e.kind === 'contract_failed').map((e) => e.tool))],
    lastId: events.reduce((max, e) => Math.max(max, e.id), afterId),
  };
}
