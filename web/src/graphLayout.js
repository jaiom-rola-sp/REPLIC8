import { Box, Code2, Database, Globe2, Layers3 } from 'lucide-react';

// Layout for the system graph. It has to stay readable with hundreds of operations:
// - a system with few operations draws each one under it;
// - a system with many draws ONE summary node (counts by ingestion tier) that expands on click;
// - an expanded system draws at most MAX_SHOWN operations in a grid, then a "+N more" node that opens the list.
export const NODE_W = 230, STEP = 250, ROW = 150, GROUP_GAP = 90;
export const INLINE_MAX = 4, MAX_SHOWN = 24, GRID_COLS = 4;

const readsFirst = (a, b) => (a.access === 'write') - (b.access === 'write') || a.tool.localeCompare(b.tool);

function tierSummary(ops) {
  const counts = {};
  for (const o of ops) counts[o.tier] = (counts[o.tier] || 0) + 1;
  const parts = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([tier, n]) => `${tier} ${n}`);
  const writes = ops.filter((o) => o.access === 'write').length;
  return parts.join(' · ') + (writes ? ` · ${writes} write (off)` : '');
}

// One column per system, with the room its children need.
export function columns(operations, expanded = new Set()) {
  const names = [...new Set(operations.map((o) => o.tool.split('.')[0]))];
  let cursor = 0;
  return names.map((name) => {
    const ops = operations.filter((o) => o.tool.startsWith(name + '.')).sort(readsFirst);
    const many = ops.length > INLINE_MAX;
    const open = many && expanded.has(name);
    const shown = open ? ops.slice(0, MAX_SHOWN) : many ? [] : ops;
    const hidden = open ? ops.length - shown.length : 0;
    const across = open ? Math.min(GRID_COLS, shown.length + (hidden ? 1 : 0)) : many ? 1 : ops.length;
    const width = across * STEP - (STEP - NODE_W);
    const col = { name, ops, many, open, shown, hidden, across, left: cursor, center: cursor + width / 2, right: cursor + width };
    cursor += width + GROUP_GAP;
    return col;
  });
}

function operationNode(op, x, y) {
  return { id: op.tool, type: 'system', position: { x, y }, data: { label: `${op.tool.split('.')[1]}()`, eyebrow: op.access === 'write' ? 'WRITE OPERATION' : 'READ OPERATION', subtitle: `${op.tier} · version ${op.version}`, icon: Code2, kind: 'operation' } };
}

const EDGE = { stroke: '#5f5f5f', strokeWidth: 1 };

// The nodes and edges under one system. `y` is where its children start.
function children(col, y) {
  if (!col.many) {
    return {
      nodes: col.shown.map((op, j) => operationNode(op, col.left + j * STEP, y)),
      edges: col.shown.map((op) => ({ id: `op-${op.tool}`, source: col.name, target: op.tool, style: EDGE })),
    };
  }
  const group = { id: `group:${col.name}`, type: 'system', position: { x: col.center - NODE_W / 2, y }, data: { kind: 'group', system: col.name, label: `${col.ops.length} operations`, eyebrow: col.open ? 'OPERATIONS · SHOWN' : 'OPERATIONS · COLLAPSED', subtitle: tierSummary(col.ops), icon: Layers3, footer: col.open ? 'Click to hide' : `Click to show ${Math.min(col.ops.length, MAX_SHOWN)}` } };
  const nodes = [group];
  const edges = [{ id: `to-group:${col.name}`, source: col.name, target: group.id, style: EDGE }];
  const cell = (k) => ({ x: col.left + (k % col.across) * STEP, y: y + ROW * (1 + Math.floor(k / col.across)) });
  col.shown.forEach((op, k) => {
    const { x, y: cy } = cell(k);
    nodes.push(operationNode(op, x, cy));
    edges.push({ id: `op-${op.tool}`, source: group.id, target: op.tool, style: EDGE });
  });
  if (col.hidden) {
    const { x, y: cy } = cell(col.shown.length);
    nodes.push({ id: `more:${col.name}`, type: 'system', position: { x, y: cy }, data: { kind: 'more', system: col.name, label: `+${col.hidden} more`, eyebrow: 'NOT DRAWN', subtitle: 'The graph shows the first operations only', icon: Code2, footer: 'Open in Operations' } });
    edges.push({ id: `more-edge:${col.name}`, source: group.id, target: `more:${col.name}`, style: EDGE });
  }
  return { nodes, edges };
}

// links: [{ source, target, fields, evidence }] between SYSTEMS (compact, from the gateway).
function linkEdges(links, names) {
  return links.filter((l) => l.source !== l.target && names.includes(l.source) && names.includes(l.target)).map((l) => {
    const fields = l.fields.length > 3 ? `${l.fields.slice(0, 3).join(', ')} +${l.fields.length - 3}` : l.fields.join(', ');
    return { id: `link-${l.source}-${l.target}`, source: l.source, target: l.target, type: 'smoothstep', label: `${fields} · ${l.evidence || 'matched'}`, style: { strokeDasharray: '4 5', stroke: '#8a8a8a', strokeWidth: 1.2 }, labelStyle: { fill: '#b5b5b5', fontSize: 10 }, labelBgStyle: { fill: '#0d0d0d', fillOpacity: 1 }, labelBgPadding: [8, 5] };
  });
}

export function graphData(operations, isLive, traceStep, links = [], expanded = new Set()) {
  const cols = columns(operations, expanded);
  const names = cols.map((c) => c.name);
  const middle = cols.length ? (cols[0].left + cols[cols.length - 1].right) / 2 : 0;
  const gx = middle - NODE_W / 2;

  if (isLive) {
    const kids = cols.map((col) => children(col, 470));
    return {
      nodes: [
        { id: 'gateway', type: 'system', position: { x: gx, y: 0 }, data: { label: 'REPLIC8', eyebrow: 'UNIFIED GATEWAY', subtitle: 'Authenticated operation registry', kind: 'gateway', footer: `${operations.length} registered operations` } },
        ...cols.flatMap((col, i) => [
          { id: col.name, type: 'system', position: { x: col.center - NODE_W / 2, y: 240 }, data: { label: col.name, eyebrow: 'REGISTERED NAMESPACE', subtitle: `${col.ops.length} operations`, icon: Database, footer: 'Select to inspect' } },
          ...kids[i].nodes,
        ]),
      ],
      edges: [
        ...cols.map((col) => ({ id: `gateway-${col.name}`, source: 'gateway', target: col.name, animated: true, style: { stroke: '#777777', strokeWidth: 1.1 } })),
        ...kids.flatMap((k) => k.edges),
        ...linkEdges(links, names),
      ],
    };
  }

  const count = (name) => cols.find((c) => c.name === name)?.ops.length ?? 0;
  const demo = {
    maintenance: { label: 'Field services', eyebrow: 'LEGACY SYSTEM · B', subtitle: 'Maintenance & equipment', icon: Database, footer: `${count('maintenance')} operations · parsed`, active: traceStep === 1 },
    inventory: { label: 'Industrial logistics', eyebrow: 'LEGACY SYSTEM · C', subtitle: 'Inventory & delivery', icon: Box, footer: `${count('inventory')} operations · mixed tiers`, active: traceStep === 2 },
  };
  const kids = cols.map((col) => children(col, 584));
  return {
    nodes: [
      { id: 'parent', type: 'system', position: { x: gx, y: 0 }, data: { label: 'Modern platform', eyebrow: 'PARENT COMPANY · A', subtitle: 'Your agents. One connection.', icon: Globe2, active: traceStep === 0 } },
      { id: 'gateway', type: 'system', position: { x: gx, y: 176 }, data: { label: 'REPLIC8', eyebrow: 'THE CONNECTION LAYER', subtitle: 'One gateway. Every system.', kind: 'gateway', footer: 'REST API + MCP', active: traceStep >= 0 } },
      ...cols.flatMap((col, i) => [
        { id: col.name, type: 'system', position: { x: col.center - NODE_W / 2, y: 390 }, data: demo[col.name] || { label: col.name, eyebrow: 'LEGACY SYSTEM', subtitle: `${col.ops.length} operations`, icon: Database } },
        ...kids[i].nodes,
      ]),
    ],
    edges: [
      { id: 'a-g', source: 'parent', target: 'gateway' },
      ...cols.map((col) => ({ id: col.name === 'maintenance' ? 'g-b' : col.name === 'inventory' ? 'g-c' : `g-${col.name}`, source: 'gateway', target: col.name })),
      ...kids.flatMap((k) => k.edges),
      { id: 'schema-link', source: 'maintenance', target: 'inventory', type: 'smoothstep', label: 'part_id · demo schema match', style: { strokeDasharray: '4 5', stroke: '#5b5b5b', strokeWidth: 1 }, labelStyle: { fill: '#9a9a9a', fontSize: 10 }, labelBgStyle: { fill: '#0d0d0d', fillOpacity: 1 }, labelBgPadding: [8, 5] },
    ].map((e) => ({ ...e, animated: traceStep >= 0 || ['g-b', 'g-c'].includes(e.id), style: { stroke: '#7c7c7c', strokeWidth: 1.2, ...e.style } })),
  };
}
