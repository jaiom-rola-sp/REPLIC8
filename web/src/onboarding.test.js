// Run with: node --test src/onboarding.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { checkGithubUrl, checkSystemName, progress } from './onboarding.js';

test('accepts public GitHub repo URLs and normalizes them', () => {
  assert.equal(checkGithubUrl('https://github.com/jaiom-rola-sp/REPLIC8').url, 'https://github.com/jaiom-rola-sp/REPLIC8');
  assert.equal(checkGithubUrl('  https://github.com/a/b.git ').url, 'https://github.com/a/b');
});

test('rejects anything the backend would refuse', () => {
  for (const bad of ['http://github.com/a/b', 'https://gitlab.com/a/b', 'https://github.com/a', 'https://github.com/a/b/tree/main',
    'https://user@github.com/a/b', 'https://github.com:444/a/b', 'https://github.com/a/b?x=1', 'https://github.com/a/..', 'not a url']) {
    assert.ok(checkGithubUrl(bad).error, bad);
  }
});

test('system names follow the backend pattern', () => {
  assert.equal(checkSystemName('maintenance'), '');
  assert.equal(checkSystemName('inv_2'), '');
  for (const bad of ['', 'Maintenance', '2fast', 'has space', 'a'.repeat(33)]) assert.ok(checkSystemName(bad), bad);
});

const ev = (id, kind, extra = {}) => ({ id, kind, system: 'demo', tool: '', detail: '', version: null, ...extra });

test('progress follows the stage events and ignores other systems and older runs', () => {
  const events = [
    ev(1, 'onboard_started'), ev(2, 'onboard_stage', { detail: 'fetch' }), // an older run
    ev(10, 'onboard_started'), ev(11, 'onboard_stage', { detail: 'fetch' }), ev(12, 'onboard_stage', { detail: 'detect' }),
    ev(13, 'onboard_stage', { detail: 'build', system: 'other' }),
  ];
  const p = progress(events, 'demo', 5);
  assert.equal(p.status, 'running');
  assert.deepEqual(p.stages.map((s) => s.state), ['done', 'active', 'pending', 'pending', 'pending', 'pending', 'pending']);
  assert.equal(p.lastId, 13);
});

test('a failure marks the stage it stopped on and carries the reason', () => {
  const p = progress([ev(1, 'onboard_started'), ev(2, 'onboard_stage', { detail: 'fetch' }), ev(3, 'onboard_stage', { detail: 'detect' }),
    ev(4, 'onboard_failed', { detail: 'no supported language yet (found: java)' })], 'demo');
  assert.equal(p.status, 'failed');
  assert.equal(p.stages[1].state, 'failed');
  assert.equal(p.stages[0].state, 'done');
  assert.match(p.reason, /no supported language/);
});

test('a published import marks every stage done and reports counts', () => {
  const p = progress([ev(1, 'onboard_started'), ev(2, 'onboard_stage', { detail: 'publish' }),
    ev(3, 'published', { version: 1, operations: 2, rejected: 1 })], 'demo');
  assert.equal(p.status, 'published');
  assert.ok(p.stages.every((s) => s.state === 'done'));
  assert.deepEqual([p.operations, p.rejected, p.version], [2, 1, 1]);
});

test('before the first event the import is just starting', () => {
  assert.equal(progress([], 'demo').status, 'starting');
});

import { parseKnownValues } from './onboarding.js';

test('known values parse into field -> list and allow repeats and blank lines', () => {
  assert.deepEqual(parseKnownValues('').values, {});
  assert.deepEqual(parseKnownValues('request_id=R-1001\n\n well_id = W-17 \nrequest_id=R-1002').values,
    { request_id: ['R-1001', 'R-1002'], well_id: ['W-17'] });
});

test('known values reject what the backend would refuse, naming the line', () => {
  for (const bad of ['R-1001', 'Request_Id=R-1', 'request_id=', 'request_id=a=b', 'request_id=' + 'x'.repeat(65), '=x',
    'request_id=1\nrequest_id=2\nrequest_id=3\nrequest_id=4\nrequest_id=5\nrequest_id=6']) {
    assert.match(parseKnownValues(bad).error, /Line \d|at most/, bad);
  }
  assert.match(parseKnownValues('ok=1\nnope').error, /Line 2/);
});
