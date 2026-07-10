(function () {
  // Client-injected VPN nudge for static pages (npz/*, news, SEO landers).
  // Rendered on the client → NOT baked into the crawlable HTML (kept out of the search index),
  // but visible to readers. ponytail: RF_BLOCKED mirrors the list in app.js — two copies until
  // the test proves this worth a shared module; keep them in sync if you edit either.
  var RF_BLOCKED = /(^|\.)(meduza\.io|themoscowtimes\.com|svoboda\.org|currenttime\.tv|theins\.ru|mediazona\.care|zona\.media|novayagazeta\.eu|verstka\.media|holod\.media|istories\.media|agents\.media|proekt\.media|republic\.ru|tvrain\.tv|bbc\.com|bbc\.co\.uk|dw\.com|reuters\.com|theguardian\.com|cnn\.com|euronews\.com|kyivindependent\.com|kyivpost\.com|pravda\.com\.ua|nv\.ua|focus\.ua|hromadske\.ua|liga\.net|err\.ee|sovanews\.tv)$/i;
  var REF = 'https://hidemn.club/#6a514a15942d6';

  function host(u) { try { return new URL(u, location.href).hostname.replace(/^www\./, ''); } catch (e) { return ''; } }

  // Fire both counters best-effort: Metrika where present (map), Vercel analytics on static pages.
  function track() {
    try { if (window.ym) ym(110490245, 'reachGoal', 'vpn_click'); } catch (e) {}
    try { if (window.va) va('event', { name: 'vpn_click' }); } catch (e) {}
  }

  function promo(contextual) {
    var head = contextual ? 'Источник заблокирован в РФ' : 'Часть источников недоступна в РФ';
    var body = contextual
      ? 'Открыть можно через VPN — работает в РФ, оплата криптой'
      : 'Первоисточники по теме (западные СМИ) заблокированы в РФ. Открыть через VPN — работает в РФ, оплата криптой';
    var d = document.createElement('div');
    d.className = 'pp-vpn';
    d.style.cssText = 'max-width:560px;margin:16px auto';
    d.innerHTML =
      '<div class="pp-vpn-h">🛡<div class="pp-vpn-t"><b>' + head + '</b><span>' + body + '</span></div></div>' +
      '<a class="pp-vpn-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">Получить доступ через hidemy →</a>';
    d.querySelector('.pp-vpn-btn').addEventListener('click', track);
    return d;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var links = [].slice.call(document.querySelectorAll('a[href^="http"]'));
    var firstBlocked = null;
    links.forEach(function (a) {
      if (a.dataset._vpn || !RF_BLOCKED.test(host(a.href))) return;
      a.dataset._vpn = '1';
      a.insertAdjacentHTML('afterend', ' <span class="vpn-off">🔒 недоступно в РФ</span>');
      if (!firstBlocked) firstBlocked = a;
    });
    if (firstBlocked) {
      var box = firstBlocked.closest('li,p,article,section,div') || firstBlocked.parentNode;
      box.insertAdjacentElement('afterend', promo(true));
    } else {
      // No blocked source on the page → place ONE block high (right after the hero/stats),
      // so it's near the fold on the fat SEO pages instead of buried at the bottom.
      var anchor = document.querySelector('.status-grid, .landing-hero, main section, main h2');
      if (anchor) anchor.insertAdjacentElement('afterend', promo(false));
      else (document.querySelector('main, article, .content, .container, .wrap') || document.body).appendChild(promo(false));
    }
  });
})();
