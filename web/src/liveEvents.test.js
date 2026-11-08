// Run with: node --test src/liveEvents.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { describeEvent, needsRefresh, systemStatus } from './liveEvents.js';

const ev = (id, kind, extra = {}) => ({ id, kind, system: 'maintenance', tool: '', detail: '', version: null, time: '2026-11-07T21:00:00+00:00', ...extra });

test('each backend event kind that matters has a plain entry', () => {
  const cases = {
    published: /Published maintenance v2/, onboard_failed: /Import failed/, change_detected: /Change detected/, heal_started: /Repair started/,
    heal_saved: /Repair saved: maintenance v2/, heal_failed: /Repair failed/, heal_skipped: /Repair skipped/, rolled_back: /Rolled back maintenance/,
    contract_failed: /Contract test failed/, schema_adjusted: /Input rules adjusted/, onboard_started: /Import started/, call_failed: /A call failed/,
  };
  for (const [kind, title] of Object.entries(cases)) assert.match(describeEvent(ev(1, kind, { version: 2, tool: 'maintenance.get_request' })).title, title, kind);
});

test('noisy events are not listed', () => {
  assert.equal(describeEvent(ev(1, 'onboard_stage', { detail: 'fetch' })), null);
  assert.equal(describeEvent(ev(2, 'onboarded', { version: 1 })), null);
  assert.equal(describeEvent(ev(3, 'something_new')), null);
});

test('published reports its counts, and a bad timestamp does not break the entry', () => {
  assert.equal(describeEvent(ev(1, 'published', { operations: 2, rejected: 1 })).detail, '2 operations live, 1 rejected');
  assert.equal(describeEvent(ev(2, 'heal_saved', { time: 'not a date' })).time, '');
});

test('only events that change what is published trigger a reload', () => {
  for (const k of ['published', 'heal_saved', 'rolled_back']) assert.ok(needsRefresh(ev(1, k)), k);
  for (const k of ['heal_started', 'change_detected', 'heal_failed', 'onboard_stage']) assert.ok(!needsRefresh(ev(1, k)), k);
});

test('system status follows the latest event for that system only', () => {
  const log = [ev(1, 'published', { version: 1 }), ev(2, 'change_detected', { version: 1 }), ev(3, 'heal_started', { version: 1 }),
    ev(4, 'heal_failed', { system: 'inventory', detail: 'x' })];
  assert.equal(systemStatus(log, 'maintenance').state, 'working');
  assert.equal(systemStatus(log, 'inventory').state, 'failed');
  assert.equal(systemStatus([...log, ev(5, 'heal_saved', { version: 2 })], 'maintenance').state, 'ok');
  assert.equal(systemStatus([...log, ev(6, 'heal_skipped', { detail: 'legacy code unchanged' })], 'maintenance').state, 'skipped');
  assert.equal(systemStatus(log, 'nothing'), null);
});

import { reasonLabel } from './liveEvents.js';

test('version reasons read as plain words', () => {
  assert.equal(reasonLabel('onboarded'), 'First import');
  assert.equal(reasonLabel('self-heal (change_detected)'), 'Repaired after a change');
  assert.equal(reasonLabel('self-heal (manual)'), 'Repaired on request');
  assert.equal(reasonLabel('something else'), 'something else');
});
