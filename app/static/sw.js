/* RRM Comptabilité – Service Worker (stabilisation hors ligne v8) */
const CACHE_VERSION = 'rrm-v8-20261018';
const STATIC_CACHE = CACHE_VERSION + '-static';
const PAGE_CACHE = CACHE_VERSION + '-pages';

const PRECACHE_URLS = [
  '/static/manifest.json',
  '/static/favicon.ico',
  '/static/favicon-32.png',
  '/static/favicon-180.png',
  '/static/favicon.png',
  '/static/logo_le_fourmi.jpg',
  '/static/offline.html',
  '/static/js/offline-sync.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => Promise.allSettled(
        PRECACHE_URLS.map((url) => cache.add(url).catch(() => null))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => !k.startsWith(CACHE_VERSION)).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

async function offlinePage() {
  const cached = await caches.match('/static/offline.html', { ignoreSearch: true });
  if (cached) return cached;
  return new Response(
    '<!DOCTYPE html><html lang="fr"><meta charset="utf-8"><title>Hors ligne</title>' +
    '<body style="font-family:system-ui;text-align:center;padding:3rem">' +
    '<h1>Hors ligne</h1><p>Reconnectez-vous pour continuer.</p>' +
    '<p><a href="/journal/new">Brouillard</a> · <a href="/budgets/new">Budgets</a></p></body></html>',
    { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}

function offlineJson() {
  return new Response(
    JSON.stringify({ error: 'offline', message: 'Hors ligne – données non synchronisées' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } }
  );
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Ne pas intercepter les origines externes (sauf CDN Bootstrap déjà en precache)
  if (url.origin !== self.location.origin && !url.hostname.includes('jsdelivr.net')) {
    return;
  }

  // POST / PUT / DELETE : réseau uniquement.
  // Si échec : JSON pour API, page offline pour le reste (évite page Chrome native).
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    event.respondWith(
      fetch(req).catch(() => {
        if (url.pathname.includes('/api/') || (req.headers.get('accept') || '').includes('application/json')) {
          return offlineJson();
        }
        return offlinePage();
      })
    );
    return;
  }

  // Fichiers statiques + CDN
  if (url.pathname.startsWith('/static/') || url.hostname.includes('jsdelivr.net')) {
    event.respondWith((async () => {
      const cached = await caches.match(req, { ignoreSearch: true });
      try {
        const res = await fetch(req);
        if (res && res.ok) {
          const cache = await caches.open(STATIC_CACHE);
          try { cache.put(req, res.clone()); } catch (e) { /* ignore opaque */ }
        }
        return res;
      } catch (e) {
        if (cached) return cached;
        return offlinePage();
      }
    })());
    return;
  }

  // Pages HTML de l'application : network-first, cache en secours
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith((async () => {
      try {
        const res = await fetch(req);
        if (res && res.ok) {
          const cache = await caches.open(PAGE_CACHE);
          try { cache.put(req, res.clone()); } catch (e) { /* ignore */ }
        }
        return res;
      } catch (e) {
        // 1) exact match
        let hit = await caches.match(req, { ignoreSearch: true });
        if (hit) return hit;
        // 2) path only
        hit = await caches.match(url.pathname);
        if (hit) return hit;
        // 3) fallbacks modules connus
        if (url.pathname.startsWith('/budgets')) {
          hit = await caches.match('/budgets/new') || await caches.match('/budgets/');
          if (hit) return hit;
        }
        if (url.pathname.startsWith('/journal')) {
          hit = await caches.match('/journal/new') || await caches.match('/journal/');
          if (hit) return hit;
        }
        return offlinePage();
      }
    })());
  }
});

self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});
