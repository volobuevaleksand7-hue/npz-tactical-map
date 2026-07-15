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

  // Аккаунт @BPLAlert_bot заморожен (15.07.2026), но CTA на него оставлены до разморозки.
  // Считаем клики — это замер реального интереса к подписке (цель bot_click_frozen, параметр
  // page = какая страница даёт спрос). ponytail: живёт здесь, а не отдельным файлом, потому что
  // vpn-nudge.js уже инжектится на ВСЕ страницы (build-nav + gen-rocket-danger + gen-wave) —
  // значит переживает регенерацию. Снять вместе с разморозкой бота.
  function trackBotInterest() {
    var links = [].slice.call(document.querySelectorAll('a[href*="t.me/BPLAlert_bot"]'));
    if (!links.length) return;
    var page = location.pathname;
    links.forEach(function (a) {
      if (a.dataset._bot) return;
      a.dataset._bot = '1';
      a.addEventListener('click', function () {
        try { if (window.ym) ym(110490245, 'reachGoal', 'bot_click_frozen', { page: page }); } catch (e) {}
        try { if (window.va) va('event', { name: 'bot_click_frozen', data: { page: page } }); } catch (e) {}
      });
    });
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
      '<a class="pp-vpn-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">→ Открыть источник</a>';
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
      // язычок виден целиком; периодически «подмигивает» — заезжает на половину и выезжает (фаза сдвинута per-tab → поочерёдно)
      '.nudge-tab.show{display:flex;transform:translateX(0);animation:tabPeek 12s ease-in-out infinite}' +
      '.nudge-tab.show:hover{transform:translateX(0)!important;transition:transform .3s ease}' +
      '.guard-face{width:28px;height:28px;color:inherit;overflow:visible}' +
      '.guard-face .sh-body{fill:currentColor}' +
      '.guard-face .face{transform-box:fill-box;transform-origin:center;animation:gScan 30s ease-in-out infinite}' +
      '.guard-face .eye{fill:#fff;transform-box:fill-box;transform-origin:center;animation:gBlink 30s infinite}' +
      '.guard-face .brow,.guard-face .mouth{stroke:#fff;stroke-width:1.3;stroke-linecap:round;fill:none}' +
      '.guard-face .plane{fill:#fff}' +
      '.nudge-tab.show:hover,.nudge-tab.show:hover .eye,.nudge-tab.show:hover .face{animation:none}' +
      // моргает и коротко «смотрит по сторонам» только когда снаружи (80–90% цикла)
      '@keyframes gBlink{0%,83%,86%,89%,100%{transform:scaleY(1)}84.5%,87.5%{transform:scaleY(.12)}}' +
      '@keyframes gScan{0%,80%,92%,100%{transform:translateX(0)}84%{transform:translateX(-1.2px)}89%{transform:translateX(1.2px)}}' +
      // подмигивание язычка: покой снаружи → заехать на половину → выехать обратно (1 раз за 12с)
      '@keyframes tabPeek{0%,86%,100%{transform:translateX(0)}93%{transform:translateX(-50%)}}' +
      // side-right: для карточек, выезжающих СПРАВА (art-nudge). Без этого язычок вылезал слева,
      // а карточка справа. Зеркалим: кромка, скругление, направление подмигивания.
      '.nudge-tab.side-right{left:auto;right:0;border-left:1px solid var(--line,#e4e4e7);border-right:none;' +
      'border-radius:12px 0 0 12px;transform:translateX(100%)}' +
      '.nudge-tab.side-right.show{transform:translateX(0);animation:tabPeekRight 12s ease-in-out infinite}' +
      '@keyframes tabPeekRight{0%,86%,100%{transform:translateX(0)}93%{transform:translateX(50%)}}' +
      '@media(prefers-reduced-motion:reduce){.nudge-tab.show,.nudge-tab.side-right.show{animation:none;transform:translateX(0)}' +
      '.guard-face .eye,.guard-face .face{animation:none}}';
    document.head.appendChild(s);
  }
  function dock(card, opts) {
    injectDockCSS();
    var reg = window.__nudgeDocks || (window.__nudgeDocks = []);
    var tab = document.createElement('button');
    tab.type = 'button'; tab.className = 'nudge-tab' + (opts.side === 'right' ? ' side-right' : '');
    tab.setAttribute('aria-label', opts.label || 'Открыть');
    tab.style.cssText = (opts.pos || '') + (opts.accent ? ';color:' + opts.accent : '');
    tab.style.animationDelay = (reg.length % 2 ? '-6s' : '0s'); // сдвиг фазы: язычки подмигивают поочерёдно, не разом
    tab.innerHTML = opts.icon;
    document.body.appendChild(tab);
    function persist(v) { try { v ? localStorage.setItem(opts.key, 'dock') : localStorage.removeItem(opts.key); } catch (e) {} }
    function collapse() { card.classList.add('nudge-out'); persist(true); setTimeout(function () { tab.classList.add('show'); }, 180); }
    function expand() {
      reg.forEach(function (d) { if (d !== api) d.collapse(); }); // одна карточка открыта за раз — не перекрываются
      tab.classList.remove('show'); card.classList.remove('nudge-out'); persist(false);
    }
    tab.addEventListener('click', expand);
    if (opts.startDocked) tab.classList.add('show'); // card уже с .nudge-out (без анимации на загрузке)
    var api = { collapse: collapse, expand: expand };
    reg.push(api);
    return api;
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
      '<a class="pp-vpn-float-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">Открыть источник →</a>';
    d.querySelector('.pp-vpn-float-btn').addEventListener('click', track);
    return d;
  }

  document.addEventListener('DOMContentLoaded', function () {
    trackBotInterest(); // до раннего return для карт — CTA бота есть и на radar/karta-azs
    if (document.getElementById('map')) {
      // 15.07 («пока что»): VPN-плашка на КАРТАХ отключена — её место заняла карточка свежей
      // сводки (article-nudge.js), внутренняя перелинковка вместо партнёрской. Вернуть =
      // раскомментировать блок ниже. На контентных страницах VPN-промо (ниже) работает как было.
      /*
      var K = 'vpn_float_x';
      // Всегда стартуем свёрнутым язычком слева: плавающая карточка перекрывала мобильный KPI-бар (v1.19.1).
      var startDocked = true;
      var f = floatPromo();
      if (startDocked) f.classList.add('nudge-out'); // до вставки в DOM — без анимации-мигания
      document.body.appendChild(f);
      var d = dock(f, { key: K, label: 'Доступ через VPN', icon: GUARD_SHIELD, pos: 'bottom:96px', startDocked: startDocked });
      f.querySelector('.pp-vpn-float-x').addEventListener('click', d.collapse);
      */
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
