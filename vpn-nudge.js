(function () {
  // Client-injected VPN nudge for static pages (npz/*, news, SEO landers) and maps.
  // Rendered on the client -> NOT baked into the crawlable HTML (kept out of the search index),
  // but visible to readers. ponytail: RF_BLOCKED mirrors the list in app.js -- two copies until
  // the test proves this worth a shared module; keep them in sync if you edit either.
  var RF_BLOCKED = /(^|\.)(meduza\.io|themoscowtimes\.com|svoboda\.org|currenttime\.tv|theins\.ru|mediazona\.care|zona\.media|novayagazeta\.eu|verstka\.media|holod\.media|istories\.media|agents\.media|proekt\.media|republic\.ru|tvrain\.tv|bbc\.com|bbc\.co\.uk|dw\.com|reuters\.com|theguardian\.com|cnn\.com|euronews\.com|kyivindependent\.com|kyivpost\.com|pravda\.com\.ua|nv\.ua|focus\.ua|hromadske\.ua|liga\.net|err\.ee|sovanews\.tv)$/i;
  // 🔴 VPN-промо ВЫКЛЮЧЕНО 09.08.2026. Две недели данных: 0-6 кликов/сут, конверсия
  // 0.06-0.14% (до свапа партнёрки было 0.36-1.67%), а кабинет RKNoff по рефералке
  // ref-609952529 не найден с 24.07 — то есть продаж мы не видим в принципе и гоним
  // трафик бесплатно. Канал на том же месте даёт втрое больше кликов (14-26/сут).
  // Освободившийся слот дока на картах отдан каналу — это самый заметный элемент сайта.
  // Вернуть: поставить true (весь код промо цел и на месте).
  var VPN_ENABLED = false;
  var REF = 'https://t.me/rknoff_bot?start=ref-609952529';
  var ANTENNA = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 15 A9 9 0 0 1 19 15"/><path d="M8.2 12.6 A5 5 0 0 1 15.8 12.6"/><circle cx="12" cy="16.4" r="1.6"/><path d="M12 18 V21.4"/></svg>';
  var SHIELD = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.6 20 5.6 V11 c0 5-3.4 8-8 10.4 C8.4 19 4 16 4 11 V5.6 Z"/><circle cx="12" cy="10.4" r="1.7"/><path d="M12 12.1 V14.8"/></svg>';

  function host(u) { try { return new URL(u, location.href).hostname.replace(/^www\./, ''); } catch (e) { return ''; } }

  function track() {
    try { if (window.ym) ym(110490245, 'reachGoal', 'vpn_click'); } catch (e) {}
    try { if (window.va) va('event', { name: 'vpn_click' }); } catch (e) {}
  }

  // CTA переведены с замороженного @BPLAlert_bot на канал @npz_karta_online (31.07.2026).
  // Считаем клики по каналу — цель tg_channel_click, параметр page = какая страница даёт спрос.
  // Старая цель bot_click_frozen остаётся для страниц, где ссылка на бота ещё не заменена:
  // пока такие есть, две цели считаются раздельно и история не смешивается.
  // ponytail: живёт здесь, а не отдельным файлом, потому что vpn-nudge.js уже инжектится на
  // ВСЕ страницы (build-nav + gen-rocket-danger + gen-wave) — значит переживает регенерацию.
  var CHANNEL_URL = 'https://t.me/npz_karta_online';
  var TG_GOALS = [
    { match: 't.me/npz_karta_online', goal: 'tg_channel_click' },
    { match: 't.me/BPLAlert_bot',     goal: 'bot_click_frozen' }
  ];

  // 🔴 Слушаем документ, а не навешиваем на найденные ссылки: две самые заметные кнопки —
  // баннер .subscription-alert и попап sub-nudge.js — появляются в DOM ПОЗЖЕ загрузки, и
  // разовый querySelectorAll их не видел. Клики по ним не считались вообще.
  // Делегирование ловит ссылку независимо от того, когда её вставили, и стоит одного слушателя.
  function trackBotInterest() {
    document.addEventListener('click', function (e) {
      var a = e.target && e.target.closest && e.target.closest('a[href*="t.me/"]');
      if (!a) return;
      var page = location.pathname;
      for (var i = 0; i < TG_GOALS.length; i++) {
        if (a.href.indexOf(TG_GOALS[i].match) === -1) continue;
        var goal = TG_GOALS[i].goal;
        try { if (window.ym) ym(110490245, 'reachGoal', goal, { page: page }); } catch (err) {}
        try { if (window.va) va('event', { name: goal, data: { page: page } }); } catch (err) {}
        return;
      }
    }, true);
  }

  // Оффер: давим на бесплатный доступ + скорость, мотив остаётся «открыть источник».
  // 🔴 «5 дней» и «3 минуты» — слова владельца, в боте НЕ подтверждены. Проверить до деплоя.
  // Про «без установки приложений» намеренно молчим: бот, скорее всего, отдаёт конфиг под
  // клиент (WireGuard/Outline) — утверждать обратное = врать в UI.
  var OFFER = 'бесплатный доступ на 5 дней, подключение за 3 минуты в Telegram-боте';
  var CTA_TXT = 'Подключить бесплатно на 5 дней →';

  function promo(contextual) {
    var head = contextual ? 'Источник заблокирован в РФ' : 'Часть источников недоступна в РФ';
    var body = contextual
      ? 'Открыть можно через VPN — ' + OFFER
      : 'Первоисточники по теме (западные СМИ) заблокированы в РФ. Открыть их можно через VPN — ' + OFFER;
    var d = document.createElement('div');
    d.className = 'pp-vpn';
    d.style.cssText = 'max-width:560px;margin:16px auto';
    d.innerHTML =
      '<div class="pp-vpn-h"><span class="pp-vpn-ic">' + SHIELD + '</span>' +
        '<div class="pp-vpn-t"><span class="pp-vpn-tag">доступ через VPN</span>' +
        '<b>' + head + '</b><div class="pp-vpn-b">' + body + '</div></div></div>' +
      '<a class="pp-vpn-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">' + CTA_TXT + '</a>';
    d.querySelector('.pp-vpn-btn').addEventListener('click', track);
    return d;
  }

  // Inline-карточка канала — в том же месте статьи, где стояло VPN-промо, и в тех же
  // классах (.pp-vpn*), чтобы не заводить второй набор стилей. Возвращает null, если
  // кнопка канала на странице уже есть — не дублируем (addChannelCta мог отработать раньше).
  function promoChannel() {
    if (document.querySelector('a[href*="t.me/npz_karta_online"]')) return null;
    var d = document.createElement('div');
    d.className = 'pp-vpn';
    d.style.cssText = 'max-width:560px;margin:16px auto';
    d.innerHTML =
      '<div class="pp-vpn-h"><span class="pp-vpn-ic">' + ANTENNA + '</span>' +
        '<div class="pp-vpn-t"><span class="pp-vpn-tag">телеграм-канал</span>' +
        '<b>Сводки об ударах дважды в день</b><div class="pp-vpn-b">Что произошло за ночь и за день: ' +
        'объекты, регионы, карта и цифры — коротко, без пересказа новостей.</div></div></div>' +
      '<a class="pp-vpn-btn" href="' + CHANNEL_URL + '" target="_blank" rel="noopener">Подписаться на канал →</a>';
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
        '<span>Открыть через VPN — 5 дней бесплатно, 3 минуты в Telegram-боте</span></div>' +
      '<a class="pp-vpn-float-btn" href="' + REF + '" target="_blank" rel="noopener nofollow sponsored">' + CTA_TXT + '</a>';
    d.querySelector('.pp-vpn-float-btn').addEventListener('click', track);
    return d;
  }

  // Карточка канала в том же доке, что раньше занимало VPN-промо. Клик считает уже
  // существующее делегирование trackBotInterest (цель tg_channel_click) — своего
  // обработчика не заводим.
  function floatChannel() {
    var d = document.createElement('div');
    d.className = 'pp-vpn-float';
    d.innerHTML =
      '<button type="button" class="pp-vpn-float-x" aria-label="Свернуть">×</button>' +
      '<span class="pp-vpn-ic">' + ANTENNA + '</span>' +
      '<div class="pp-vpn-float-t"><b>Сводки об ударах в Telegram</b>' +
        '<span>Два раза в день: что за ночь произошло, карта и цифры</span></div>' +
      '<a class="pp-vpn-float-btn" href="' + CHANNEL_URL + '" target="_blank" rel="noopener">Подписаться на канал →</a>';
    return d;
  }

  // Топ-3 текстовых донора трафика (замер 24.07) — плавающая карточка вместо inline,
  // глубоко в статье её реже замечают. '/' не в списке: там уже #map (карта на главной).
  var FLOAT_PAGES = ['/skolko-skladov-wildberries-ozon', '/karta-bpla', '/news'];

  // Бейджи «🔒 недоступно в РФ» у заблокированных ссылок информативны сами по себе, отдельно
  // от промо — поэтому вешаются и там, где карточка плавающая. Возвращает первую такую ссылку
  // (к ней привязывается контекстная inline-карточка). На картах НЕ зовём: там ссылки живут в
  // попапах, их рисует app.js своей копией.
  function markBlockedLinks() {
    var firstBlocked = null;
    [].slice.call(document.querySelectorAll('a[href^="http"]')).forEach(function (a) {
      if (a.dataset._vpn || !RF_BLOCKED.test(host(a.href))) return;
      a.dataset._vpn = '1';
      a.insertAdjacentHTML('afterend', ' <span class="vpn-off">🔒 недоступно в РФ</span>');
      if (!firstBlocked) firstBlocked = a;
    });
    return firstBlocked;
  }

  // Читатель уходит в чужие каналы: 143 ссылки-источника на exilenova_plus / radarrussiia /
  // noel_reports на 41 странице, и НИ НА ОДНОЙ из них не было нашей кнопки (замер 01.08.2026,
  // ~1900 переходов в чужие каналы за 17 дней). Ставим свою рядом; источники не трогаем —
  // они нужны для нейтральной атрибуции.
  // ponytail: инжектим отсюда, а не правим шаблоны news/*.html и npz/*.html — этот файл уже
  // на всех страницах и переживает их регенерацию.
  var FOREIGN_TG = 'a[href*="t.me/exilenova_plus"],a[href*="t.me/radarrussiia"],a[href*="t.me/noel_reports"]';

  function addChannelCta() {
    if (document.querySelector('a[href*="t.me/npz_karta_online"]')) return; // кнопка уже есть
    if (!document.querySelector(FOREIGN_TG)) return;                        // уводить некому

    var row = document.querySelector('.cta-buttons');
    if (row) {
      var b = document.createElement('a');
      b.className = 'cta-btn secondary';
      b.href = CHANNEL_URL; b.target = '_blank'; b.rel = 'noopener';
      b.textContent = '📡 Сводки в Telegram →';
      row.appendChild(b);
      return;
    }
    var main = document.querySelector('main');
    if (!main) return;
    var box = document.createElement('div');
    box.style.cssText = 'margin:28px auto;max-width:900px;padding:14px 18px;border:1px solid ' +
      'rgba(18,165,148,.35);border-radius:12px;background:rgba(18,165,148,.07);font-size:15px';
    box.innerHTML = 'Следите за обстановкой в нашем Telegram-канале — сводки об ударах дважды ' +
      'в день. <a href="' + CHANNEL_URL + '" target="_blank" rel="noopener" ' +
      'style="font-weight:700;white-space:nowrap">📡 Подписаться →</a>';
    main.appendChild(box);
  }

  // 🔴 На страницах заводов и в новостях ссылки-источники дорисовываются из данных уже ПОСЛЕ
  // DOMContentLoaded — разовая проверка не находила ни одной и молча выходила. Пробуем трижды;
  // повтор безопасен, addChannelCta выходит сразу, если кнопка уже стоит.
  function scheduleChannelCta() {
    addChannelCta();
    window.addEventListener('load', addChannelCta);
    setTimeout(addChannelCta, 2500);
  }

  document.addEventListener('DOMContentLoaded', function () {
    trackBotInterest(); // до раннего return для карт — CTA бота есть и на radar/karta-azs
    scheduleChannelCta();
    var isMap = !!document.getElementById('map');
    var firstBlocked = isMap ? null : markBlockedLinks();
    if (isMap || FLOAT_PAGES.indexOf(location.pathname.replace(/\/$/, '')) !== -1) {
      // На картах живут ОБЕ плашки (решение Серёги 15.07): слева внизу — язычок, справа —
      // карточка свежей сводки (article-nudge.js). Не конфликтуют: разные стороны дока
      // (side:'right' у сводки) + реестр __nudgeDocks сдвигает фазы подмигивания.
      // 09.08.2026: в левом язычке вместо VPN — подписка на канал (см. VPN_ENABLED).
      var K = 'vpn_float_x'; // ключ localStorage прежний: у кого язычок был свёрнут, таким и останется
      // Всегда стартуем свёрнутым язычком слева: плавающая карточка перекрывала мобильный KPI-бар (v1.19.1).
      var startDocked = true;
      var f = VPN_ENABLED ? floatPromo() : floatChannel();
      if (startDocked) f.classList.add('nudge-out'); // до вставки в DOM — без анимации-мигания
      document.body.appendChild(f);
      var d = dock(f, VPN_ENABLED
        ? { key: K, label: 'Доступ через VPN', icon: GUARD_SHIELD, pos: 'bottom:96px', startDocked: startDocked }
        : { key: K, label: 'Сводки в Telegram', icon: ANTENNA, pos: 'bottom:96px', startDocked: startDocked });
      f.querySelector('.pp-vpn-float-x').addEventListener('click', d.collapse);
      return;
    }
    // Бейджи «🔒 недоступно в РФ» остаются и без VPN-промо: читателю честнее знать, что
    // ссылка не откроется, даже если мы больше ничего ему не предлагаем.
    // 🔴 Место, где стояло VPN-промо, не оставляем пустым: addChannelCta показывает кнопку
    // канала только там, где есть ссылка на ЧУЖОЙ телеграм («уводить некому»), а таких
    // страниц меньшинство — без этой ветки статьи остались бы вообще без CTA.
    var card = VPN_ENABLED ? promo(!!firstBlocked) : promoChannel();
    if (!card) return;
    if (firstBlocked) {
      var box = firstBlocked.closest('li,p,article,section,div') || firstBlocked.parentNode;
      box.insertAdjacentElement('afterend', card);
    } else {
      var anchor = document.querySelector('.status-grid, .landing-hero, main section, main h2');
      if (anchor) anchor.insertAdjacentElement('afterend', card);
      else (document.querySelector('main, article, .content, .container, .wrap') || document.body).appendChild(card);
    }
  });
})();
