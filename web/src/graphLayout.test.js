// Run with: node --test src/graphLayout.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { graphData, columns, INLINE_MAX, MAX_SHOWN, NODE_W } from './graphLayout.js';

// 11 systems with 25 operations each, plus one with 120: 395 operations in all.
const make = (system, n, tier = 'parsed') => Array.from({ length: n }, (_, i) => ({
  tool: `${system}.op_${String(i).padStart(3, '0')}`, tier, version: 1, access: i % 10 === 9 ? 'write' : 'read' }));
const SYSTEMS = [...Array.from({ length: 11 }, (_, i) => `sys${String(i).padStart(2, '0')}`), 'huge'];
const BIG = SYSTEMS.flatMap((s) => make(s, s === 'huge' ? 120 : 25));

const HEIGHT = 125; // a node is at most ~116px tall
const overlaps = (a, b) => Math.abs(a.position.x - b.position.x) < NODE_W && Math.abs(a.position.y - b.position.y) < HEIGHT;
function assertSound(graph) {
  const ids = graph.nodes.map((n) => n.id);
  assert.equal(new Set(ids).size, ids.length, 'node ids are unique');
  assert.equal(new Set(graph.edges.map((e) => e.id)).size, graph.edges.length, 'edge ids are unique');
  for (const e of graph.edges) assert.ok(ids.includes(e.source) && ids.includes(e.target), `edge ${e.id} points at real nodes`);
  for (let i = 0; i < graph.nodes.length; i++) for (let j = i + 1; j < graph.nodes.length; j++) assert.ok(!overlaps(graph.nodes[i], graph.nodes[j]), `${graph.nodes[i].id} overlaps ${graph.nodes[j].id}`);
}

test('hundreds of operations collapse to one summary node per large system', () => {
  const g = graphData(BIG, true, -1, [], new Set());
  assert.equal(g.nodes.length, 1 + 12 + 12);                     // gateway + systems + one group each
  assert.equal(g.nodes.filter((n) => n.data.kind === 'operation').length, 0);
  const huge = g.nodes.find((n) => n.id === 'group:huge');
  assert.equal(huge.data.label, '120 operations');
  assert.match(huge.data.subtitle, /parsed 120 · 12 write \(off\)/);
  assertSound(g);
});

test('a small system still draws every operation inline', () => {
  const ops = [...make('a', INLINE_MAX), ...make('b', 2)];
  const g = graphData(ops, true, -1, [], new Set());
  assert.equal(g.nodes.filter((n) => n.data.kind === 'operation').length, INLINE_MAX + 2);
  assert.equal(g.nodes.filter((n) => n.data.kind === 'group').length, 0);
  assertSound(g);
});

test('expanding a system draws at most MAX_SHOWN operations, then a +N more node', () => {
  const g = graphData(BIG, true, -1, [], new Set(['huge']));
  const shown = g.nodes.filter((n) => n.data.kind === 'operation' && n.id.startsWith('huge.'));
  assert.equal(shown.length, MAX_SHOWN);
  const more = g.nodes.find((n) => n.id === 'more:huge');
  assert.equal(more.data.label, `+${120 - MAX_SHOWN} more`);
  assert.equal(more.data.system, 'huge');
  assertSound(g);
});

test('reads are drawn before writes', () => {
  const g = graphData(BIG, true, -1, [], new Set(['sys00']));
  const writes = g.nodes.filter((n) => n.id.startsWith('sys00.') && n.data.eyebrow === 'WRITE OPERATION');
  const lastRead = Math.max(...g.nodes.filter((n) => n.id.startsWith('sys00.') && n.data.eyebrow === 'READ OPERATION').map((n) => n.position.y));
  assert.ok(writes.every((w) => w.position.y >= lastRead));
});

test('every system expanded at once is still bounded and overlap-free', () => {
  const g = graphData(BIG, true, -1, [], new Set(SYSTEMS));
  assert.ok(g.nodes.length <= 1 + 12 + 12 + 12 * (MAX_SHOWN + 1));
  assertSound(g);
});

test('links between systems become one labelled edge, and unknown systems are ignored', () => {
  const links = [
    { source: 'sys00', target: 'sys01', fields: ['id', 'part_id', 'site', 'region'], evidence: 'recorded' },
    { source: 'sys00', target: 'ghost', fields: ['id'], evidence: 'schema' },
    { source: 'sys00', target: 'sys00', fields: ['id'], evidence: 'schema' },
  ];
  const g = graphData(BIG, true, -1, links, new Set());
  const dashed = g.edges.filter((e) => e.id.startsWith('link-'));
  assert.equal(dashed.length, 1);
  assert.equal(dashed[0].label, 'id, part_id, site +1 · recorded');
});

test('demo mode keeps its two-per-system story', () => {
  const demo = ['maintenance.get_request', 'maintenance.list_equipment', 'inventory.check_stock', 'inventory.delivery_options']
    .map((tool) => ({ tool, tier: 'parsed', version: 1, access: 'read' }));
  const g = graphData(demo, false, -1);
  assert.equal(g.nodes.filter((n) => n.data.kind === 'operation').length, 4);
  assert.ok(g.edges.some((e) => e.id === 'schema-link'));
  assertSound(g);
  assert.equal(columns(demo).length, 2);
});
