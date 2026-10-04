import test from 'node:test';
import assert from 'node:assert/strict';

import {
  REQUEST_ID_RE,
  resolveRequestId,
  withRequestId,
  withoutRequestId,
} from '../request-id.js';

test('accepts only bounded log-safe caller request IDs', () => {
  const accepted = ['abc', 'req-123', 'SOC.case:42', 'a'.repeat(128)];
  for (const value of accepted) {
    const req = new Request('https://intel.cyberdudebivash.com/api/health', {
      headers: { 'X-Request-ID': value },
    });
    assert.equal(resolveRequestId(req), value);
    assert.equal(REQUEST_ID_RE.test(value), true);
  }

  const rejected = [
    '',
    ' has-space',
    'contains space',
    'line\nbreak',
    '<script>',
    'a'.repeat(129),
  ];
  for (const value of rejected) {
    const req = new Request('https://intel.cyberdudebivash.com/api/health', {
      headers: value ? { 'X-Request-ID': value } : {},
    });
    const id = resolveRequestId(req);
    assert.notEqual(id, value);
    assert.match(id, /^sentinel-apex-/);
    assert.equal(REQUEST_ID_RE.test(id), true);
  }
});

test('response correlation is per-request and removable before shared caching', async () => {
  const base = new Response('ok', {
    status: 200,
    headers: { 'Cache-Control': 'public, max-age=300' },
  });
  const correlated = withRequestId(base, 'req-one');
  assert.equal(correlated.headers.get('X-Request-ID'), 'req-one');
  assert.equal(await correlated.clone().text(), 'ok');

  const cacheCopy = withoutRequestId(correlated);
  assert.equal(cacheCopy.headers.get('X-Request-ID'), null);
  assert.equal(cacheCopy.headers.get('Cache-Control'), 'public, max-age=300');
});
