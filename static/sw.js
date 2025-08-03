/**
 * Lightweight Service Worker for local Raspberry Pi deployment
 * - Version bump to control cache invalidation
 * - Precache a few essentials
 * - Stale-while-revalidate for static assets
 */
const SW_VERSION = 'v1.0.0';
const STATIC_CACHE = `static-cache-${SW_VERSION}`;
const PRECACHE_URLS = [
  '/', // shell (served by Flask)
  '/favicon.ico',
  '/static/enhanced_forecast.js' // keep simple, no bundling
];

// Install: precache essentials (best-effort)
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS).catch(() => undefined);
    })
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('static-cache-') && k !== STATIC_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch strategy:
// - For same-origin static assets under /static: stale-while-revalidate
// - For others: network-first with cache fallback (offline)
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle GET requests
  if (req.method !== 'GET') return;

  // Same-origin static assets strategy
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  // For root and simple HTML navigations, try network first
  if (req.mode === 'navigate') {
    event.respondWith(networkFirst(req));
    return;
  }

  // Default: pass-through
});

// Push notifications
self.addEventListener('push', function(event) {
  try {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'Weather Alert';
    const body = data.body || 'New notification';
    event.waitUntil(
      self.registration.showNotification(title, { body })
    );
  } catch {
    // ignore malformed payloads
  }
});

// Helpers
async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  const networkPromise = fetch(request).then((res) => {
    if (res && res.status === 200) {
      cache.put(request, res.clone());
    }
    return res;
  }).catch(() => cached);
  return cached || networkPromise;
}

async function networkFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  try {
    const fresh = await fetch(request);
    if (fresh && fresh.status === 200) {
      cache.put(request, fresh.clone());
    }
    return fresh;
  } catch {
    const cached = await cache.match(request);
    return cached || new Response('<h1>Offline</h1>', {
      headers: { 'Content-Type': 'text/html' },
      status: 200
    });
  }
}
