import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkWorkspaceToken, createWorkspace, describeWorkspace, normalizeGateway, workspaceLabel } from './workspace.js';

const TOKEN = 'r8w_' + 'A'.repeat(43);

test('gateway addresses are normalized', () => {
  assert.equal(normalizeGateway(' https://replic8.tail1.ts.net/ '), 'https://replic8.tail1.ts.net');
  assert.equal(normalizeGateway('/gateway'), '/gateway');
  assert.throws(() => normalizeGateway('replic8.ts.net'), /gateway address/);
  assert.throws(() => normalizeGateway('ftp://x.example'), /HTTP or HTTPS/);
});

test('workspace tokens are recognised', () => {
  assert.equal(checkWorkspaceToken(TOKEN), '');
  assert.match(checkWorkspaceToken('t'.repeat(48)), /start with r8w_/);
  assert.match(checkWorkspaceToken(''), /start with r8w_/);
});

test('sidebar label', () => {
  assert.equal(workspaceLabel(null, false).title, 'No workspace open');
  assert.equal(workspaceLabel({ kind: 'workspace', id: 'abc', name: 'Judges demo' }, true).title, 'Judges demo');
  assert.equal(workspaceLabel({ kind: 'workspace', id: 'abc', name: '' }, true).title, 'Workspace abc');
  assert.equal(workspaceLabel({ kind: 'default' }, true).title, 'Shared gateway');
});

const reply = (status, body) => async (url, init) => ({ status, ok: status >= 200 && status < 300, json: async () => body, url, init });

test('creating a workspace sends the admin token and returns the new token', async () => {
  let seen;
  const ws = await createWorkspace('https://g.example', 'ADMIN', 'Demo', async (url, init) => { seen = { url, init }; return reply(201, { id: 'a1', token: TOKEN })(); });
  assert.equal(ws.token, TOKEN);
  assert.equal(seen.url, 'https://g.example/v1/workspaces');
  assert.equal(seen.init.headers.Authorization, 'Bearer ADMIN');
  assert.deepEqual(JSON.parse(seen.init.body), { name: 'Demo' });
});

test('creating a workspace explains failures', async () => {
  await assert.rejects(createWorkspace('https://g', 'x', '', reply(401, {})), /admin token/);
  await assert.rejects(createWorkspace('https://g', 'x', '', reply(503, {})), /not have workspaces/);
  await assert.rejects(createWorkspace('https://g', 'x', '', reply(201, { token: 'nope' })), /returned 201/);
});

test('describing a workspace tolerates older gateways', async () => {
  assert.deepEqual(await describeWorkspace('https://g', TOKEN, reply(200, { kind: 'workspace', id: 'a1' })), { kind: 'workspace', id: 'a1' });
  assert.equal(await describeWorkspace('https://g', TOKEN, reply(404, {})), null);
  assert.equal(await describeWorkspace('https://g', TOKEN, async () => { throw new Error('down'); }), null);
});
