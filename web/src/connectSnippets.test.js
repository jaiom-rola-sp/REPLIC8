// Run with: node --test src/connectSnippets.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { ADDRESS_PLACEHOLDER, TOKEN_PLACEHOLDER, gatewayAddress, isLocalAddress, sampleCall, snippets } from './connectSnippets.js';

test('a relative gateway path lives under this site; an absolute one is kept without a trailing slash', () => {
  assert.equal(gatewayAddress('/gateway', 'http://127.0.0.1:5173'), 'http://127.0.0.1:5173/gateway');
  assert.equal(gatewayAddress('https://api.example.com/', 'http://x'), 'https://api.example.com');
  assert.equal(gatewayAddress('', 'http://x'), ADDRESS_PLACEHOLDER);
});

test('local addresses are recognised', () => {
  for (const a of ['http://127.0.0.1:8000', 'http://localhost:5173/gateway', 'https://[::1]:8000']) assert.ok(isLocalAddress(a), a);
  for (const a of ['https://replic8.eastus.cloudapp.azure.com', 'https://127.0.0.1.evil.com', ADDRESS_PLACEHOLDER]) assert.ok(!isLocalAddress(a), a);
});

test('the sample call uses the first operation that has inputs', () => {
  const ops = [{ tool: 'a.none', input_schema: { properties: {} } }, { tool: 'b.get', input_schema: { properties: { id: { type: 'string' }, n: { type: 'integer' }, ok: { type: 'boolean' } } } }];
  assert.deepEqual(sampleCall(ops), { tool: 'b.get', input: { id: 'VALUE', n: 0, ok: true } });
  assert.equal(sampleCall([]).tool, 'system.tool_name');
});

test('snippets point at the right routes and only ever contain the placeholder token', () => {
  const s = snippets('https://gw.example.com', { tool: 'maintenance.get_request', input: { request_id: 'VALUE' } });
  assert.equal(s.claude, `claude mcp add --transport http replic8 https://gw.example.com/mcp --header "Authorization: Bearer ${TOKEN_PLACEHOLDER}"`);
  const config = JSON.parse(s.config);
  assert.equal(config.mcpServers.replic8.url, 'https://gw.example.com/mcp');
  assert.equal(config.mcpServers.replic8.headers.Authorization, `Bearer ${TOKEN_PLACEHOLDER}`);
  assert.match(s.curlList, /\/v1\/operations/);
  assert.match(s.curlCall, /\/v1\/operations\/maintenance\.get_request/);
  const body = s.curlCall.match(/-d '(.*)'$/)[1];
  assert.deepEqual(JSON.parse(body), { input: { request_id: 'VALUE' } });
  for (const text of Object.values(s)) assert.ok(!/Bearer (?!YOUR_GATEWAY_TOKEN)/.test(text), 'no real token in a snippet');
});
