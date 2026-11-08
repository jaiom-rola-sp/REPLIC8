// Turns the gateway's event log (GET /v1/events) into activity-feed entries and a per-system status.
// Events carry only identifiers, versions, counts and fixed reason codes, so everything here is safe to show.

const clock = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};
const ver = (e) => (e.version != null ? ` v${e.version}` : '');

// One feed entry per event, or null for events that are too noisy to list
// (`onboard_stage` and `onboarded` are covered by the import screen and `published`).
// tone: ok | warn | work | info
export function describeEvent(e) {
  const base = { id: e.id, time: clock(e.time) };
  switch (e.kind) {
    case 'onboard_started': return { ...base, tone: 'work', title: `Import started: ${e.system}`, detail: 'Cloning, building and testing the legacy code' };
    case 'published': return { ...base, tone: 'ok', title: `Published ${e.system}${ver(e)}`, detail: `${e.operations ?? 0} operations live, ${e.rejected ?? 0} rejected` };
    case 'onboard_failed': return { ...base, tone: 'warn', title: `Import failed: ${e.system}`, detail: e.detail || 'See the gateway log' };
    case 'contract_failed': return { ...base, tone: 'warn', title: `Contract test failed: ${e.tool}`, detail: e.detail || '' };
    case 'call_failed': return { ...base, tone: 'warn', title: `A call failed: ${e.tool}`, detail: e.detail || '' };
    case 'change_detected': return { ...base, tone: 'work', title: `Change detected in ${e.system}`, detail: `The legacy repo moved past${ver(e)}` };
    case 'heal_started': return { ...base, tone: 'work', title: `Repair started: ${e.system}`, detail: `Nemotron is reading the code change${e.detail ? ` · ${e.detail}` : ''}` };
    case 'heal_saved': return { ...base, tone: 'ok', title: `Repair saved: ${e.system}${ver(e)}`, detail: 'The new version passed its contract tests' };
    case 'heal_failed': return { ...base, tone: 'warn', title: `Repair failed: ${e.system}`, detail: e.detail || '' };
    case 'heal_skipped': return { ...base, tone: 'info', title: `Repair skipped: ${e.system}`, detail: e.detail || '' };
    case 'rolled_back': return { ...base, tone: 'info', title: `Rolled back ${e.system}`, detail: `Now serving${ver(e)}` };
    case 'schema_adjusted': return { ...base, tone: 'info', title: `Input rules adjusted: ${e.tool}`, detail: 'Loosened to accept real example values' };
    default: return null;
  }
}

// These events change what is published, so the operation list and version history should reload.
export const needsRefresh = (e) => ['published', 'heal_saved', 'rolled_back'].includes(e.kind);

const TRACKED = new Set(['change_detected', 'heal_started', 'heal_saved', 'heal_failed', 'heal_skipped', 'rolled_back', 'published', 'onboard_failed']);

// The latest thing that happened to one system: { state: working | ok | failed | skipped, text, detail } or null.
export function systemStatus(events, system) {
  const last = [...events].reverse().find((e) => e.system === system && TRACKED.has(e.kind));
  if (!last) return null;
  const d = describeEvent(last);
  const state = ['change_detected', 'heal_started'].includes(last.kind) ? 'working'
    : ['heal_failed', 'onboard_failed'].includes(last.kind) ? 'failed'
    : last.kind === 'heal_skipped' ? 'skipped' : 'ok';
  return { state, text: d.title, detail: d.detail };
}

// The backend's reason is 'onboarded' or 'self-heal (<why>)'.
export function reasonLabel(reason = '') {
  if (reason === 'onboarded') return 'First import';
  if (/change_detected/.test(reason)) return 'Repaired after a change';
  if (/manual/.test(reason)) return 'Repaired on request';
  return reason;
}
