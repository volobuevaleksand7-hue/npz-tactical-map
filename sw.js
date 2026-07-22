/* Топливный фронт РФ — service worker (устанавливаемость + офлайн-оболочка).
   Данные (data/, api/, version.json) и сторонние ресурсы (тайлы, raw.githubusercontent,
   CDN Leaflet) НЕ кэшируются — всегда свежие. Кэшируется только статичная оболочка.
   TODO фаза 2: push-уведомления (Web Push + VAPID) —
     self.addEventListener('push', e => { ... self.registration.showNotification(...) });
     self.addEventListener('notificationclick', e => { ... });
*/
var CACHE = 'npz-shell-v22';   // bump: слой «Склады ВБ/Озон» (app.js + index.html лежат в CRITICAL прекэше)
// CRITICAL должен закешироваться — иначе install падает и старый рабочий SW остаётся (не активируем битую оболочку).
var CRITICAL = ['/', '/index.html', '/styles.css', '/app.js', '/manifest.webmanifest'];
// OPTIONAL — best-effort: 404/сбой одной страницы не рушит установку и не сносит старый кэш.
var OPTIONAL = ['/radar', '/news', '/install', '/help', '/search.css', '/search.js',
                '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png'];
function reload(u) { return new Request(u, { cache: 'reload' }); }

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE)
      .then(function (c) {
        return c.addAll(CRITICAL.map(reload))                 // падение здесь = install reject = старый SW жив
          .then(function () {
            return Promise.all(OPTIONAL.map(function (u) {     // опциональные — по отдельности, ошибку глотаем
              return c.add(reload(u)).catch(function () {});
            }));
          });
      })
      .then(function () { return self.skipWaiting(); })         // только если CRITICAL закеширован
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (keys) { return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); })); })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;                        // сторонние — как есть
  if (/^\/(data|api)\//.test(url.pathname) || url.pathname === '/version.json') return; // всегда свежие

  if (req.mode === 'navigate') {
    // страницы: сеть первой (свежий контент), офлайн — из кэша, иначе главная
    e.respondWith(
      fetch(req).then(function (r) {
        var cp = r.clone(); caches.open(CACHE).then(function (c) { c.put(req, cp); });
        return r;
      }).catch(function () { return caches.match(req).then(function (m) { return m || caches.match('/'); }); })
    );
    return;
  }
  // статика: кэш первым, иначе сеть
  e.respondWith(caches.match(req).then(function (m) { return m || fetch(req); }));
});
