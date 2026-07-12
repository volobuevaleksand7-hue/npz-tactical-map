/* Яндекс.Метрика NPZ — ЕДИНЫЙ источник счётчика для всего сайта.
   Подключается одной строкой <script src="/metrika.js"></script> на каждой странице
   (вставляют генераторы автоматически). Менять id/настройки счётчика — ТОЛЬКО здесь. */
(function (m, e, t, r, i, k, a) {
  m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments); };
  m[i].l = 1 * new Date();
  for (var j = 0; j < e.scripts.length; j++) { if (e.scripts[j].src === r) { return; } }
  k = e.createElement(t), a = e.getElementsByTagName(t)[0], k.async = 1, k.src = r, a.parentNode.insertBefore(k, a);
})(window, document, 'script', 'https://mc.yandex.ru/metrika/tag.js?id=110490245', 'ym');

ym(110490245, 'init', {
  ssr: true, webvisor: true, clickmap: true, ecommerce: 'dataLayer',
  referrer: document.referrer, url: location.href,
  accurateTrackBounce: true, trackLinks: true
});
