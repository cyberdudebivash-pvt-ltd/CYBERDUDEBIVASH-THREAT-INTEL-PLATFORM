'use strict';
/**
 * Shared local static-file HTTP server for render-test/verify_*.js harnesses.
 *
 * Consolidates the startStaticServer() previously duplicated, near-identically,
 * across 16 of this directory's 18 files (issue #318 -- Single Source of Truth
 * at the test-tooling layer; the remaining 2, verify_eicc_zero_fabrication_states.js
 * and verify_stale_service_worker_recovery.js, define their own startServer(root)
 * with request-interception/mocking logic this generic server doesn't need to
 * cover, so they're correctly left as-is).
 *
 * Behavior matches the safer of the two prior variants: a path-traversal check
 * via path.relative() rather than the weaker `filePath.startsWith(root)` some
 * call sites used (a bare startsWith is spoofable by a sibling directory
 * sharing the same string prefix). No existing test exercises the difference
 * between the two checks, so this is a strict tightening, not a behavior
 * change for any passing check.
 */
const path = require('path');
const http = require('http');
const fs = require('fs');

/**
 * @param {string} root - absolute directory to serve.
 * @param {number} port - port to listen on (127.0.0.1 only).
 * @param {Record<string,string>} mime - extension-to-content-type map; callers keep their own (some serve .md/.yaml/.xml/.mp4 fixtures this base set doesn't need to know about).
 * @returns {Promise<import('http').Server>}
 */
function startStaticServer(root, port, mime) {
  const server = http.createServer((req, res) => {
    let urlPath = decodeURIComponent(req.url.split('?')[0].split('#')[0]);
    if (urlPath.endsWith('/')) urlPath += 'index.html';
    const filePath = path.join(root, urlPath);
    const rel = path.relative(root, filePath);
    if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) { res.writeHead(403); res.end(); return; }
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end('Not found'); return; }
      const ext = path.extname(filePath);
      res.writeHead(200, { 'Content-Type': mime[ext] || 'application/octet-stream' });
      res.end(data);
    });
  });
  return new Promise((resolve) => server.listen(port, '127.0.0.1', () => resolve(server)));
}

module.exports = { startStaticServer };
