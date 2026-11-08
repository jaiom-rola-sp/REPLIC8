// Builds the Try it form from an operation's input schema, checks the values the way the gateway will,
// and turns a failed call into plain words. The gateway checks everything again; this just saves a round trip.

// One field per top-level property, or null when the schema has anything this form cannot draw
// (nested objects, arrays): the caller then falls back to a JSON box.
export function fieldsFor(schema) {
  const props = schema && typeof schema === 'object' ? schema.properties : null;
  if (!props || typeof props !== 'object' || Array.isArray(props)) return null;
  const required = new Set(Array.isArray(schema.required) ? schema.required : []);
  const fields = [];
  for (const [name, spec] of Object.entries(props)) {
    if (!spec || typeof spec !== 'object') return null;
    const type = Array.isArray(spec.type) ? spec.type.find((t) => t !== 'null') : spec.type;
    let kind;
    if (Array.isArray(spec.enum) && spec.enum.every((v) => typeof v === 'string')) kind = 'choice';
    else if (type === 'string') kind = 'text';
    else if (type === 'integer') kind = 'integer';
    else if (type === 'number') kind = 'number';
    else if (type === 'boolean') kind = 'boolean';
    else return null;
    fields.push({ name, kind, required: required.has(name), maxLength: spec.maxLength, pattern: spec.pattern, choices: spec.enum, description: spec.description });
  }
  return fields;
}

// { input } ready to send, or { error } in plain words.
export function buildInput(fields, values) {
  const input = {};
  for (const f of fields) {
    const raw = values[f.name];
    if (f.kind === 'boolean') {
      if (raw === undefined && !f.required) continue;
      input[f.name] = raw === true || raw === 'true';
      continue;
    }
    if (raw === undefined || raw === '') {
      if (f.required) return { error: `${f.name} is required.` };
      continue;
    }
    if (f.kind === 'integer' || f.kind === 'number') {
      const n = Number(raw);
      if (!Number.isFinite(n) || (f.kind === 'integer' && !Number.isInteger(n))) return { error: `${f.name} must be a ${f.kind === 'integer' ? 'whole number' : 'number'}.` };
      input[f.name] = n;
      continue;
    }
    const text = String(raw);
    if (f.maxLength && text.length > f.maxLength) return { error: `${f.name} can be at most ${f.maxLength} characters.` };
    if (f.kind === 'choice' && !f.choices.includes(text)) return { error: `Pick one of the listed values for ${f.name}.` };
    if (f.pattern) {
      try { if (!new RegExp(f.pattern).test(text)) return { error: `${f.name} does not match the allowed format.` }; } catch { /* a pattern this browser can't read: the gateway will check it */ }
    }
    input[f.name] = text;
  }
  return { input };
}

export function parseJsonInput(text) {
  try {
    const value = JSON.parse(text || '{}');
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return { error: 'The input must be a JSON object, like {"id": "R-1001"}.' };
    return { input: value };
  } catch { return { error: 'That is not valid JSON.' }; }
}

export function describeFailure(status, detail = '') {
  if (status === 401) return 'The gateway did not accept this token.';
  if (status === 403) return 'This token may not call this tool (it is outside the token\'s scopes, or it is a write operation, which is disabled).';
  if (status === 404) return 'The gateway does not publish this tool.';
  if (status === 413) return 'That input is too large.';
  if (status === 422) return `The gateway rejected the input${detail ? `: ${String(detail).slice(0, 200)}` : '.'}`;
  if (status === 429) return 'Too many requests. Wait a moment and try again.';
  if (status >= 500) return 'The legacy program or the gateway failed. Check the activity feed.';
  return `The gateway returned ${status}.`;
}
