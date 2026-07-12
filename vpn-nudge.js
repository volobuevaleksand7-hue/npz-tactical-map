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

  // Dock: свернуть плавающую карточку у левого края в вертикальный «язычок» (не удалять) —
  // тап по язычку возвращает карточку. Общий для vpn-nudge и sub-nudge (экспортим в window).
  // Guard-щит с серьёзным лицом (глаза моргают, брови сдвинуты) — иконка VPN-язычка.
  var GUARD_SHIELD =
    '<svg class="guard-face" viewBox="0 0 24 26" aria-hidden="true">' +
      '<path class="sh-body" d="M12 2.4 20 5.4 V11 c0 5.4-3.4 8.6-8 11 C8.4 19.6 4 16.4 4 11 V5.4 Z"/>' +
      '<g class="face">' +
        '<path class="brow" d="M8.5 8.1 L11 9"/><path class="brow" d="M15.5 8.1 L13 9"/>' +
        '<circle class="eye" cx="9.7" cy="11" r="1.45"/><circle class="eye" cx="14.3" cy="11" r="1.45"/>' +
        '<path class="mouth" d="M10.4 14.6 L13.6 14.6"/>' +
      '</g>' +
    '</svg>';

  function injectDockCSS() {
    if (document.getElementById('nudge-dock-css')) return;
    var s = document.createElement('style'); s.id = 'nudge-dock-css';
    s.textContent =
      '.nudge-out{transform:translateX(-135%)!important;opacity:0!important;pointer-events:none!important;' +
      'transition:transform .32s cubic-bezier(.4,0,.2,1),opacity .32s ease!important}' +
      '.nudge-tab{position:fixed;left:0;z-index:1200;display:none;align-items:center;justify-content:center;' +
      'width:34px;height:64px;border:1px solid var(--line,#e4e4e7);border-left:none;border-radius:0 12px 12px 0;' +
      'background:var(--surface,#fff);color:var(--teal,#12a594);cursor:pointer;box-shadow:3px 3px 14px rgba(0,0,0,.16);' +
      'transform:translateX(-100%);line-height:0}' +
      // язычок стоит скрытым (виден ~4px край), раз в 30с плавно выезжает: половина → пауза → полностью → назад
      '.nudge-tab.show{display:flex;animation:peekGuard 30s ease-in-out infinite}' +
      '.nudge-tab.show:hover{transform:translateX(0)!important;transition:transform .3s ease}' +
      '@keyframes peekGuard{0%,55%{transform:translateX(-90%)}63%,70%{transform:translateX(-48%)}' +
      '80%,90%{transform:translateX(0)}100%{transform:translateX(-90%)}}' +
      '.guard-face{width:28px;height:28px;color:inherit;overflow:visible}' +
      '.guard-face .sh-body{fill:currentColor}' +
      '.guard-face .face{transform-box:fill-box;transform-origin:center;animation:gScan 30s ease-in-out infinite}' +
      '.guard-face .eye{fill:#fff;transform-box:fill-box;transform-origin:center;animation:gBlink 30s infinite}' +
      '.guard-face .brow,.guard-face .mouth{stroke:#fff;stroke-width:1.3;stroke-linecap:round;fill:none}' +
      '.guard-face .plane{fill:#fff}' +
      '.nudge-tab.show:hover .eye,.nudge-tab.show:hover .face{animation:none}' +
      // моргает и коротко «смотрит по сторонам» только когда снаружи (80–90% цикла)
      '@keyframes gBlink{0%,83%,86%,89%,100%{transform:scaleY(1)}84.5%,87.5%{transform:scaleY(.12)}}' +
      '@keyframes gScan{0%,80%,92%,100%{transform:translateX(0)}84%{transform:translateX(-1.2px)}89%{transform:translateX(1.2px)}}' +
      '@media(prefers-reduced-motion:reduce){.nudge-tab.show{animation:none;transform:translateX(-90%)}' +
      '.guard-face .eye,.guard-face .face{animation:none}}';
    document.head.appendChild(s);
  }
  function dock(card, opts) {
    injectDockCSS();
    var tab = document.createElement('button');
    tab.type = 'button'; tab.className = 'nudge-tab';
    tab.setAttribute('aria-label', opts.label || 'Открыть');
    tab.style.cssText = (opts.pos || '') + (opts.accent ? ';color:' + opts.accent : '');
    tab.innerHTML = opts.icon;
    document.body.appendChild(tab);
    function persist(v) { try { v ? localStorage.setItem(opts.key, 'dock') : localStorage.removeItem(opts.key); } catch (e) {} }
    function collapse() { card.classList.add('nudge-out'); persist(true); setTimeout(function () { tab.classList.add('show'); }, 180); }
    function expand() { tab.classList.remove('show'); card.classList.remove('nudge-out'); persist(false); }
    tab.addEventListener('click', expand);
    if (opts.startDocked) tab.classList.add('show'); // card уже с .nudge-out (без анимации на загрузке)
    return { collapse: collapse, expand: expand };
  }
  window.__nudgeDock = dock;

  // Floating card for map pages (main map, /karta-bpla, /karta-azs) — no in-content anchor,
  // so the promo lives in a corner. Крестик сворачивает в язычок (dock), не удаляет.
  function floatPromo() {
    var d = document.createElement('div');
    d.className = 'pp-vpn-float';
    d.innerHTML =
      '<button type="button" class="pp-vpn-float-x" aria-label="Свернуть">×</button>' +
      '<span class="pp-vpn-ic">' + SHIELD + '</span>' +
      '<div class="pp-vpn-float-t"><b>Источники недоступны в РФ?</b>' +
        '<span>Западные СМИ по теме — через VPN</span></div>' +
      '<a class="pp-vpn-float-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">Открыть через VPN →</a>';
    d.querySelector('.pp-vpn-float-btn').addEventListener('click', track);
    return d;
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('map')) {
      var K = 'vpn_float_x';
      // Всегда стартуем свёрнутым язычком слева: плавающая карточка перекрывала мобильный KPI-бар (v1.19.1).
      var startDocked = true;
      var f = floatPromo();
      if (startDocked) f.classList.add('nudge-out'); // до вставки в DOM — без анимации-мигания
      document.body.appendChild(f);
      var d = dock(f, { key: K, label: 'Доступ через VPN', icon: GUARD_SHIELD, pos: 'top:52%', startDocked: startDocked });
      f.querySelector('.pp-vpn-float-x').addEventListener('click', d.collapse);
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
