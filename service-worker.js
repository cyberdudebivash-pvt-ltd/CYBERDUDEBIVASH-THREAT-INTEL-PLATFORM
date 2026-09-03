// CYBERDUDEBIVASH SENTINEL APEX — Service Worker v200.1
// P0 production convergence fix (2026-09-03)
//
// Root cause addressed:
//   The previous v175 worker claimed that dashboard JS was always fresh, but its
//   fetch policy only bypassed cache for /js/engines/*. All other JavaScript and
//   CSS (including api_adapter.js, card_renderer.js and
//   card_renderer_integration.js) fell through to a generic cache-first branch.
//   CACHE_VERSION also remained v175 across later v184-v200 frontend releases.
//   A real browser could therefore receive current v200 HTML while executing an
//   older cached data-loader/renderer, producing the observed split state:
//   API online + v200 shell, but SYNC:LOADING / NO DATA / LIVE 0.
//
// Permanent invariant:
//   * HTML, JS, CSS, JSON, API/data routes and service-worker.js are NETWORK ONLY.
//   * Only the explicit immutable/offline-safe STATIC_ASSETS allow cache-first.
//   * Every SW release changes CACHE_VERSION, purging prior sentinel-apex caches.
//   * No runtime intelligence or executable frontend code may be served stale.

'use strict';

const CACHE_VERSION = 'sentinel-apex-v200.1-live';
const CACHE_NAME = CACHE_VERSION;

const STATIC_ASSETS = Object.freeze([
  '/manifest.json',
  '/assets/sentinel-apex-thumbnail.jpg',
]);
const STATIC_ASSET_SET = new Set(STATIC_ASSETS);

self.addEventListener('install', event => {
  console.log('[SW v200.1] Installing:', CACHE_VERSION);
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      cache.addAll(STATIC_ASSETS).catch(err => {
        console.warn('[SW v200.1] Optional pre-cache failed:', err);
      })
    )
  );
});

self.addEventListener('activate', event => {
  console.log('[SW v200.1] Activating:', CACHE_VERSION);
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key.startsWith('sentinel-apex-') && key !== CACHE_NAME)
          .map(key => {
            console.log('[SW v200.1] Purging stale cache:', key);
            return caches.delete(key);
          })
      ))
      .then(() => self.clients.claim())
      .then(() => self.clients.matchAll({ type: 'window' }))
      .then(clients => {
        clients.forEach(client => client.postMessage({
          type: 'SW_ACTIVATED',
          version: CACHE_VERSION,
        }));
      })
  );
});

self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'GET_VERSION') {
    event.source.postMessage({ type: 'VERSION', version: CACHE_VERSION });
  }
});

function isExplicitStaticAsset(url) {
  return url.origin === self.location.origin && STATIC_ASSET_SET.has(url.pathname);
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // Never cache non-GET requests.
  if (request.method !== 'GET') {
    event.respondWith(fetch(request));
    return;
  }

  // The ONLY cache-first paths are the explicit offline-safe static assets.
  if (isExplicitStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response && response.ok && response.type === 'basic') {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // Production safety boundary: dashboard code and intelligence are network-only.
  // In particular this covers /, *.html, *.js, *.css, *.json, /api/*,
  // /service-worker.js and every future frontend/data route by default.
  event.respondWith(fetch(request, { cache: 'no-store' }));
});
