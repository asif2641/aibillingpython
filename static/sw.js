/**
 * aibilling Service Worker
 * ========================
 * Provides offline caching, network-first strategy for navigation,
 * and stale-while-revalidate for static assets & CDNs.
 */

const CACHE_NAME = 'aibilling-v1';

// Static assets to pre-cache on service worker installation
const PRECACHE_ASSETS = [
  '/',
  '/manifest.json',
  '/offline/',
  '/en/offline/',
  '/ur/offline/',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon.svg',
  'https://cdn.tailwindcss.com',
  'https://unpkg.com/htmx.org@1.9.12',
  'https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+Arabic:wght@400;500;600;700&display=swap'
];

// Install Event — precache core offline shell & static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // Use individual fetches with error catches so one unreachable CDN won't abort SW installation
      await Promise.all(
        PRECACHE_ASSETS.map((url) =>
          cache.add(url).catch((err) => {
            console.warn(`[ServiceWorker] Precache skipped for ${url}:`, err);
          })
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// Activate Event — cleanup old caches & take control immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log(`[ServiceWorker] Removing obsolete cache: ${cache}`);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event — routing and caching strategies
self.addEventListener('fetch', (event) => {
  // Only handle HTTP/HTTPS GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  const url = new URL(event.request.url);

  // Strategy 1: HTML Navigation Requests (Network-First with Offline Fallback)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          // If network succeeded, optionally cache localized offline pages or current page
          return networkResponse;
        })
        .catch(async () => {
          // Network failed — fallback to cached offline shell
          const cache = await caches.open(CACHE_NAME);
          
          // Determine best language match if URL contains /ur/
          if (url.pathname.startsWith('/ur/')) {
            const urOffline = await cache.match('/ur/offline/');
            if (urOffline) return urOffline;
          }

          const enOffline = await cache.match('/en/offline/');
          if (enOffline) return enOffline;

          const defaultOffline = await cache.match('/offline/');
          if (defaultOffline) return defaultOffline;

          // Ultimate fallback if cache is somehow missing
          return new Response(
            `<!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>You're Offline — aibilling</title>
              <style>
                body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; text-align: center; }
                .card { background: #1e293b; padding: 2rem; border-radius: 1rem; max-width: 420px; border: 1px solid #334155; }
                h1 { margin-top: 0; color: #60a5fa; }
                button { background: #4f46e5; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 0.5rem; cursor: pointer; font-size: 1rem; font-weight: 600; margin-top: 1rem; }
              </style>
            </head>
            <body>
              <div class="card">
                <h1>You're Offline / آپ آف لائن ہیں</h1>
                <p>No internet connection detected. Please check your network and retry.</p>
                <p dir="rtl">انٹرنیٹ کنکشن دستیاب نہیں ہے۔ براے مہربانی نیٹ ورک چیک کریں۔</p>
                <button onclick="window.location.reload()">Retry Connection / دوبارہ کوشش کریں</button>
              </div>
            </body>
            </html>`,
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        })
    );
    return;
  }

  // Strategy 2: Static Assets & CDNs (Stale-While-Revalidate / Cache-First)
  const isStaticAsset = (
    url.pathname.startsWith('/static/') ||
    url.hostname.includes('cdn.tailwindcss.com') ||
    url.hostname.includes('unpkg.com') ||
    url.hostname.includes('jsdelivr.net') ||
    url.hostname.includes('fonts.googleapis.com') ||
    url.hostname.includes('fonts.gstatic.com') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.jpg') ||
    url.pathname.endsWith('.jpeg') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.js')
  );

  if (isStaticAsset) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((cachedResponse) => {
          const fetchPromise = fetch(event.request)
            .then((networkResponse) => {
              if (networkResponse && (networkResponse.status === 200 || networkResponse.type === 'opaque')) {
                cache.put(event.request, networkResponse.clone());
              }
              return networkResponse;
            })
            .catch((err) => {
              if (cachedResponse) {
                return cachedResponse;
              }
              throw err;
            });

          return cachedResponse || fetchPromise;
        });
      })
    );
    return;
  }

  // Strategy 3: Standard fetch for everything else (API calls, sync endpoints)
  event.respondWith(
    fetch(event.request).catch(async (err) => {
      const cached = await caches.match(event.request);
      if (cached) return cached;
      throw err;
    })
  );
});
