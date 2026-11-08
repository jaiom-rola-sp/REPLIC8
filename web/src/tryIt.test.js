// Run with: node --test src/tryIt.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildInput, describeFailure, fieldsFor, parseJsonInput } from './tryIt.js';

const schema = { type: 'object', required: ['request_id'], properties: {
  request_id: { type: 'string', maxLength: 8 }, limit: { type: 'integer' }, ratio: { type: 'number' }, active: { type: 'boolean' },
  site: { type: 'string', enum: ['PERMIAN', 'EAGLEFORD'] } } };

test('simple schemas become one field each; anything nested falls back to a JSON box', () => {
  const f = fieldsFor(schema);
  assert.deepEqual(f.map((x) => [x.name, x.kind, x.required]), [['request_id', 'text', true], ['limit', 'integer', false], ['ratio', 'number', false], ['active', 'boolean', false], ['site', 'choice', false]]);
  assert.equal(fieldsFor({ properties: { a: { type: 'object' } } }), null);
  assert.equal(fieldsFor({ properties: { a: { type: 'array', items: { type: 'string' } } } }), null);
  assert.equal(fieldsFor(null), null);
  assert.deepEqual(fieldsFor({ type: 'object', properties: {} }), []);
});

test('values are converted and checked the way the gateway will', () => {
  const f = fieldsFor(schema);
  assert.deepEqual(buildInput(f, { request_id: 'R-1001', limit: '5', ratio: '0.5', active: true, site: 'PERMIAN' }).input, { request_id: 'R-1001', limit: 5, ratio: 0.5, active: true, site: 'PERMIAN' });
  assert.deepEqual(buildInput(f, { request_id: 'R-1001' }).input, { request_id: 'R-1001' });         // optional fields left out
  assert.match(buildInput(f, {}).error, /request_id is required/);
  assert.match(buildInput(f, { request_id: 'x'.repeat(9) }).error, /at most 8/);
  assert.match(buildInput(f, { request_id: 'R-1', limit: '2.5' }).error, /whole number/);
  assert.match(buildInput(f, { request_id: 'R-1', ratio: 'abc' }).error, /must be a number/);
  assert.match(buildInput(f, { request_id: 'R-1', site: 'MARS' }).error, /Pick one/);
});

test('a pattern is applied, and one the browser cannot read is left to the gateway', () => {
  const f = fieldsFor({ required: ['id'], properties: { id: { type: 'string', pattern: '^[A-Z]+$' } } });
  assert.match(buildInput(f, { id: 'abc' }).error, /allowed format/);
  assert.deepEqual(buildInput(f, { id: 'ABC' }).input, { id: 'ABC' });
  const bad = fieldsFor({ properties: { id: { type: 'string', pattern: '(' } } });
  assert.deepEqual(buildInput(bad, { id: 'x' }).input, { id: 'x' });
});

test('the JSON box accepts only an object', () => {
  assert.deepEqual(parseJsonInput('{"id": "R-1"}').input, { id: 'R-1' });
  assert.deepEqual(parseJsonInput('').input, {});
  for (const t of ['[1]', '5', 'null', '{oops']) assert.ok(parseJsonInput(t).error, t);
});

test('failures are explained in plain words', () => {
  assert.match(describeFailure(401), /did not accept this token/);
  assert.match(describeFailure(403), /scopes|write/);
  assert.match(describeFailure(422, 'input does not match the schema: x'), /rejected the input: input does not match/);
  assert.match(describeFailure(429), /Too many/);
  assert.match(describeFailure(500), /activity feed/);
  assert.match(describeFailure(418), /418/);
});
