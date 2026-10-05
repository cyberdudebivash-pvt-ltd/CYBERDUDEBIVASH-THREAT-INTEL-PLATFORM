import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

function read(rel) {
  return fs.readFileSync(new URL(rel, import.meta.url), 'utf8');
}

for (const rel of ['../../../../cve.html', '../../../../lookup.html']) {
  test(`${rel} never recovers or transmits a raw API key from persistent Web Storage`, () => {
    const source = read(rel);
    assert.doesNotMatch(source, /localStorage\.(?:getItem|setItem|removeItem)\([^\n]*cdb_api_key/i);
    assert.doesNotMatch(source, /sessionStorage\.(?:getItem|setItem|removeItem)\([^\n]*(?:api[_-]?key|sentinel_api_key)/i);
    assert.doesNotMatch(source, /["']X-API-Key["']\s*:/i);
  });

  test(`${rel} may reuse only the bounded browser-session JWT and avoids ambient credentials`, () => {
    const source = read(rel);
    assert.match(source, /sessionStorage\.getItem\(["']apex_jwt["']\)/);
    assert.match(source, /Authorization["']?\]\s*=\s*["']Bearer ["']\s*\+\s*token/);
    assert.match(source, /cache:\s*["']no-store["']/);
    assert.match(source, /credentials:\s*["']omit["']/);
  });
}

test('CVE and IOC lookup retain anonymous operation when no bounded JWT exists', () => {
  const cve = read('../../../../cve.html');
  const lookup = read('../../../../lookup.html');
  assert.match(cve, /var headers = \{\};/);
  assert.match(lookup, /var headers = \{\};/);
  assert.doesNotMatch(cve, /Authentication required|Access remains locked/i);
  assert.doesNotMatch(lookup, /Authentication required|Access remains locked/i);
});


test('API-key acquisition page uses only the bounded current session JWT for non-security UI hints', () => {
  const source = read('../../../../get-api-key.html');
  assert.doesNotMatch(source, /localStorage\.getItem\(['"]cdb_jwt/);
  assert.doesNotMatch(source, /sessionStorage\.getItem\(['"]cdb_jwt/);
  assert.match(source, /sessionStorage\.getItem\(['"]apex_jwt['"]\)/);
});
