(function () {
  // Client-injected VPN nudge for static pages (npz/*, news, SEO landers) and maps.
  // Rendered on the client -> NOT baked into the crawlable HTML (kept out of the search index),
  // but visible to readers. ponytail: RF_BLOCKED mirrors the list in app.js -- two copies until
  // the test proves this worth a shared module; keep them in sync if you edit either.
  var RF_BLOCKED = /(^|\.)(meduza\.io|themoscowtimes\.com|svoboda\.org|currenttime\.tv|theins\.ru|mediazona\.care|zona\.media|novayagazeta\.eu|verstka\.media|holod\.media|istories\.media|agents\.media|proekt\.media|republic\.ru|tvrain\.tv|bbc\.com|bbc\.co\.uk|dw\.com|reuters\.com|theguardian\.com|cnn\.com|euronews\.com|kyivindependent\.com|kyivpost\.com|pravda\.com\.ua|nv\.ua|focus\.ua|hromadske\.ua|liga\.net|err\.ee|sovanews\.tv)$/i;
  var REF = 'https://hidemn.club/#6a514a15942d6';
  var SHIELD = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.6 20 5.6 V11 c0 5-3.4 8-8 10.4 C8.4 19 4 16 4 11 V5.6 Z"/><circle cx="12" cy="10.4" r="1.7"/><path d="M12 12.1 V14.8"/></svg>';

  function host(u) { try { return new URL(u, location.href).hostname.replace(/^www\./, ''); } catch (e) { return ''; } }

  function track() {
    try { if (window.ym) ym(110490245, 'reachGoal', 'vpn_click'); } catch (e) {}
    try { if (window.va) va('event', { name: 'vpn_click' }); } catch (e) {}
  }

  function promo(contextual) {
    var head = contextual ? 'Источник заблокирован в РФ' : 'Часть источников недоступна в РФ';
    var body = contextual
      ? 'Открыть можно через VPN — работает в РФ'
      : 'Первоисточники по теме (западные СМИ) заблокированы в РФ. Открыть через VPN — работает в РФ';
    var d = document.createElement('div');
    d.className = 'pp-vpn';
    d.style.cssText = 'max-width:560px;margin:16px auto';
    d.innerHTML =
      '<div class="pp-vpn-h"><span class="pp-vpn-ic">' + SHIELD + '</span>' +
        '<div class="pp-vpn-t"><span class="pp-vpn-tag">доступ через VPN</span>' +
        '<b>' + head + '</b><div class="pp-vpn-b">' + body + '</div></div></div>' +
      '<a class="pp-vpn-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">→ Получить доступ через hidemy</a>';
    d.querySelector('.pp-vpn-btn').addEventListener('click', track);
    return d;
  }

  // Small dismissible floating card for map pages (main map, /karta-bpla, /karta-azs) —
  // those have no in-content anchor, so the promo lives in a corner instead of the flow.
  function floatPromo() {
    var K = 'vpn_float_x';
    try { if (localStorage.getItem(K)) return null; } catch (e) {}
    var d = document.createElement('div');
    d.className = 'pp-vpn-float';
    d.innerHTML =
      '<button type="button" class="pp-vpn-float-x" aria-label="Закрыть">×</button>' +
      '<span class="pp-vpn-ic">' + SHIELD + '</span>' +
      '<div class="pp-vpn-float-t"><b>Источники недоступны в РФ?</b>' +
        '<span>Западные СМИ по теме — через VPN</span></div>' +
      '<a class="pp-vpn-float-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">Открыть через VPN →</a>';
    d.querySelector('.pp-vpn-float-btn').addEventListener('click', track);
    d.querySelector('.pp-vpn-float-x').addEventListener('click', function () {
      try { localStorage.setItem(K, '1'); } catch (e) {}
      d.remove();
    });
    return d;
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('map')) {
      var f = floatPromo();
      if (f) document.body.appendChild(f);
      return;
    }
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
      var anchor = document.querySelector('.status-grid, .landing-hero, main section, main h2');
      if (anchor) anchor.insertAdjacentElement('afterend', promo(false));
      else (document.querySelector('main, article, .content, .container, .wrap') || document.body).appendChild(promo(false));
    }
  });
})();
