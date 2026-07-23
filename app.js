/* NPZ TACTICAL MAP — strategy/board-game client */
(function () {
  "use strict";

  var RAW = "https://raw.githubusercontent.com/volobuevaleksand7-hue/npz-tactical-map/main/";
  var FILES = {
    state: "data/fuel-state.json",
    hist: "data/history-crimea.json",
    forecast: "data/forecast.json",
    economy: "data/economy.json",
    strikes: "data/strikes.json",
    roads: "data/roads.json",
    availability: "data/fuel-availability.json",
    voices: "data/fuel-voices.json",
    grid: "data/grid-state.json",
    azsStations: "data/azs-stations.json",
    azsRoutes: "data/azs-routes.json",
    capacityTimeline: "data/capacity-timeline.json",
    health: "data/health.json",
    candidates: "data/strike-candidates.json",
    warehouses: "data/warehouses.json"
  };
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function safeUrl(u){u=String(u||'');return /^https?:\/\//i.test(u)?u:'#';}
  // Media inaccessible from RF without a VPN — matched against the source host.
  var RF_BLOCKED = /(^|\.)(meduza\.io|themoscowtimes\.com|svoboda\.org|currenttime\.tv|theins\.ru|mediazona\.care|zona\.media|novayagazeta\.eu|verstka\.media|holod\.media|istories\.media|agents\.media|proekt\.media|republic\.ru|tvrain\.tv|bbc\.com|bbc\.co\.uk|dw\.com|reuters\.com|theguardian\.com|cnn\.com|euronews\.com|kyivindependent\.com|kyivpost\.com|pravda\.com\.ua|nv\.ua|focus\.ua|hromadske\.ua|liga\.net|err\.ee|sovanews\.tv)$/i;
  function srcBlocked(u){try{return RF_BLOCKED.test(new URL(u).hostname);}catch(e){return false;}}
  function srcHost(u){try{return new URL(u).hostname.replace(/^www\./,'');}catch(e){return'';}}
  // Source line for a popup. RF-blocked sources render struck-through + a native VPN promo
  // (monetized hidemy.name affiliate via Admitad); normal sources render the plain link.
  function srcHtml(u,label){
    if(!u) return '';
    if(!srcBlocked(u)) return '<div class="pp-src"><a href="'+safeUrl(u)+'" target="_blank" rel="noopener">'+esc(label||'источник')+' ↗</a></div>';
    return '<div class="pp-src pp-src--off">🔒 <a href="'+safeUrl(u)+'" target="_blank" rel="noopener">'+esc(srcHost(u))+' — недоступно из РФ</a></div>'+
      '<div class="pp-vpn"><div class="pp-vpn-h"><span class="pp-vpn-ic"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.6 20 5.6 V11 c0 5-3.4 8-8 10.4 C8.4 19 4 16 4 11 V5.6 Z"/><circle cx="12" cy="10.4" r="1.7"/><path d="M12 12.1 V14.8"/></svg></span><div class="pp-vpn-t"><span class="pp-vpn-tag">доступ через VPN</span><b>Источник заблокирован в РФ</b><div class="pp-vpn-b">Открыть можно через VPN — работает в РФ</div></div></div>'+
      '<a class="pp-vpn-btn" href="https://hidemn.club/#6a514a15942d6" target="_blank" rel="noopener nofollow sponsored" onclick="try{ym(110490245,&#39;reachGoal&#39;,&#39;vpn_click&#39;)}catch(e){}">→ Получить доступ через hidemy</a></div>';
  }
  // ponytail: single padding tuned for the Russia view's topbar+strikebar overlay; reused on
  // Crimea/AZS maps too since their overlay is shorter — extra clearance there is harmless.
  var POPUP_OPTS = { autoPanPaddingTopLeft: [14, 90], autoPanPaddingBottomRight: [14, 60] };
  function bindButton(el, fn) {
    if (!el.hasAttribute("role")) el.setAttribute("role", "button");
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
    el.addEventListener("click", fn);
    el.addEventListener("keydown", function (e) {
      if (e.target !== el) return; // не перехватывать клавиши на вложенных ссылках/кнопках
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn.call(el, e); }
    });
  }
  // ponytail: минимальный toast — приложение не имеет своего менеджера уведомлений
  function showToast(text) {
    var t = document.createElement("div");
    t.className = "pwa-toast";
    t.textContent = text;
    document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("show"); }); // .pwa-toast скрыт без .show
    setTimeout(function () {
      t.classList.remove("show");
      setTimeout(function () { t.remove(); }, 300);
    }, 4000);
  }

  var S = { state: null, hist: null, forecast: null, economy: null, strikes: null, roads: null, availability: null, voices: null, grid: null, regionsGeo: null, outlineGeo: null, azsStations: null, azsRoutes: null, capacityTimeline: null, health: null };
  var SK = { dates: [], idx: 0, mode: "7d", from: "", to: "", playing: false, timer: null };
  var renderedStrikes = [], feedSorted = [];
  var maps = { ru: null, cr: null, az: null };
  var tiles = { ru: null, cr: null, az: null };
  var L_ru = {}, L_cr = {}, L_az = {};
  var nextSyncAt = 0, refreshTimer = null, regionMode = "now", crimeaReady = false, azsReady = false;
  var appStarted = false, azsDataPromise = null, regionsGeoPromise = null;
  var AZS_ROUTE = { line: null, cities: [] };
  var tripRequestId = 0; // bump on every build/reset so a late OSRM response can be told apart from stale

  var STC = { operational: "#2f9e57", partial: "#df8f17", down: "#d23a2e" };
  var LVL = { low: "#7bbf5a", medium: "#e0b020", high: "#df8f17", severe: "#d23a2e", critical: "#a01d14" };

  /* ---------- BOOT ---------- */
  function boot() {
    var log = document.getElementById("bootLog"), fill = document.getElementById("bootFill");
    var t0 = Date.now();

    function addLine(text, cls) {
      var d = document.createElement("div");
      d.className = cls || "ok";
      d.textContent = text;
      log.appendChild(d);
    }
    function setProgress(pct) {
      fill.style.width = Math.round(pct) + "%";
    }

    addLine("[ OK ] инициализация ТВД");
    setProgress(15);

    // Стартуем загрузку данных сразу
    var dataPromise = load();
    loadVersion();

    setTimeout(function () {
      addLine("[ OK ] загрузка игрового поля");
      setProgress(30);
    }, 50);

    function finish() {
      addLine("[WARN] режим = ОЦЕНКА (нет реалтайм-телеметрии)");
      setProgress(100);
      start();
    }

    dataPromise.then(function () {
      addLine("[ OK ] OSINT-канал :: данные получены");
      setProgress(80);
      // Минимальное время показа boot — 400 мс, чтобы экран не моргнул
      var elapsed = Date.now() - t0;
      if (elapsed < 400) setTimeout(finish, 400 - elapsed);
      else finish();
    }).catch(function (e) {
      addLine("[ERR ] ошибка загрузки", "warn");
      setProgress(100);
      start();
    });
  }

  function start() {
    document.getElementById("boot").classList.add("hidden");
    document.getElementById("app").classList.remove("hidden");
    // Тяжёлую инициализацию карт откладываем на после первого кадра,
    // чтобы #app отрисовался без задержки
    var inited = false;
    function initAll() {
      if (inited) return;
      inited = true;
      initTheme();
      initPwaInstall();
      initRuMap();
      loadGeo();
      initTabs();
      initControls();
      initMobile();
      initPanelExpand();
      initCardCollapse();
      tickClock(); setInterval(tickClock, 1000);
      appStarted = true;
      if (S.state) renderAll();
    }
    requestAnimationFrame(function () { requestAnimationFrame(initAll); });
    setTimeout(initAll, 400); // rAF не стреляет в скрытой вкладке — без фолбэка приложение не инициализируется до фокуса
  }

  function initMobile() {
    var COL_WIDTH = 820;
    var isMobile = window.innerWidth <= COL_WIDTH;
    var colLeft = document.querySelector(".col-left");
    var panelRight = document.getElementById("panelRight");
    var viewRu = document.getElementById("view-russia");

    // Bottom-sheet/FAB styles live in styles.css (.mob-sheet*/.mob-fab) — single source of truth.

    // --- FAB ---
    var fab = document.createElement("button");
    fab.className = "mob-fab";
    fab.innerHTML = "📊";
    fab.setAttribute("aria-label", "Открыть аналитическую панель");
    viewRu.appendChild(fab);

    // --- Bottom sheet ---
    var sheet = document.createElement("div");
    sheet.className = "mob-sheet collapsed";
    sheet.setAttribute("role", "dialog"); // немодальный: карта и навигация остаются доступны, aria-modal не ставим
    sheet.setAttribute("aria-label", "Аналитическая панель");
    sheet.innerHTML =
      '<div class="mob-sheet-handle"><span></span></div>' +
      '<div class="mob-sheet-kpi" role="button" tabindex="0" aria-label="Свернуть/развернуть панель"></div>' +
      '<div class="mob-sheet-tabs">' +
        '<button class="mob-sheet-tab active" data-tab="balance" aria-label="Национальный баланс">Баланс</button>' +
        '<button class="mob-sheet-tab" data-tab="strikes" aria-label="Лента ударов">Удары</button>' +
        '<button class="mob-sheet-tab" data-tab="npz" aria-label="Список НПЗ">НПЗ</button>' +
        '<button class="mob-sheet-tab" data-tab="voices" aria-label="Голоса с мест">Голоса</button>' +
      '</div>' +
      '<div class="mob-sheet-body"></div>';
    viewRu.appendChild(sheet);

    var body = sheet.querySelector(".mob-sheet-body");

    // Map tab → source element id
    var SOURCES = { balance: "balanceBody", strikes: "feedList", npz: "npzList", voices: "voicesList" };
    var panels = {};
    Object.keys(SOURCES).forEach(function (key) {
      var p = document.createElement("div");
      p.style.display = "none";
      p.setAttribute("role", "tabpanel");
      var tabBtn = sheet.querySelector('[data-tab="' + key + '"]');
      p.setAttribute("aria-label", tabBtn ? tabBtn.textContent : key);
      panels[key] = p;
      body.appendChild(p);
    });

    function copyContent(key) {
      var src = document.getElementById(SOURCES[key]);
      if (src) panels[key].innerHTML = src.innerHTML;
    }

    function switchTab(key) {
      sheet.querySelectorAll(".mob-sheet-tab").forEach(function (t) {
        t.classList.toggle("active", t.dataset.tab === key);
        t.setAttribute("aria-selected", t.dataset.tab === key ? "true" : "false");
      });
      Object.keys(panels).forEach(function (k) { panels[k].style.display = k === key ? "" : "none"; });
      copyContent(key);
    }

    // Event delegation for interactive items inside sheet body
    body.addEventListener("click", function (e) {
      // NPZ row — fly to refinery
      var nr = e.target.closest(".npz-row");
      if (nr && nr.dataset.id) {
        var ref = S.state && S.state.refineries && S.state.refineries.find(function (x) { return x.id === nr.dataset.id; });
        if (ref && ref._m) {
          sheet.classList.add("collapsed");
          fab.innerHTML = "📊";
          fab.setAttribute("aria-label", "Открыть аналитическую панель");
          maps.ru.flyTo([ref.lat, ref.lon], 6, { duration: .6 });
          ref._m.openPopup();
        }
        return;
      }
      // Feed item — fly to strike
      var fi = e.target.closest(".feed-item");
      if (fi && fi.dataset.fi !== undefined) {
        sheet.classList.add("collapsed");
        fab.innerHTML = "📊";
        fab.setAttribute("aria-label", "Открыть аналитическую панель");
        flyToStrike(feedSorted[+fi.dataset.fi]);
        return;
      }
      // Voice item — fly to location
      var vi = e.target.closest(".voice-item");
      if (vi && vi.dataset.vi !== undefined) {
        var v0 = (S.voices && S.voices.voices) || [];
        var sorted = v0.slice().sort(function (a, b) { return String(b.seen || b.date || "").localeCompare(String(a.seen || a.date || "")); });
        var q = sorted[+vi.dataset.vi];
        if (q && typeof q.lat === "number") {
          var btn = document.querySelector('#layerToggles button[data-layer=azs]');
          if (btn && !btn.classList.contains("active")) btn.click();
          sheet.classList.add("collapsed");
          fab.innerHTML = "📊";
          fab.setAttribute("aria-label", "Открыть аналитическую панель");
          maps.ru.flyTo([q.lat, q.lon], 7, { duration: .6 });
        }
        return;
      }
    });

    // Tab click handlers
    sheet.querySelectorAll(".mob-sheet-tab").forEach(function (tab) {
      tab.addEventListener("click", function () { switchTab(this.dataset.tab); });
    });

    // open/close helpers — минимальный focus-management: фокус внутрь при открытии, назад на FAB при закрытии
    function closeSheet() {
      if (sheet.classList.contains("collapsed")) return;
      sheet.classList.add("collapsed");
      fab.innerHTML = "📊";
      fab.setAttribute("aria-label", "Открыть аналитическую панель");
      fab.focus();
    }
    function openSheet() {
      sheet.classList.remove("collapsed");
      fab.innerHTML = "✕";
      fab.setAttribute("aria-label", "Закрыть аналитическую панель");
      var active = sheet.querySelector(".mob-sheet-tab.active");
      switchTab(active ? active.dataset.tab : "balance");
      var handle = sheet.querySelector(".mob-sheet-handle");
      if (handle) handle.focus();
    }

    // FAB / KPI strip toggle sheet (same logic, no duplication)
    function toggleSheet() {
      if (sheet.classList.contains("collapsed")) openSheet(); else closeSheet();
    }
    fab.addEventListener("click", toggleSheet);
    bindButton(sheet.querySelector(".mob-sheet-kpi"), toggleSheet);

    // Escape closes sheet
    sheet.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeSheet();
    });

    // Handle: клик/тап + Enter/Space сворачивает панель
    bindButton(sheet.querySelector(".mob-sheet-handle"), function () { closeSheet(); });
    sheet.querySelector(".mob-sheet-handle").setAttribute("aria-label", "Свернуть/развернуть панель");

    // Resize: show/hide desktop panels vs mobile sheet
    function applyMode() {
      var mobile = window.innerWidth <= COL_WIDTH;
      if (mobile) {
        colLeft.classList.add("mob-hidden");
        panelRight.classList.add("mob-hidden");
      } else {
        colLeft.classList.remove("mob-hidden");
        panelRight.classList.remove("mob-hidden");
        closeSheet();
      }
    }
    applyMode();
    var rt;
    window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(applyMode, 150); });

    // ponytail: авто-открытие панели на мобиле УБРАНО — она закрывала карту при каждой загрузке
    // (жалоба владельца, 50% трафика мобильный; карта = приоритет). Панель стартует свёрнутой,
    // открывается кнопкой 📊. Предзагружаем «Баланс», чтобы первое открытие было мгновенным.
    if (isMobile) switchTab("balance");
  }

  /* ---------- THEME ---------- */
  function tileUrl() {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    return "https://{s}.basemaps.cartocdn.com/" + (dark ? "dark_all" : "light_all") + "/{z}/{x}/{y}{r}.png";
  }
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("npz-theme"); } catch (e) {}
    document.documentElement.setAttribute("data-theme", saved || "light");
    // иконка = куда переключит: в светлой теме показываем 🌙 (переключит на тёмную), в тёмной — ☀️
    var themeBtn = document.getElementById("themeToggle");
    themeBtn.textContent = (saved === "dark") ? "☀️" : "🌙";
    themeBtn.setAttribute("aria-pressed", saved === "dark" ? "true" : "false");
    themeBtn.addEventListener("click", function () {
      var dark = document.documentElement.getAttribute("data-theme") === "dark";
      var next = dark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("npz-theme", next); } catch (e) {}
      this.textContent = next === "dark" ? "☀️" : "🌙";
      this.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
      [["ru", tiles.ru], ["cr", tiles.cr]].forEach(function (p) {
        if (p[1]) p[1].setUrl(tileUrl());
      });
    });
  }

  /* ---------- PWA INSTALL ---------- */
  // слушатель — сразу при загрузке скрипта: браузер может выстрелить beforeinstallprompt
  // до initPwaInstall (он ждёт boot), а событие одноразовое
  var deferredPrompt = null;
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
  });
  function initPwaInstall() {
    var btn = document.getElementById("installBtn");
    if (!btn) return;
    if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) {
      btn.classList.add("hidden");
      return;
    }
    btn.addEventListener("click", function (e) {
      if (!deferredPrompt) return; // нет сохранённого события (iOS/десктоп) — обычная ссылка на /install
      e.preventDefault();
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () { deferredPrompt = null; });
    });
    window.addEventListener("appinstalled", function () {
      btn.classList.add("hidden");
      deferredPrompt = null;
      showToast("✅ Приложение установлено");
    });
  }

  /* ---------- MAPS ---------- */
  // нейтральная атрибуция: без дефолтного префикса Leaflet (флаг+ссылка)
  L.Control.Attribution.prototype.options.prefix = "Leaflet";
  function baseTiles() {
    return L.tileLayer(tileUrl(), { attribution: "© OpenStreetMap · CARTO · OSINT ESTIMATE", subdomains: "abcd", maxZoom: 19 });
  }
  function initRuMap() {
    // ponytail: на узком экране тот же zoom показывает меньше градусов по ширине — центр
    // [55.5,55] (десктоп) уводит европейскую часть РФ (удары/НПЗ) за левый край, в кадре
    // остаётся Казахстан. На мобиле сдвигаем центр западнее, к плотности целей (Крым/Волгоград/Самара).
    var ruCenter = (window.innerWidth <= 768) ? [55, 47] : [55.5, 55];
    maps.ru = L.map("map", { center: ruCenter, zoom: 4, minZoom: 3, maxZoom: 9, worldCopyJump: false, zoomControl: false });
    maps.ru.on("click", closeAnalyticsDropdown);
    L.control.zoom({ position: "bottomright" }).addTo(maps.ru);
    tiles.ru = baseTiles().addTo(maps.ru);
    L_ru.regions = L.layerGroup().addTo(maps.ru);   // shading (bottom)
    L_ru.border = L.layerGroup().addTo(maps.ru);    // RF border
    L_ru.roads = L.layerGroup().addTo(maps.ru);     // дороги — топливные артерии
    L_ru.logistics = L.layerGroup().addTo(maps.ru);
    // НПЗ — кластеризация для юга РФ, где плотность заводов высокая
    L_ru.npz = (typeof L.markerClusterGroup === "function")
      ? L.markerClusterGroup({ maxClusterRadius: 60, spiderfyOnMaxZoom: true, disableClusteringAtZoom: 8 })
      : L.layerGroup();
    L_ru.npz.addTo(maps.ru);
    // Удары — кластеризация (множественные удары по одним городам)
    L_ru.strikes = (typeof L.markerClusterGroup === "function")
      ? L.markerClusterGroup({ maxClusterRadius: 34, spiderfyOnMaxZoom: true, disableClusteringAtZoom: 6, iconCreateFunction: strikeClusterIcon })
      : L.layerGroup();
    L_ru.strikes.addTo(maps.ru);
    // Хотспоты (⚠ на дорогах) — кластеризация, часто скучены у одного города
    L_ru.hotspots = (typeof L.markerClusterGroup === "function")
      ? L.markerClusterGroup({ maxClusterRadius: 40, spiderfyOnMaxZoom: true, disableClusteringAtZoom: 8 })
      : L.layerGroup();
    L_ru.hotspots.addTo(maps.ru);
    L_ru.azs = L.layerGroup();                      // AZS network status — OFF by default (toggle)
    L_ru.grid = L.layerGroup();                     // Electricity grid (substations + blackouts) — OFF by default
    L_ru.prices = L.layerGroup();                   // Price heatmap (АИ-95 по регионам) — OFF by default
    L_ru.candidates = L.layerGroup();               // Кандидаты в удары с ленты radar-map.ru (rumor) — OFF by default
    L_ru.warehouses = L.layerGroup();               // Крупные РЦ Wildberries/Ozon + поражённые — OFF by default
  }
  function loadGeo() {
    Promise.all([
      fetch("data/russia-outline.geojson").then(function (r) { return r.json(); }).catch(function () { return null; }),
      fetch("data/crimea-regions.geojson").then(function (r) { return r.json(); }).catch(function () { return null; }),
      fetch("data/new-territories.geojson").then(function (r) { return r.json(); }).catch(function () { return null; })
    ]).then(function (res) {
      S.outlineGeo = res[0]; S.crimeaGeo = res[1]; S.ntGeo = res[2];
      renderBorder();
      if (S.state) loadRegionsGeo();
    });
  }
  function initCrMap() {
    maps.cr = L.map("mapCrimea", { center: [45.25, 34.3], zoom: 7, minZoom: 6, maxZoom: 11, zoomControl: false });
    maps.cr.on("click", closeAnalyticsDropdown);
    L.control.zoom({ position: "bottomright" }).addTo(maps.cr);
    tiles.cr = baseTiles().addTo(maps.cr);
    L_cr.fill = L.layerGroup().addTo(maps.cr);   // заливка полуострова — как на основной карте
    L_cr.layer = L.layerGroup().addTo(maps.cr);  // маршруты + опорные точки (history-crimea.json)
    L_cr.azs = L.layerGroup().addTo(maps.cr);    // АЗС — тот же слой/стиль, что и на вкладке АЗС
    crimeaReady = true;
  }

  /* ---------- DATA LOAD ---------- */
  // live=true → raw-CDN ПЕРВЫМ с cache-bust (свежие данные без редеплоя Vercel),
  // фоллбэк на бандл. live=false → бандл первым (быстро, для статичных geojson/станций).
  var usedFallback = false;
  function fetchJsonPath(path, live) {
    var primary = live ? (RAW + path + "?t=" + Date.now()) : ("/" + path);
    var backup  = live ? ("/" + path) : (RAW + path);
    var opt = live ? { cache: "no-store" } : {};
    function fetchWithTimeout(url, fetchOpts) {
      var ctrl = new AbortController();
      var timer = setTimeout(function () { ctrl.abort(); }, 12000);
      var opts = Object.assign({}, fetchOpts || {}, { signal: ctrl.signal });
      return fetch(url, opts).then(function (r) {
        clearTimeout(timer);
        if (!r.ok) throw 0;
        return r.json();
      }).catch(function (e) {
        clearTimeout(timer);
        throw e;
      });
    }
    return fetchWithTimeout(primary, opt)
      .catch(function () { if (live) usedFallback = true; return fetchWithTimeout(backup, {}); });
  }
  // статичные тяжёлые файлы (координаты станций/маршруты) — бандлом; остальные данные — live из raw
  var STATIC_DATA = { azsStations: 1, azsRoutes: 1 };
  function fetchData(key) {
    return fetchJsonPath(FILES[key], !STATIC_DATA[key]);
  }
  function loadRegionsGeo() {
    if (S.regionsGeo) { renderRegions(); return Promise.resolve(S.regionsGeo); }
    if (regionsGeoPromise) return regionsGeoPromise;
    regionsGeoPromise = fetchJsonPath("data/russia-regions.geojson").then(function (geo) {
      S.regionsGeo = geo;
      // Включаем Крым и новые территории в слой заливки регионов
      if (S.regionsGeo) {
        if (S.crimeaGeo && S.crimeaGeo.features) S.regionsGeo.features = S.regionsGeo.features.concat(S.crimeaGeo.features);
        if (S.ntGeo && S.ntGeo.features) S.regionsGeo.features = S.regionsGeo.features.concat(S.ntGeo.features);
      }
      renderRegions();
      return S.regionsGeo;
    }).catch(function () { regionsGeoPromise = null; return null; });
    return regionsGeoPromise;
  }
  function loadAzsData() {
    if (S.azsStations && S.azsRoutes) return Promise.resolve();
    if (azsDataPromise) return azsDataPromise;
    azsDataPromise = Promise.all([fetchData("azsStations").catch(function () { return null; }), fetchData("azsRoutes").catch(function () { return null; })])
      .then(function (res) { S.azsStations = res[0]; S.azsRoutes = res[1]; if (!S.azsStations || !S.azsRoutes) azsDataPromise = null; });
    return azsDataPromise;
  }
  function load() {
    if (S._loading) return;
    S._loading = true;
    return Promise.all([fetchData("state"), fetchData("hist").catch(function () { return null; }), fetchData("forecast").catch(function () { return null; }), fetchData("economy").catch(function () { return null; }), fetchData("strikes").catch(function () { return null; }), fetchData("roads").catch(function () { return null; }), fetchData("availability").catch(function () { return null; }), fetchData("voices").catch(function () { return null; }), fetchData("grid").catch(function () { return null; }), fetchData("capacityTimeline").catch(function () { return null; }), fetchData("health").catch(function () { return null; })])
      .then(function (res) {
        S.state = res[0]; S.hist = res[1]; S.forecast = res[2]; S.economy = res[3]; S.strikes = res[4]; S.roads = res[5]; S.availability = res[6]; S.voices = res[7]; S.grid = res[8]; S.capacityTimeline = res[9]; S.health = res[10];
        if (appStarted) renderAll();
        var sec = (S.state.meta && S.state.meta.refresh_seconds) || 300;
        nextSyncAt = Date.now() + sec * 1000;
        if (refreshTimer) clearTimeout(refreshTimer);
        refreshTimer = setTimeout(load, sec * 1000);
      })
      .catch(function (e) {
        console.error("feed error", e);
        document.getElementById("ticker").innerHTML = '<span style="color:#d23a2e">// ОШИБКА ЗАГРУЗКИ — повтор через 60с</span>';
        setTimeout(load, 60000);
        throw e;
      })
      .finally(function () {
        S._loading = false;
      });
  }

  function renderAll() {
    renderBalance(); renderKpiBar(); renderNpz(); renderLogistics(); renderRegions();
    renderTicker(); renderSyncMeta();
    renderRoads(); renderCrimea(); renderHistory(); renderForecast(); renderEconomy(); renderStrikes(); renderFeed(); renderPrices();
    renderAzs(); renderVoices(); renderGrid();
    loadRegionsGeo();
    if (azsReady) loadAzsData().then(renderAzsTab);
    if (crimeaReady) loadAzsData().then(renderCrimea);
  }

  /* ---------- 3D REFINERY PIECE ---------- */
  function refinerySVG(status, damaged) {
    var c = STC[status], down = status === "down";
    var smoke = "", flame = "";
    if (down || damaged) {
      smoke = '<circle class="smoke" cx="49" cy="15" r="3" fill="#5a5148"/>' +
              '<circle class="smoke s2" cx="49" cy="15" r="3.4" fill="#6b6258"/>' +
              '<circle class="smoke s3" cx="49" cy="15" r="2.6" fill="#4d453d"/>';
      flame = '<path class="flame" d="M44 50 q-3 -6 0 -10 q2 4 4 1 q3 5 -1 9 z" fill="#ff7a1a"/>' +
              '<path class="flame" d="M45 50 q-1.5 -4 0 -6 q1.5 3 2.4 0 q1.4 3 -0.6 6 z" fill="#ffd23a"/>';
    } else {
      smoke = '<circle class="smoke" cx="49" cy="15" r="2.4" fill="#cfd6d4" opacity=".5"/>' +
              '<circle class="smoke s2" cx="49" cy="15" r="2.8" fill="#dde3e1" opacity=".4"/>';
    }
    var ring = down ? '<circle class="alert-ring" cx="32" cy="50" r="14" fill="none" stroke="' + c + '" stroke-width="2"/>' : "";
    return '' +
      '<svg width="100%" height="100%" viewBox="0 0 64 64">' +
      ring +
      // base tile (iso diamond)
      '<path d="M32 60 L54 50 L32 40 L10 50 Z" fill="' + c + '" fill-opacity=".18" stroke="' + c + '" stroke-width="1.5"/>' +
      // back distillation column
      '<rect x="26" y="20" width="7" height="26" rx="3" fill="#c2b48f" stroke="#6b5d3f" stroke-width="1"/>' +
      '<ellipse cx="29.5" cy="20" rx="3.5" ry="1.6" fill="#e7ddc4" stroke="#6b5d3f" stroke-width="1"/>' +
      // storage tank (front-left)
      '<rect x="13" y="38" width="11" height="12" rx="2" fill="#d8cbac" stroke="#6b5d3f" stroke-width="1"/>' +
      '<ellipse cx="18.5" cy="38" rx="5.5" ry="2.2" fill="#ece3cc" stroke="#6b5d3f" stroke-width="1"/>' +
      // main building (3D box)
      '<path d="M34 32 L46 32 L46 50 L34 50 Z" fill="#d8cbac" stroke="#6b5d3f" stroke-width="1"/>' +
      '<path d="M46 32 L51 28 L51 46 L46 50 Z" fill="#bfae87" stroke="#6b5d3f" stroke-width="1"/>' +
      '<path d="M34 32 L39 28 L51 28 L46 32 Z" fill="#ebe1c8" stroke="#6b5d3f" stroke-width="1"/>' +
      // chimney
      '<rect x="47" y="14" width="4" height="14" fill="#a99878" stroke="#6b5d3f" stroke-width="1"/>' +
      // flag
      '<line x1="40" y1="28" x2="40" y2="13" stroke="#6b5d3f" stroke-width="1.4"/>' +
      '<path d="M40 13 L51 16 L40 19 Z" fill="' + c + '" stroke="#5a4d33" stroke-width=".6"/>' +
      smoke + flame +
      '</svg>';
  }
  function buildPiece(r) {
    var status = STC[r.status] ? r.status : "operational";
    var scale = Math.max(0.82, Math.min(1.35, 0.85 + ((Number(r.capacity_mt_year) || 10) - 10) / 42));
    var w = Math.round(54 * scale), h = Math.round(58 * scale);
    var c = STC[status], pct = Math.max(0, Math.min(100, Number(r.est_output_pct) || 0));
    var html = '<div class="npz-piece ' + esc(status) + '" style="width:' + w + 'px;height:' + h + 'px">' +
      refinerySVG(status, status === "partial") +
      '<div class="hp"><i style="width:' + pct + '%;background:' + c + '"></i></div></div>';
    return L.divIcon({ className: "", html: html, iconSize: [w, h], iconAnchor: [w / 2, h * 0.74], popupAnchor: [0, -h * 0.6] });
  }

  function countByStatus() {
    var c = { down: 0, partial: 0, operational: 0 };
    (S.state.refineries || []).forEach(function (r) { c[r.status] = (c[r.status] || 0) + 1; });
    return c;
  }

  /* ---------- MOBILE KPI STRIP ---------- */
  // компактная сводка в свёрнутом .mob-sheet (первый экран мобилки) — те же цифры, что в десктопной левой колонке
  function renderKpiBar() {
    var el = document.querySelector(".mob-sheet-kpi");
    if (!el) return;
    var nb = S.state && S.state.national_balance;
    var pct = (nb && nb.capacity_offline_pct != null) ? esc(nb.capacity_offline_pct) + "%" : "—";
    var down = S.state ? esc(countByStatus().down) : "—";
    var d7 = "—";
    if (S.strikes) {
      var cutoff = isoMinusDays(todayISO(), 6);
      d7 = strikeList().filter(function (s) { return s.date && s.date >= cutoff; }).length;
    }
    el.innerHTML = '<b>' + pct + '</b> выбито · <b>' + down + '</b> стоит · <b>' + esc(d7) + '</b> уд./7д';
  }

  /* ---------- BALANCE ---------- */
  function renderBalance() {
    if (!S.state) return;
    var nb = S.state.national_balance || {}, fb = S.state.fuel_balance || {}, c = countByStatus();
    var h = "";
    if (S.health && S.health.meta && S.health.meta.overall === "degraded") h += '<div class="note" style="border-left-color:#d23a2e;color:#d23a2e">⚠ Мониторинг: ' + esc(S.health.meta.dead_count) + ' агент(ов) не на связи (нет обновлений)</div>';
    h += '<div class="bal-big"><div class="n">' + esc(nb.capacity_offline_pct) + '%</div><div class="u">мощностей переработки выбито полностью<br>~' + esc(nb.capacity_offline_mt_year) + ' из ' + esc(nb.refining_capacity_total_mt_year) + ' млн т/год' + (nb.throughput_shortfall_pct ? ' · с учётом частично работающих недобор ~<b style="color:var(--red)">' + esc(nb.throughput_shortfall_pct) + '%</b>' : '') + '</div></div>';
    if (S.capacityTimeline && S.capacityTimeline.timeline && S.capacityTimeline.timeline.length > 1) h += sparkBlock(S.capacityTimeline.timeline);
    h += '<div style="display:flex;gap:6px;text-align:center;margin-bottom:6px">' +
      chip(c.down, "стоит", "red") + chip(c.partial, "частично", "amber") + chip(c.operational, "работает", "green") + '</div>';
    h += bar("Потери выпуска бензина", nb.gasoline_output_loss_pct, "red");
    h += bar("Потери выпуска дизеля", nb.diesel_output_loss_pct, "amber");
    h += '<div class="sect">БАЛАНС: ВНУТР. РЫНОК ⟷ ЭКСПОРТ</div>';
    if (fb.gasoline) h += splitBlock("Бензин · ~" + fb.gasoline.production_mt_year + " млн т/год", fb.gasoline);
    if (fb.diesel) h += splitBlock("Дизель · ~" + fb.diesel.production_mt_year + " млн т/год", fb.diesel);
    h += '<div class="sect">МЕРЫ</div>';
    h += kv("Экспорт бензина", nb.export_ban_gasoline ? '<span class="tag ban">ЗАПРЕТ</span>' : '<span class="tag on">ОТКР.</span>');
    h += kv("Экспорт керосина", nb.export_ban_kerosene ? '<span class="tag ban">ЗАПРЕТ</span>' : '<span class="tag on">ОТКР.</span>');
    h += kv("Импорт из Беларуси", nb.import_from_belarus ? '<span class="tag on">ДА</span>' : "—");
    if (nb.notes) h += '<div class="note">' + esc(nb.notes) + '</div>';
    if (S.state.meta && S.state.meta.confidence) h += '<div class="note">⚠ ' + esc(S.state.meta.confidence) + '</div>';
    document.getElementById("balanceBody").innerHTML = h;
  }
  function sparkBlock(tl) {
    var pts = tl.slice(-12).map(function (x) { return +x.capacity_offline_pct || 0; });
    if (pts.length < 2) return "";
    var w = 230, hh = 34, max = Math.max.apply(null, pts), min = Math.min.apply(null, pts), rng = (max - min) || 1, n = pts.length;
    var d = pts.map(function (v, i) { var x = (i / (n - 1)) * w; var y = hh - ((v - min) / rng) * (hh - 7) - 4; return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); }).join(" ");
    var first = pts[0], last = pts[n - 1], up = last >= first;
    return '<div class="spark" style="margin:0 0 8px"><div style="font-size:9px;color:var(--ink-dim);display:flex;justify-content:space-between;margin-bottom:1px"><span>динамика выбытия мощностей</span><span style="color:' + (up ? "#d23a2e" : "#2f9e57") + ';font-weight:700">' + first + '% → ' + last + '%</span></div><svg width="' + w + '" height="' + hh + '" viewBox="0 0 ' + w + ' ' + hh + '" style="width:100%;display:block"><path d="' + d + '" fill="none" stroke="#d23a2e" stroke-width="2" stroke-linejoin="round"/></svg></div>';
  }
  function chip(v, k, cls) { return '<div style="flex:1;background:var(--surface2);border-radius:8px;padding:6px 2px"><div style="font-family:var(--mono);font-weight:800;font-size:18px;color:var(--' + (cls === "red" ? "red" : cls === "amber" ? "amber" : "green") + ')">' + esc(v) + '</div><div style="font-size:9px;color:var(--ink-dim)">' + esc(k) + '</div></div>'; }
  function bar(l, p, cls) { var n = Math.min(100, Number(p) || 0); return '<div class="bar"><div class="bl"><span>' + esc(l) + '</span><span class="r">' + esc(p) + '%</span></div><div class="track"><div class="fill ' + esc(cls) + '" style="width:' + n + '%"></div></div></div>'; }
  function splitBlock(l, f) { var dom = Number(f.domestic_pct) || 0, exp = Number(f.export_pct) || 0; return '<div class="bar"><div class="bl"><span>' + esc(l) + '</span><span class="r">' + esc(f.export_status) + '</span></div><div class="split"><div class="dom" style="width:' + dom + '%">ВНУТР ' + esc(f.domestic_pct) + '%</div><div class="exp" style="width:' + exp + '%">ЭКСП ' + esc(f.export_pct) + '%</div></div></div>'; }
  function kv(k, v) { return '<div class="kv"><span>' + esc(k) + '</span><span class="v">' + v + '</span></div>'; }

  /* ---------- NPZ ---------- */
  function renderNpz() {
    if (!S.state) return;
    L_ru.npz.clearLayers();
    var list = (S.state.refineries || []).slice().sort(function (a, b) {
      var o = { down: 0, partial: 1, operational: 2 };
      return o[a.status] !== o[b.status] ? o[a.status] - o[b.status] : b.capacity_mt_year - a.capacity_mt_year;
    });
    list.forEach(function (r) {
      var m = L.marker([r.lat, r.lon], { icon: buildPiece(r), riseOnHover: true }).bindPopup(npzPopup(r), POPUP_OPTS);
      r._m = m; m.addTo(L_ru.npz);
    });
    var c = countByStatus();
    document.getElementById("npzCount").textContent = list.length;
    document.getElementById("legend").innerHTML =
      '<span><i style="background:var(--red)"></i>стоит ' + c.down + '</span>' +
      '<span><i style="background:var(--amber)"></i>частично ' + c.partial + '</span>' +
      '<span><i style="background:var(--green)"></i>работает ' + c.operational + '</span>';
    document.getElementById("npzList").innerHTML = list.map(function (r) {
      return '<div class="npz-row" role="button" tabindex="0" title="' + esc(r.name) + '" data-id="' + esc(r.id) + '"><span class="dot ' + esc(r.status) + '"></span><span class="nm">' + esc(r.name) + '</span><span class="cap">' + esc(r.capacity_mt_year) + '</span></div>';
    }).join("");
    Array.prototype.forEach.call(document.querySelectorAll(".npz-row"), function (row) {
      bindButton(row, function () {
        var r = S.state.refineries.find(function (x) { return x.id === row.dataset.id; });
        if (r && r._m) { maps.ru.flyTo([r.lat, r.lon], 6, { duration: .6 }); r._m.openPopup(); }
      });
    });
  }
  function npzPopup(r) {
    var lbl = { down: "ОСТАНОВЛЕН", partial: "ЧАСТИЧНО", operational: "РАБОТАЕТ" }[r.status];
    var h = '<div class="pp-h">' + esc(r.name) + '</div><span class="pp-st ' + esc(r.status) + '">' + esc(lbl) + '</span>';
    h += '<div class="pp-kv"><span>Оператор</span><span>' + esc(r.operator) + '</span></div>';
    h += '<div class="pp-kv"><span>Регион</span><span>' + esc(r.region) + '</span></div>';
    h += '<div class="pp-kv"><span>Мощность</span><span>' + esc(r.capacity_mt_year) + ' млн т/год</span></div>';
    h += '<div class="pp-kv"><span>Загрузка (оц.)</span><span>' + esc(r.est_output_pct) + '%</span></div>';
    if (r.status !== "operational" && r.status_since) { var _dd = Math.floor((Date.now() - new Date(r.status_since + "T00:00:00Z").getTime()) / 86400000); h += '<div class="pp-kv"><span>Статус с</span><span>' + esc(rusDate(r.status_since)) + (_dd >= 0 ? ' · <b>' + _dd + ' дн.</b>' : '') + '</span></div>'; }
    if (r.damage) h += '<div class="pp-dmg">⚠ ' + esc(r.damage) + '</div>';
    if (r.note) h += '<div class="pp-note">' + esc(r.note) + '</div>';
    if (r.source_url) h += srcHtml(r.source_url, 'источник');
    return h;
  }

  /* ---------- LOGISTICS ---------- */
  function termSVG(hit) {
    var c = hit ? "#d23a2e" : "#178585";
    var smoke = hit ? '<circle class="smoke" cx="20" cy="10" r="2.6" fill="#5a5148"/><circle class="smoke s2" cx="20" cy="10" r="3" fill="#6b6258"/>' : "";
    return '<svg class="term-piece" width="100%" height="100%" viewBox="0 0 40 40">' +
      '<path d="M20 36 L34 29 L20 22 L6 29 Z" fill="' + c + '" fill-opacity=".18" stroke="' + c + '" stroke-width="1.4"/>' +
      '<rect x="13" y="16" width="14" height="14" rx="2" fill="#d8cbac" stroke="#6b5d3f" stroke-width="1"/>' +
      '<ellipse cx="20" cy="16" rx="7" ry="2.6" fill="#ece3cc" stroke="#6b5d3f" stroke-width="1"/>' +
      '<text x="20" y="28" font-size="11" text-anchor="middle" fill="' + c + '">⚓</text>' + smoke + '</svg>';
  }
  function renderLogistics() {
    if (!S.state) return;
    L_ru.logistics.clearLayers();
    (S.state.pipelines || []).forEach(function (p) {
      var col = p.type === "product" ? "#178585" : "#8a6d3b";
      L.polyline(p.coords, { color: col, weight: 3, opacity: .65, dashArray: p.type === "product" ? "3,7" : null })
        .bindPopup('<div class="pp-h">' + esc(p.name) + '</div><div class="pp-kv"><span>Тип</span><span>' + (p.type === "product" ? "нефтепродукты" : "сырая нефть") + '</span></div>', POPUP_OPTS)
        .addTo(L_ru.logistics);
    });
    (S.state.export_terminals || []).forEach(function (t) {
      var hit = t.status === "hit";
      var icon = L.divIcon({ className: "", html: termSVG(hit), iconSize: [34, 34], iconAnchor: [17, 26] });
      var h = '<div class="pp-h">⚓ ' + esc(t.name) + '</div><span class="pp-st ' + (hit ? "hit" : "ok") + '">' + (hit ? "ПОРАЖЁН" : "РАБОТАЕТ") + '</span>';
      h += '<div class="pp-kv"><span>Тип</span><span>' + esc(t.type) + '</span></div><div class="pp-kv"><span>Регион</span><span>' + esc(t.region) + '</span></div>';
      if (t.status_since) h += '<div class="pp-kv"><span>С</span><span>' + esc(rusDate(t.status_since)) + '</span></div>';
      if (t.note) h += '<div class="pp-note">' + esc(t.note) + '</div>';
      L.marker([t.lat, t.lon], { icon: icon }).bindPopup(h, POPUP_OPTS).addTo(L_ru.logistics);
    });
  }

  /* ---------- ROADS (fuel arteries) ---------- */
  function roadPopup(rd) {
    var st = { threatened: "ПОД УДАРАМИ", cut: "ПЕРЕРЕЗАНА", ok: "РАБОТАЕТ" }[rd.status] || rd.status;
    var h = '<div class="pp-h">🛣 ' + esc(rd.name) + '</div><span class="pp-st ' + (rd.status === "ok" ? "operational" : rd.status === "cut" ? "down" : "partial") + '">' + esc(st) + '</span>';
    if (rd.note) h += '<div class="pp-dmg">' + esc(rd.note) + '</div>';
    if (rd.source_url) h += srcHtml(rd.source_url, 'источник');
    return h;
  }
  function hotspotPopup(hp) {
    var h = '<div class="pp-h">⚠ ' + esc(hp.name) + '</div><div class="pp-dmg">' + esc(hp.note || "") + '</div>';
    if (hp.source_url) h += srcHtml(hp.source_url, 'новость');
    return h;
  }
  function renderRoads() {
    if (!L_ru.roads) return;
    L_ru.roads.clearLayers();
    if (L_ru.hotspots) L_ru.hotspots.clearLayers();
    var r = S.roads; if (!r) return;
    (r.roads || []).forEach(function (rd) {
      if (!rd.coords || !rd.coords.length) return;
      var opts;
      if (rd.status === "threatened") opts = { color: "#d23a2e", weight: 4, opacity: .92, className: "road-threatened" };
      else if (rd.status === "cut") opts = { color: "#7a1610", weight: 4, opacity: .9, dashArray: "2,9" };
      else opts = { color: "#5b5650", weight: 3, opacity: .7 };
      L.polyline(rd.coords, opts).bindPopup(roadPopup(rd), POPUP_OPTS).addTo(L_ru.roads);
    });
    (r.hotspots || []).forEach(function (hp) {
      if (typeof hp.lat !== "number") return;
      var icon = L.divIcon({ className: "", html: '<div class="hotspot">⚠️</div>', iconSize: [24, 24], iconAnchor: [12, 12] });
      L.marker([hp.lat, hp.lon], { icon: icon, zIndexOffset: 550 }).bindPopup(hotspotPopup(hp), POPUP_OPTS).addTo(L_ru.hotspots || L_ru.roads);
    });
  }

  /* ---------- REGIONS SHADING (now / forecast) ---------- */
  function loadColor(level) {
    if (level === "critical") return "#9a1f16";
    if (level === "severe") return "#d23a2e";
    if (level === "high" || level === "medium") return "#e8911c";
    return "#3fa05a"; // нет нагрузки / low → зелёный
  }
  function normRegion(s) {
    return (s || "").toLowerCase().replace(/ё/g, "е")
      .replace(/республика|область|обл\.?|край|автономный округ|автономная|город|г\./g, "")
      .replace(/[^а-я]/g, "");
  }
  var REGION_ALIAS = { "ленобласть": "ленинградская", "питер": "санктпетербург" };
  function regKeys(name) {
    return name.split("/").map(function (p) { var k = normRegion(p); return REGION_ALIAS[k] || k; });
  }
  function buildLoadMap() {
    var map = {}, isF = regionMode === "forecast", src;
    if (isF && S.forecast && S.forecast.region_forecast)
      src = S.forecast.region_forecast.map(function (d) { return { region: d.region, level: d.level, note: d.note }; });
    else
      src = (S.state.deficit_regions || []).map(function (d) { return { region: d.region, level: d.level, note: d.restriction + (d.since ? " (с " + rusDate(d.since) + ")" : "") }; });
    var ord = { low: 1, medium: 2, high: 3, severe: 4, critical: 5 };
    src.forEach(function (d) {
      regKeys(d.region).forEach(function (k) {
        if (!map[k] || (ord[d.level] || 0) > (ord[map[k].level] || 0)) map[k] = { level: d.level, note: d.note, region: d.region };
      });
    });
    return map;
  }
  function renderBorder() {
    if (!S.outlineGeo || !L_ru.border) return;
    L_ru.border.clearLayers();
    L.geoJSON(S.outlineGeo, { style: { color: "#23408e", weight: 2.5, fill: false, opacity: .85 }, interactive: false }).addTo(L_ru.border);
    // Крым и новые территории — пунктирная граница (de-facto контроль)
    var dashStyle = { color: "#23408e", weight: 2.5, fill: false, opacity: .85, dashArray: "5,4" };
    if (S.crimeaGeo) L.geoJSON(S.crimeaGeo, { style: dashStyle, interactive: false }).addTo(L_ru.border);
    if (S.ntGeo) L.geoJSON(S.ntGeo, { style: dashStyle, interactive: false }).addTo(L_ru.border);
  }
  function effInfo(f, lm) {
    var info = lm[normRegion(f.properties.name)];
    if (!info && f.properties && f.properties.nt)
      info = { level: "high", nt: true, note: "Новая территория (под контролем РФ). Прифронтовая зона: логистика топлива под угрозой ударов, приоритет ГСМ для нужд обороны." };
    return info;
  }
  function renderRegions() {
    if (!S.regionsGeo || !S.state || !L_ru.regions) return;
    L_ru.regions.clearLayers();
    var lm = buildLoadMap();
    L.geoJSON(S.regionsGeo, {
      style: function (f) {
        var info = effInfo(f, lm);
        return { color: "#7a7e85", weight: .5, fillColor: loadColor(info ? info.level : "normal"), fillOpacity: info ? .5 : .26 };
      },
      onEachFeature: function (f, layer) {
        var info = effInfo(f, lm);
        var st = info ? (info.level === "critical" || info.level === "severe" ? "down" : "partial") : "operational";
        var lbl = info ? info.level.toUpperCase() : "НЕТ НАГРУЗКИ";
        var tag = (f.properties && f.properties.nt) ? ' <span class="pp-st partial">НОВАЯ ТЕРР.</span>' : '';
        layer.bindPopup('<div class="pp-h">' + esc(f.properties.name) + '</div><span class="pp-st ' + esc(st) + '">' + esc(lbl) + '</span>' + tag + (info && info.note ? '<div class="pp-note">' + esc(info.note) + '</div>' : ''), POPUP_OPTS);
      }
    }).addTo(L_ru.regions);
  }

  /* ---------- PRICE HEATMAP (АИ-95 по регионам) ---------- */
  function priceColor(p) {
    if (!p) return "#9aa0a6";
    if (p >= 95) return "#a01d14"; if (p >= 86) return "#d23a2e"; if (p >= 79) return "#e07a18";
    if (p >= 73) return "#e8b020"; if (p >= 67) return "#9fc63a"; return "#2f9e57";
  }
  function renderPrices() {
    if (!L_ru.prices) return;
    L_ru.prices.clearLayers();
    var a = S.availability; if (!a || !a.regions) return;
    a.regions.forEach(function (r) {
      var p = r.ai95_price_rub; if (!p || typeof r.lat !== "number") return;
      var c = priceColor(p);
      L.marker([r.lat, r.lon], { icon: L.divIcon({ className: "", html: '<div style="background:' + c + ';color:#fff;font:700 11px/1 var(--mono),monospace;padding:3px 5px;border-radius:5px;border:1px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.45);white-space:nowrap">' + p + '₽</div>', iconSize: [36, 18], iconAnchor: [18, 9] }), zIndexOffset: 350 })
        .bindPopup('<div class="pp-h">💰 ' + esc(r.region) + '</div><div class="pp-kv"><span>АИ-95</span><span>' + esc(p) + ' ₽/л</span></div>' + (r.diesel_price_rub ? '<div class="pp-kv"><span>ДТ</span><span>' + esc(r.diesel_price_rub) + ' ₽/л</span></div>' : '') + (r.queues_hours ? '<div class="pp-kv"><span>Очередь</span><span>~' + esc(r.queues_hours) + ' ч</span></div>' : ''), POPUP_OPTS)
        .addTo(L_ru.prices);
    });
  }

  /* ---------- CRIMEA ---------- */
  // data-drift защита: генератор history-crimea.json (Haiku, agents/update-prompt-history.md) иногда
  // отдаёт restrictions объектом вместо массива → .forEach падал в цикле рендера. Терпим любую форму
  // и раскладываем объект в строки, ничего не теряя. ponytail: корень — в промпте генератора, тут страховка на фронте.
  var CRIMEA_R_LBL = { fuel_rationing: "Нормирование топлива", max_liters_per_day: "Лимит, л/сутки", sales_status: "Продажи", official_price_rub_per_liter: "Офиц. цена, ₽/л", black_market_price_rub_per_liter: "Чёрный рынок, ₽/л", priority_allocation: "Приоритетный отпуск", effective_since: "Действует с" };
  function crimeaRestrictions(cr) {
    var r = cr.restrictions;
    if (Array.isArray(r)) return r;
    if (r && typeof r === "object") return Object.keys(r).map(function (k) {
      var v = r[k];
      if (Array.isArray(v)) v = v.join(", "); else if (typeof v === "boolean") v = v ? "да" : "нет";
      return { text: (CRIMEA_R_LBL[k] || k.replace(/_/g, " ")) + ": " + v };
    });
    if (typeof r === "string" && r) return [r];
    return [];
  }
  function renderCrimea() {
    var cr = S.hist && S.hist.crimea;
    var body = document.getElementById("crimeaBody");
    if (!cr) { body.innerHTML = '<div class="note">Данные по Крыму загружаются…</div>'; return; }
    var h = '<div class="csum">' + esc(cr.summary) + '</div>';
    h += '<div class="sect">ОГРАНИЧЕНИЯ</div>';
    crimeaRestrictions(cr).forEach(function (r) {
      var pre = (r && r.date) ? esc(rusDate(r.date)) + ' — ' : '';
      var src = (r && r.source_url) ? ' <a href="' + safeUrl(r.source_url) + '" target="_blank" rel="noopener" style="font-size:10px;color:var(--teal)">источник ↗</a>' : '';
      h += '<div class="crow"><span class="ci">⛔</span><span>' + pre + esc(r && r.text ? r.text : r) + src + '</span></div>';
    });
    h += '<div class="sect">АЗС / ГОРОДА</div><div class="cstations">';
    (cr.stations || []).forEach(function (s) { h += '<div class="cst"><span>📍 ' + esc(s.name) + ' <span style="color:var(--ink-dim);font-size:11px">' + esc(s.note || s.details) + '</span></span><span class="cb ' + esc(s.status) + '">' + esc(String(s.status || "").toUpperCase()) + '</span></div>'; });
    h += '</div>';
    // C: сводка по сети АЗС Крыма — те же уровни/цвета, что на вкладке АЗС (даёт конкретику на карте)
    if (S.azsStations && S.azsStations.stations) {
      var cst = S.azsStations.stations.filter(function (s) { return /крым|севастополь/i.test(s.region || ""); });
      if (cst.length) {
        var cc = {}; cst.forEach(function (s) { var lv = stationLevel(s); cc[lv] = (cc[lv] || 0) + 1; });
        var lo = ["calm", "strained", "limited", "severe", "critical"];
        var leg = lo.filter(function (k) { return cc[k]; }).map(function (k) { return '<span style="white-space:nowrap"><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + AZS_LVL[k] + ';margin-right:3px;vertical-align:middle"></i>' + esc(AZS_LBL[k]) + ' ' + cc[k] + '</span>'; }).join(' · ');
        if (cc.unknown) leg += (leg ? ' · ' : '') + '<span style="white-space:nowrap"><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + AZS_UNKNOWN + ';margin-right:3px;vertical-align:middle"></i>нет данных ' + cc.unknown + '</span>';
        h += '<div class="sect">СЕТЬ АЗС КРЫМА · ' + cst.length + ' на карте</div><div style="display:flex;flex-wrap:wrap;gap:7px;font-size:11px;padding:2px 0 4px;font-weight:600">' + leg + '</div>';
      }
    }
    if (cr.outlook) h += '<div class="coutlook">🔮 ' + esc(cr.outlook) + '</div>';
    body.innerHTML = h;

    if (crimeaReady) {
      // заливка полуострова — та же логика цвета, что и на основной карте (buildLoadMap/effInfo/loadColor)
      if (S.crimeaGeo && L_cr.fill) {
        L_cr.fill.clearLayers();
        var lm = buildLoadMap();
        L.geoJSON(S.crimeaGeo, {
          style: function (f) {
            var info = effInfo(f, lm);
            return { color: "#7a7e85", weight: 1, fillColor: loadColor(info ? info.level : "normal"), fillOpacity: info ? .5 : .3 };
          },
          onEachFeature: function (f, layer) {
            var info = effInfo(f, lm);
            var st = info ? (info.level === "critical" || info.level === "severe" ? "down" : "partial") : "operational";
            var lbl = info ? info.level.toUpperCase() : "НЕТ НАГРУЗКИ";
            layer.bindPopup('<div class="pp-h">' + esc(f.properties.name) + '</div><span class="pp-st ' + esc(st) + '">' + esc(lbl) + '</span>' + (info && info.note ? '<div class="pp-note">' + esc(info.note) + '</div>' : ''), POPUP_OPTS);
          }
        }).addTo(L_cr.fill);
      }
      L_cr.layer.clearLayers();
      (cr.routes || []).forEach(function (rt) {
        if (!Array.isArray(rt.coords)) return; // drift: маршрут без coords — на карте не рисуем (текст всё равно в списке выше)
        var col = rt.status === "threatened" ? "#d23a2e" : rt.status === "cut" ? "#a01d14" : "#178585";
        L.polyline(rt.coords, { color: col, weight: 4, opacity: .8, dashArray: "6,8" })
          .bindPopup('<div class="pp-h">' + esc(rt.name) + '</div><span class="pp-st down">' + esc(String(rt.status || "").toUpperCase()) + '</span><div class="pp-note">' + esc(rt.note || rt.details) + '</div>', POPUP_OPTS)
          .addTo(L_cr.layer);
      });
      (cr.stations || []).forEach(function (s) {
        if (typeof s.lat !== "number" || typeof s.lon !== "number") return; // drift: станция без координат — только в списке выше
        var c = s.status === "dry" ? "#a01d14" : s.status === "ok" ? "#2f9e57" : "#df8f17";
        L.marker([s.lat, s.lon], { icon: L.divIcon({ className: "", html: '<div style="background:' + c + ';color:#fff;font-weight:800;font-size:11px;padding:3px 8px;border-radius:8px;box-shadow:0 3px 8px rgba(0,0,0,.35);white-space:nowrap">⛽ ' + esc(s.name) + '</div>', iconSize: [128, 24], iconAnchor: [64, 18] }) })
          .bindPopup('<div class="pp-h">⛽ ' + esc(s.name) + '</div><span class="pp-st ' + esc(s.status) + '">' + esc(String(s.status || "").toUpperCase()) + '</span><div class="pp-note">' + esc(s.note || s.details) + '</div>', POPUP_OPTS)
          .addTo(L_cr.layer);
      });
      // АЗС-сеть — те же иконки/уровни/попапы, что и на вкладке АЗС (data/azs-stations.json)
      if (S.azsStations && L_cr.azs) {
        L_cr.azs.clearLayers();
        (S.azsStations.stations || []).forEach(function (s) {
          if (!/крым|севастополь/i.test(s.region || "")) return;
          L.marker([s.lat, s.lon], { icon: azsStationIcon(stationLevel(s), false) })
            .bindPopup(azsStationPopup(s), POPUP_OPTS)
            .addTo(L_cr.azs);
        });
      }
    }
  }

  /* ---------- HISTORY ---------- */
  var histFilter = "all";
  function renderHistory() {
    var box = document.getElementById("timeline");
    if (!S.hist || !S.hist.history) { box.innerHTML = '<div class="note">История загружается…</div>'; return; }
    var items = S.hist.history.filter(function (e) { return histFilter === "all" || e.type === histFilter; });
    var TL = { strike: "🔥 удар", repair: "🛠 ремонт", restriction: "⛔ ограничение", policy: "📋 мера" };
    box.innerHTML = items.map(function (e) {
      return '<div class="tl-item ' + esc(e.type) + '"><span class="tl-date">' + esc(rusDate(e.date)) + '</span><span class="tl-type ' + esc(e.type) + '">' + esc(TL[e.type] || e.type) + '</span>' +
        '<div class="tl-title">' + esc(e.title) + '</div><div class="tl-detail">' + esc(e.detail) + (e.region ? ' <i style="color:var(--ink-dim)">· ' + esc(e.region) + '</i>' : "") +
        (e.source_url ? ' <a href="' + safeUrl(e.source_url) + '" target="_blank" rel="noopener">источник ↗</a>' : "") + '</div></div>';
    }).join("") || '<div class="note">Нет событий по фильтру.</div>';

    var rb = document.getElementById("repairedBox");
    if (S.hist.repaired && S.hist.repaired.length) {
      rb.innerHTML = '<h3>🛠 Восстановленные / частично перезапущенные НПЗ</h3>' + S.hist.repaired.map(function (r) {
        return '<div class="ri"><b>' + esc(r.name) + '</b> · ' + esc(r.repaired_date) + ' — ' + esc(r.detail) + (r.source_url ? ' <a href="' + safeUrl(r.source_url) + '" target="_blank" rel="noopener" style="color:var(--teal)">↗</a>' : "") + '</div>';
      }).join("");
    } else rb.innerHTML = "";
  }

  /* ---------- FORECAST ---------- */
  function renderForecast() {
    var f = S.forecast;
    if (!f) { document.getElementById("scenarios").innerHTML = '<div class="note">Прогноз загружается…</div>'; return; }
    document.getElementById("scenarios").innerHTML = (f.scenarios || []).map(function (s) {
      return '<div class="scn ' + esc(s.id) + '"><div class="sp">' + esc(s.probability_pct) + '%</div><div class="snm">' + esc(s.name) + '</div><div class="sh">' + esc(s.horizon) + '</div><div class="ss">' + esc(s.summary) + '</div></div>';
    }).join("");
    var t = '<thead><tr><th>Горизонт</th><th>Топливо</th><th>Цены</th><th>Экономика</th><th>АПК</th><th>Социум</th><th></th></tr></thead><tbody>';
    (f.table || []).forEach(function (r) {
      t += '<tr><td>' + esc(r.horizon) + '</td><td>' + esc(r.fuel) + '</td><td>' + esc(r.prices) + '</td><td>' + esc(r.economy) + '</td><td>' + esc(r.agriculture || "—") + '</td><td>' + esc(r.social || "—") + '</td><td><span class="sev-badge sev-' + esc(r.severity) + '">' + esc(r.severity) + '</span></td></tr>';
    });
    document.getElementById("forecastTable").innerHTML = t + '</tbody>';
    document.getElementById("econChain").innerHTML = (f.economic_chain || []).map(function (s, i) {
      return '<div class="step"><div class="sn">' + (i + 1) + '</div><div class="sc"><div class="st">' + esc(String(s.stage || "").replace(/^\d+\.\s*/, "")) + '</div><div class="se">' + esc(s.effect) + '</div></div></div>';
    }).join("");
  }

  /* ---------- ECONOMY ---------- */
  function ecoBlock(b) {
    if (!b) return "";
    var h = '<div class="eco-h">' + esc(b.title) + ' <span class="eco-oil-pill">нефтегаз ~' + esc(b.oil_gas_pct) + '%</span></div>';
    h += (b.items || []).map(function (it) {
      return '<div class="eco-bar"><div class="eco-bl"><span>' + (it.oil ? "🛢 " : "") + esc(it.name) + '</span><span>' + esc(it.pct) + '%</span></div>' +
        '<div class="eco-track"><div class="eco-fill' + (it.oil ? " oil" : "") + '" style="width:' + (Number(it.pct) || 0) + '%"></div></div>' +
        (it.note ? '<div class="eco-note">' + esc(it.note) + '</div>' : "") + '</div>';
    }).join("");
    return h;
  }
  function renderEconomy() {
    var e = S.economy;
    var bud = document.getElementById("ecoBudget"), exp = document.getElementById("ecoExports"),
        imp = document.getElementById("ecoImpact"), hl = document.getElementById("ecoHighlight");
    if (!e) { if (bud) bud.innerHTML = '<div class="note">Инфографика доходов загружается…</div>'; return; }
    bud.innerHTML = ecoBlock(e.budget);
    exp.innerHTML = ecoBlock(e.exports);
    imp.innerHTML = (e.impact || []).map(function (i) {
      return '<div class="imp ' + esc(i.severity) + '"><div class="imp-h">' + esc(i.label) + ' <span class="sev-badge sev-' + esc(i.severity) + '">' + esc(i.severity) + '</span></div><div class="imp-d">' + esc(i.detail) + '</div></div>';
    }).join("");
    hl.innerHTML = '⚠ ' + esc(e.highlight || "");
  }

  /* ---------- STRIKES (by day) ---------- */
  var MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  function fmtDay(d) { if (!d) return "—"; var p = d.split("-"); return parseInt(p[2], 10) + " " + (MONTHS[parseInt(p[1], 10) - 1] || ""); }
  function rusDate(d) { if (!d) return ""; var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(d)); if (!m) return d; return parseInt(m[3], 10) + " " + (MONTHS[parseInt(m[2], 10) - 1] || "") + " " + m[1]; }
  function plural(n) { var a = n % 10, b = n % 100; if (a === 1 && b !== 11) return ""; if (a >= 2 && a <= 4 && (b < 10 || b >= 20)) return "а"; return "ов"; }
  function explosionPts(cx, cy, spikes, ro, ri) {
    var p = [], step = Math.PI / spikes;
    for (var i = 0; i < 2 * spikes; i++) {
      var r = (i % 2 === 0) ? ro : ri, a = i * step - Math.PI / 2;
      p.push((cx + r * Math.cos(a)).toFixed(1) + "," + (cy + r * Math.sin(a)).toFixed(1));
    }
    return p.join(" ");
  }
  function strikeMarker(s, hot) {
    var missile = (s.type === "missile" || s.type === "both");
    var outer = missile ? "#a00a0a" : "#d8170d";  // ракета — тёмно-красный, БПЛА — красный
    var mid = missile ? "#e6451a" : "#ff7019";
    var size = hot ? 32 : 24;
    // Язык пламени с белой контрастной обводкой, чтобы читался поверх НПЗ-фишек
    var flameOuter = "M16 1.5 C20.5 7 25 11 24 17.5 C23 24 18.5 27.5 16 31 C13.5 27.5 9 24 8 17.5 C7 11 11.5 7 16 1.5 Z";
    var flameMid = "M16 7 C18.5 11 22 14 21 19 C20 23.5 17.5 25.5 16 28 C14.5 25.5 12 23.5 11 19 C10 14 13.5 11 16 7 Z";
    var flameCore = "M16 13 C17.4 16 19 17.5 18.4 20 C17.8 22 16.7 23.5 16 25.5 C15.3 23.5 14.2 22 13.6 20 C13 17.5 14.6 16 16 13 Z";
    var pulse = hot ? '<path class="strike-pulse" d="' + flameOuter + '" fill="none" stroke="' + outer + '" stroke-width="2"/>' : "";
    var html = '<div class="strike flame ' + (hot ? "hot" : "") + '">' +
      '<svg width="' + size + '" height="' + size + '" viewBox="0 0 32 32">' +
      pulse +
      // белая контрастная обводка по контуру пламени
      '<path d="' + flameOuter + '" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/>' +
      '<path d="' + flameOuter + '" fill="' + outer + '" stroke="#5a0303" stroke-width=".6" stroke-linejoin="round"/>' +
      '<path d="' + flameMid + '" fill="' + mid + '"/>' +
      '<path d="' + flameCore + '" fill="#ffd255"/>' +
      '</svg></div>';
    return L.divIcon({ className: "", html: html, iconSize: [size, size], iconAnchor: [size / 2, size * 0.78], popupAnchor: [0, -size * 0.5] });
  }
  function strikePopup(s) {
    var tl = { drone: "БПЛА", missile: "РАКЕТЫ", both: "БПЛА + РАКЕТЫ" }[s.type] || s.type;
    var h = '<div class="pp-h">' + esc(s.city || "") + (s.region ? ' · ' + esc(s.region) : "") + '</div>';
    h += '<span class="pp-st ' + (s.type === "drone" ? "partial" : "down") + '">💥 ' + esc(tl) + (s.count ? ' ×' + esc(s.count) : "") + '</span>';
    h += '<div class="pp-kv"><span>Дата</span><span>' + esc(fmtDay(s.date)) + (s.time ? ', ' + esc(s.time) : '') + '</span></div>';
    if (s.target) h += '<div class="pp-kv"><span>Цель</span><span>' + esc(s.target) + '</span></div>';
    if (s.casualties) h += '<div class="pp-kv"><span>Последствия</span><span>' + esc(s.casualties) + '</span></div>';
    if (s.title) h += '<div class="pp-dmg">' + esc(s.title) + '</div>';
    if (s.detail) h += '<div class="pp-note">' + esc(s.detail) + '</div>';
    if (s.source_url) h += srcHtml(s.source_url, 'читать новость');
    return h;
  }
  /* ---------- EXPAND PANELS (click a card → read it full-size) ---------- */
  var _detailPrevFocus = null;
  function _detailKeydown(e) {
    if (e.key === "Escape") { closeDetail(); return; }
    if (e.key !== "Tab") return;
    var ov = document.getElementById("detailModal"); if (!ov) return;
    var focusable = ov.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  function ensureDetail() {
    var ov = document.getElementById("detailModal");
    if (ov) return ov;
    ov = document.createElement("div");
    ov.id = "detailModal"; ov.className = "detail-modal"; ov.setAttribute("hidden", "");
    ov.innerHTML = '<div class="detail-card" role="dialog" aria-modal="true">' +
      '<button type="button" class="detail-close" aria-label="Закрыть">✕</button>' +
      '<div class="detail-body"></div></div>';
    document.body.appendChild(ov);
    ov.addEventListener("click", function (e) { if (e.target === ov) closeDetail(); });
    ov.querySelector(".detail-close").addEventListener("click", closeDetail);
    return ov;
  }
  function openDetail(html) {
    var ov = ensureDetail();
    ov.querySelector(".detail-body").innerHTML = html;
    _detailPrevFocus = document.activeElement;
    ov.removeAttribute("hidden");
    document.addEventListener("keydown", _detailKeydown);
    var c = ov.querySelector(".detail-close"); if (c) c.focus();
  }
  function closeDetail() {
    var ov = document.getElementById("detailModal"); if (!ov) return;
    ov.setAttribute("hidden", "");
    document.removeEventListener("keydown", _detailKeydown);
    if (_detailPrevFocus && _detailPrevFocus.focus) { try { _detailPrevFocus.focus(); } catch (e) {} }
  }
  function openPanelExpand(bodyEl, title, cls) {
    if (!bodyEl) return;
    openDetail('<div class="exp-title">' + esc(title) + '</div>' +
      '<div class="exp-body ' + (cls || "") + '">' + bodyEl.innerHTML + '</div>');
  }
  // ponytail: Крым/АЗС карточки не сворачивались на мобиле (до 74% экрана перманентно закрыто);
  // клик по заголовку сворачивает тело (как .panel-h в radar.html), на мобиле стартуют свёрнутыми
  function initCardCollapse() {
    ["crimeaPanel", "azsPanel", "azsCommentsCard"].forEach(function (id) {
      var card = document.getElementById(id); if (!card) return;
      var head = card.querySelector(".card-h"); if (!head) return;
      if (window.innerWidth <= 820) card.classList.add("collapsed");
      head.setAttribute("aria-expanded", card.classList.contains("collapsed") ? "false" : "true");
      bindButton(head, function () {
        var collapsed = card.classList.toggle("collapsed");
        head.setAttribute("aria-expanded", collapsed ? "false" : "true");
      });
    });
  }
  function initPanelExpand() {
    [["panelLeft", "НАЦИОНАЛЬНЫЙ БАЛАНС", "balanceBody", ""],
     ["panelFeed", "📰 ЛЕНТА УДАРОВ", "feedList", "exp-feed"],
     ["panelVoices", "🗣 ГОЛОСА ЛЮДЕЙ", "voicesList", "exp-voices"]
    ].forEach(function (p) {
      var panel = document.getElementById(p[0]); if (!panel) return;
      var head = panel.querySelector(".card-h"); if (!head) return;
      if (!head.querySelector(".card-expand")) {
        var ic = document.createElement("span");
        ic.className = "card-expand"; ic.setAttribute("aria-hidden", "true"); ic.textContent = "⤢";
        head.appendChild(ic);
        head.classList.add("card-h--clickable");
      }
      bindButton(head, function () { openPanelExpand(document.getElementById(p[2]), p[1], p[3]); });
    });
  }

  function strikeList() {
    var arr = (S.strikes && S.strikes.strikes) || [];
    // новые коллекторы пишут location:[lat,lon] и description — нормализуем к старой схеме (lat/lon, detail)
    arr.forEach(function (s) {
      if (typeof s.lat !== "number" && s.location && s.location.length === 2) { s.lat = +s.location[0]; s.lon = +s.location[1]; }
      if (!s.detail && s.description) s.detail = s.description;
    });
    return arr;
  }
  function buildStrikeDates() {
    var set = {}; strikeList().forEach(function (s) { set[s.date] = 1; });
    SK.dates = Object.keys(set).sort();
    if (SK.idx > SK.dates.length - 1) SK.idx = SK.dates.length - 1;
    if (SK.idx < 0) SK.idx = 0;
  }
  function todayISO() { return new Date().toISOString().slice(0, 10); }
  function isoMinusDays(iso, n) {
    var d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() - n);
    return d.toISOString().slice(0, 10);
  }
  function prevMonthRange(iso) {
    var d = new Date(iso + "T00:00:00Z");
    var firstThis = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
    var lastPrev = new Date(firstThis.getTime() - 86400000);
    var firstPrev = new Date(Date.UTC(lastPrev.getUTCFullYear(), lastPrev.getUTCMonth(), 1));
    return { from: firstPrev.toISOString().slice(0, 10), to: lastPrev.toISOString().slice(0, 10) };
  }
  // диапазон [from,to] для текущего режима (кроме поштучного "day")
  function modeRange() {
    var today = todayISO();
    if (SK.mode === "prevmonth") return prevMonthRange(today);
    if (SK.mode === "range") {
      var lo = SK.from || (SK.dates[0] || today), hi = SK.to || (SK.dates[SK.dates.length - 1] || today);
      if (lo > hi) { var t = lo; lo = hi; hi = t; }
      return { from: lo, to: hi };
    }
    var days = SK.mode === "30d" ? 29 : SK.mode === "today" ? 0 : 6;
    return { from: isoMinusDays(today, days), to: today };
  }
  function shownStrikes() {
    var list = strikeList();
    if (SK.mode === "day") { var day = SK.dates[SK.idx]; return list.filter(function (s) { return s.date === day; }); }
    if (SK.mode === "all") return list;
    var r = modeRange();
    return list.filter(function (s) { return s.date >= r.from && s.date <= r.to; });
  }
  // маркер+попап на удар пересоздавать дорого (архив ~150) — кэшируем по id, таймлайн просто
  // переключает видимость (addLayer/removeLayer) вместо clearLayers+пересборки на каждый шаг.
  // fp = снимок записи: правка опубликованного удара (sanitize и т.п.) обновляет маркер, а не отдаёт кэш.
  var strikeMarkerCache = {};
  function renderStrikes() {
    if (!L_ru.strikes) return;
    buildStrikeDates();
    var shown = shownStrikes(), hot = SK.mode === "day" || SK.mode === "today";
    var shownIds = {};
    renderedStrikes = [];
    shown.forEach(function (s) {
      if (typeof s.lat !== "number" || typeof s.lon !== "number") return;
      var id = s.id || (s.date + "|" + s.lat + "|" + s.lon + "|" + (s.time || ""));
      shownIds[id] = 1;
      var cached = strikeMarkerCache[id];
      var fp = JSON.stringify(s);
      if (!cached) {
        var m = L.marker([s.lat, s.lon], { icon: strikeMarker(s, hot), zIndexOffset: 600 }).bindPopup(strikePopup(s), POPUP_OPTS);
        cached = strikeMarkerCache[id] = { marker: m, hot: hot, fp: fp };
      } else if (cached.fp !== fp) {
        cached.marker.setLatLng([s.lat, s.lon]).setIcon(strikeMarker(s, hot)).setPopupContent(strikePopup(s));
        cached.hot = hot; cached.fp = fp;
      } else if (cached.hot !== hot) {
        cached.marker.setIcon(strikeMarker(s, hot));
        cached.hot = hot;
      }
      if (!L_ru.strikes.hasLayer(cached.marker)) L_ru.strikes.addLayer(cached.marker);
      renderedStrikes.push({ s: s, marker: cached.marker });
    });
    Object.keys(strikeMarkerCache).forEach(function (id) {
      if (shownIds[id]) return;
      var mk = strikeMarkerCache[id].marker;
      if (L_ru.strikes.hasLayer(mk)) L_ru.strikes.removeLayer(mk);
    });
    updateStrikeBar();
  }

  /* ---------- STRIKE CANDIDATES (radar tripwire, unconfirmed rumor) ---------- */
  // ponytail: маркер полностью инлайн (без classов), чтобы не трогать styles.css.
  // Амбер + пунктир + «?» = сигнал «возможный удар, НЕ подтверждён» — визуально отделён от
  // сплошного красного пламени подтверждённых ударов.
  function candidateMarker() {
    var flame = "M16 1.5 C20.5 7 25 11 24 17.5 C23 24 18.5 27.5 16 31 C13.5 27.5 9 24 8 17.5 C7 11 11.5 7 16 1.5 Z";
    var html = '<div class="strike-cand" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">' +
      '<svg width="26" height="26" viewBox="0 0 32 32">' +
      '<path d="' + flame + '" fill="rgba(240,165,0,.16)" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/>' +
      '<path d="' + flame + '" fill="rgba(240,165,0,.16)" stroke="#f0a500" stroke-width="2" stroke-dasharray="3 2.4" stroke-linejoin="round"/>' +
      '<text x="16" y="21" text-anchor="middle" font-size="15" font-weight="800" fill="#f0a500" font-family="system-ui,Arial,sans-serif">?</text>' +
      '</svg></div>';
    return L.divIcon({ className: "", html: html, iconSize: [26, 26], iconAnchor: [13, 20], popupAnchor: [0, -16] });
  }
  function candidatePopup(c) {
    var h = '<div class="pp-h">' + esc(c.city || "город не определён") + (c.region ? ' · ' + esc(c.region) : "") + '</div>';
    h += '<span class="pp-st partial" style="background:rgba(240,165,0,.18);color:#f0a500;border-color:#f0a500">❓ КАНДИДАТ · НЕ ПОДТВЕРЖДЁН</span>';
    h += '<div class="pp-kv"><span>Когда</span><span>' + esc(fmtDay(c.date)) + (c.time_local ? ', ' + esc(c.time_local) : (c.time ? ', ' + esc(c.time) : '')) + '</span></div>';
    if (c.target) h += '<div class="pp-kv"><span>Цель</span><span>' + esc(c.target) + '</span></div>';
    if (c.detail) h += '<div class="pp-note">' + esc(c.detail) + '</div>';
    h += '<div class="pp-src" style="opacity:.85">🛰 сигнал с ленты <b>radar-map.ru</b> · требует подтверждения (GDELT/FIRMS)</div>';
    return h;
  }
  function renderCandidates() {
    if (!L_ru.candidates) return;
    L_ru.candidates.clearLayers();
    var arr = (S.candidates && S.candidates.candidates) || [];
    arr.forEach(function (c) {
      if (typeof c.lat !== "number" || typeof c.lon !== "number") return;
      L.marker([c.lat, c.lon], { icon: candidateMarker(), zIndexOffset: 500 })
        .bindPopup(candidatePopup(c), POPUP_OPTS)
        .addTo(L_ru.candidates);
    });
  }
  function loadCandidates() {
    // live=true → raw github первым (cache-bust), как strikes: слой подхватывает свежих
    // кандидатов, которые VPS-крон strike-candidates.py пушит ежечасно, без редеплоя сайта.
    return fetchJsonPath(FILES.candidates, true)
      .then(function (j) { S.candidates = j; renderCandidates(); })
      .catch(function () { /* нет файла/пусто — слой просто пустой */ });
  }

  /* ---------- STRIKE NEWS FEED (column tied to map) ---------- */
  function typeShort(t) { return t === "missile" ? "ракета" : t === "both" ? "БПЛА+ракета" : "БПЛА"; }
  function renderFeed() {
    var el = document.getElementById("feedList"); if (!el) return;
    feedSorted = strikeList().slice().sort(function (a, b) {
      if (a.date !== b.date) return a.date < b.date ? 1 : -1;
      var ta = a.time || "", tb = b.time || "";
      return ta < tb ? 1 : (ta > tb ? -1 : 0);
    });
    var cnt = document.getElementById("feedCount"); if (cnt) cnt.textContent = feedSorted.length;
    el.innerHTML = feedSorted.map(function (s, i) {
      return '<div class="feed-item ' + esc(s.type) + '" role="button" tabindex="0" data-fi="' + i + '">' +
        '<div class="feed-dt">' + esc(fmtDay(s.date)) + (s.time ? ' · ' + esc(s.time) : '') + ' · ' + esc(typeShort(s.type)) + (s.count ? ' ×' + esc(s.count) : '') + '</div>' +
        '<div class="feed-city">' + esc(s.city || '') + (s.region ? ' <span style="color:var(--ink-dim);font-weight:400">· ' + esc(s.region) + '</span>' : '') + '</div>' +
        '<div class="feed-title">' + esc(s.title || s.detail || '') + '</div></div>';
    }).join("") || '<div class="note">Лента ударов загружается…</div>';
    Array.prototype.forEach.call(el.querySelectorAll(".feed-item"), function (it) {
      bindButton(it, function () { flyToStrike(feedSorted[+it.dataset.fi]); });
    });
  }
  function flyToStrike(s) {
    if (!s || typeof s.lat !== "number") return;
    var btn = document.querySelector('#layerToggles button[data-layer=strikes]');
    if (btn && !btn.classList.contains("active")) btn.click();
    else if (L_ru.strikes && !maps.ru.hasLayer(L_ru.strikes)) maps.ru.addLayer(L_ru.strikes);
    stopPlay();
    setStrikeMode("day");
    var di = SK.dates.indexOf(s.date); if (di >= 0) SK.idx = di;
    renderStrikes();
    var bar = document.getElementById("strikeBar"); if (bar) bar.classList.remove("hidden");
    maps.ru.flyTo([s.lat, s.lon], 7, { duration: .7 });
    setTimeout(function () {
      for (var i = 0; i < renderedStrikes.length; i++) {
        if (renderedStrikes[i].s === s) { renderedStrikes[i].marker.openPopup(); break; }
      }
    }, 780);
  }
  function updateStrikeBar() {
    var sl = document.getElementById("dayslider"); if (!sl) return;
    sl.max = Math.max(0, SK.dates.length - 1); sl.value = SK.idx; sl.disabled = false;
    var lbl = document.getElementById("dayLabel"), n = shownStrikes().length;
    var modeLbl;
    if (SK.mode === "today") modeLbl = "Сегодня";
    else if (SK.mode === "7d") modeLbl = "За 7 дней";
    else if (SK.mode === "30d") modeLbl = "За 30 дней";
    else if (SK.mode === "prevmonth") { var pr = prevMonthRange(todayISO()); modeLbl = "Прошлый месяц: " + fmtDay(pr.from) + " – " + fmtDay(pr.to); }
    else if (SK.mode === "range") { var rr = modeRange(); modeLbl = fmtDay(rr.from) + " – " + fmtDay(rr.to); }
    else if (SK.mode === "all") modeLbl = "Все · " + SK.dates.length + " дн.";
    else modeLbl = fmtDay(SK.dates[SK.idx]);
    lbl.textContent = modeLbl + " · " + n + " удар" + plural(n);
    // подсветка активной preset-кнопки
    Array.prototype.forEach.call(document.querySelectorAll("#strikeBar .sb-preset"), function (b) {
      b.classList.toggle("active", b.dataset.preset === SK.mode);
    });
    // границы и значения полей диапазона дат
    var df = document.getElementById("dayFrom"), dt = document.getElementById("dayTo");
    if (df && dt && SK.dates.length) {
      var lo = SK.dates[0], hi = SK.dates[SK.dates.length - 1];
      df.min = lo; df.max = hi; dt.min = lo; dt.max = hi;
      if (SK.mode === "range") { if (SK.from) df.value = SK.from; if (SK.to) dt.value = SK.to; }
      var rng = df.parentNode; if (rng) rng.classList.toggle("active", SK.mode === "range");
    }
  }
  function setStrikeMode(mode) {
    var was = SK.mode;
    SK.mode = mode;
    // прыгаем на последний день только при ВХОДЕ в day-режим, иначе ‹/› сбрасывали бы шаг
    if (mode === "day" && was !== "day" && SK.dates.length) { SK.idx = SK.dates.length - 1; }
  }
  function startPlay() {
    if (!SK.dates.length) return;
    setStrikeMode("day");
    SK.playing = true; var p = document.getElementById("dayPlay"); if (p) { p.textContent = "⏸"; p.classList.add("active"); }
    SK.timer = setInterval(function () { SK.idx = (SK.idx + 1) % SK.dates.length; renderStrikes(); }, 1200);
  }
  function stopPlay() {
    SK.playing = false; if (SK.timer) { clearInterval(SK.timer); SK.timer = null; }
    var p = document.getElementById("dayPlay"); if (p) { p.textContent = "▶"; p.classList.remove("active"); }
  }

  /* ---------- AZS TAB (separate map: stations + trip + comments) ---------- */
  var AZS_UNKNOWN = "#7a7e85";
  var azsState = { brands: null, level: null, hasFuelOnly: false, userPos: null };
  var AZS_STATUS2LVL = { ok: "calm", normal: "calm", available: "calm", open: "calm", minor: "strained", some: "strained", limited: "limited", talony: "limited", severe: "severe", shortage: "severe", critical: "critical", dry: "critical", none: "critical", closed: "critical" };

  function initAzMap() {
    if (azsReady) return;
    maps.az = L.map("mapAzs", { center: [58, 85], zoom: 3, minZoom: 3, maxZoom: 15, worldCopyJump: false, zoomControl: false });
    maps.az.on("click", closeAnalyticsDropdown);
    L.control.zoom({ position: "bottomright" }).addTo(maps.az);
    tiles.az = baseTiles().addTo(maps.az);
    L_az.cluster = (typeof L.markerClusterGroup === "function")
      ? L.markerClusterGroup({ maxClusterRadius: 48, chunkedLoading: true, spiderfyOnMaxZoom: true, iconCreateFunction: azsClusterIcon })
      : L.layerGroup();
    L_az.cluster.addTo(maps.az);
    L_az.comments = L.layerGroup().addTo(maps.az);
    L_az.route = L.layerGroup().addTo(maps.az);
    L_az.me = L.layerGroup().addTo(maps.az);
    azsReady = true;
  }
  var azsBound = false;
  function renderAzsTab() {
    renderAzsStations();
    renderAzsComments(AZS_ROUTE.cities.length ? AZS_ROUTE.cities : null);
    if (!document.querySelector("#azsPresets button")) renderAzsPresets();
    if (!document.querySelector("#azsBrands label")) renderAzsBrandFilter();
    renderAzsLegend();
    if (!azsBound) { bindAzsRouteUI(); azsBound = true; }
    if (AZS_ROUTE.line) recomputeTripStations();
  }

  /* join: станция -> уровень (green→red) по статусу её сети в её регионе */
  var AZS_REGION_ALIAS = { "московская": "москва", "адыгея": "краснодарский" }; // агломерации наследуют статус соседа (оценка)
  function azsRegionEntry(regionName) {
    var a = S.availability; if (!a || !a.regions) return null;
    var target = normRegion(regionName);
    if (AZS_REGION_ALIAS[target]) target = AZS_REGION_ALIAS[target];
    for (var i = 0; i < a.regions.length; i++) {
      if (normRegion(a.regions[i].region) === target) return a.regions[i];
    }
    return null;
  }
  function brandMatchesNetwork(st, nw) {
    var n = (nw.name || "").toLowerCase().replace(/ё/g, "е");
    var lbl = (st.brand_label || "").toLowerCase().replace(/ё/g, "е");
    if (!n || !lbl) return false;
    return n.indexOf(lbl) >= 0 || lbl.indexOf(n) >= 0;
  }
  function stationLevel(st) {
    var reg = azsRegionEntry(st.region);
    if (!reg) return "unknown";
    if (reg.networks && st.brand && st.brand !== "other") {
      for (var i = 0; i < reg.networks.length; i++) {
        var nw = reg.networks[i];
        if (brandMatchesNetwork(st, nw)) {
          if (nw.level && AZS_LVL[nw.level]) return nw.level;
          var lv = AZS_STATUS2LVL[(nw.status || "").toLowerCase()];
          if (lv) return lv;
          break;
        }
      }
    }
    return (reg.level && AZS_LVL[reg.level]) ? reg.level : "unknown";
  }

  function azsStationIcon(level, hi) {
    var c = AZS_LVL[level] || AZS_UNKNOWN;
    var ring = hi ? '<circle cx="9" cy="9" r="8" fill="none" stroke="#1b6ef3" stroke-width="2"/>' : "";
    // ponytail: видимая точка остаётся 18×18 (не трогаем визуал), хит-зона расширена прозрачным
    // паддингом до 36×36 — иначе тач-таргет был в 2.4× меньше рекомендуемых 44px
    var html = '<div style="width:36px;height:36px;display:flex;align-items:center;justify-content:center"><svg width="18" height="18" viewBox="0 0 18 18">' + ring +
      '<circle cx="9" cy="9" r="5.5" fill="' + c + '" stroke="#000" stroke-opacity=".35" stroke-width="1"/></svg></div>';
    return L.divIcon({ className: "azs-divicon", html: html, iconSize: [36, 36], iconAnchor: [18, 18], popupAnchor: [0, -6] });
  }
  // Кластер красится по «худшей» точке внутри (а не по count). Серый "unknown" не повышает уровень — иначе серость съест предупреждение.
  var AZS_LVL_ORD = { unknown: 0, calm: 1, strained: 2, limited: 3, severe: 4, critical: 5 };
  function azsClusterIcon(cluster) {
    var kids = cluster.getAllChildMarkers();
    var worst = "unknown", worstReal = "unknown";
    for (var i = 0; i < kids.length; i++) {
      var l = kids[i]._lvl || "unknown";
      if ((AZS_LVL_ORD[l] || 0) > (AZS_LVL_ORD[worst] || 0)) worst = l;
      if (l !== "unknown" && (AZS_LVL_ORD[l] || 0) > (AZS_LVL_ORD[worstReal] || 0)) worstReal = l;
    }
    // Если хоть одна точка не "unknown", показываем худшую реальную (так группа из 10 красных + 2 серых будет красной, а не серой).
    if (worstReal !== "unknown") worst = worstReal;
    var c = AZS_LVL[worst] || AZS_UNKNOWN;
    var n = cluster.getChildCount();
    var size = n < 10 ? 30 : n < 50 ? 36 : n < 200 ? 42 : 48;
    var fs = n < 10 ? 12 : n < 50 ? 13 : 14;
    var darkText = (worst === "limited" || worst === "strained");
    var txt = darkText ? "#1a1a1a" : "#fff";
    var html = '<div class="azs-cluster-pin" style="width:' + size + 'px;height:' + size + 'px;line-height:' + (size - 4) + 'px;background:' + c + ';color:' + txt + ';font-size:' + fs + 'px">' + n + '</div>';
    return L.divIcon({ className: "azs-cluster", html: html, iconSize: L.point(size, size) });
  }
  // Кластер УДАРОВ — красный бейдж-огонёк с числом (а не дефолтный зелёный кружок markercluster).
  function strikeClusterIcon(cluster) {
    var n = cluster.getChildCount();
    var size = n < 5 ? 32 : n < 15 ? 38 : 44;
    var fs = n < 5 ? 13 : 14;
    var html = '<div style="position:relative;width:' + size + 'px;height:' + size + 'px;border-radius:50%;'
      + 'background:radial-gradient(circle at 50% 32%,#ff8a1e,#d21f1f);border:2px solid #fff;'
      + 'box-shadow:0 0 0 2px rgba(210,31,31,.30),0 2px 6px rgba(0,0,0,.40);'
      + 'display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:' + fs + 'px;">'
      + '<span style="position:absolute;top:-9px;right:-5px;font-size:16px;filter:drop-shadow(0 1px 1px rgba(0,0,0,.55))">🔥</span>'
      + n + '</div>';
    return L.divIcon({ className: "strike-cluster", html: html, iconSize: L.point(size, size) });
  }
  function nearestComments(st, max) {
    var v = (S.voices && S.voices.voices) || [], out = [];
    for (var i = 0; i < v.length && out.length < (max || 2); i++) {
      var q = v[i];
      if (st.city && q.city && q.city === st.city) out.push(q);
      else if (normRegion(q.region || "") === normRegion(st.region)) out.push(q);
    }
    return out;
  }
  // Great-circle distance (haversine), km. Pure — see __selfcheck at bottom of file.
  function haversineKm(lat1, lon1, lat2, lon2) {
    var R = 6371, toRad = Math.PI / 180;
    var dLat = (lat2 - lat1) * toRad, dLon = (lon2 - lon1) * toRad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  // «Есть топливо» — честная OSINT-оценка: калм/перебои/лимиты считаем «есть», severe/critical/unknown — нет.
  function azsLevelHasFuel(lvl) { return lvl === "calm" || lvl === "strained" || lvl === "limited"; }

  function azsStationPopup(st, distKm) {
    var lvl = stationLevel(st), c = AZS_LVL[lvl] || AZS_UNKNOWN, lbl = (AZS_LBL[lvl] || "нет данных").toUpperCase();
    var reg = azsRegionEntry(st.region);
    var html = '<div class="azs-pop"><div class="ap-brand">' + esc(st.brand_label || "АЗС") + '</div>';
    if (typeof distKm === "number") {
      html += '<div class="ap-row" style="font-weight:700">📍 ' + (distKm < 1 ? Math.round(distKm * 1000) + " м" : distKm.toFixed(1) + " км") + ' от вас</div>';
    }
    html += '<div class="ap-row"><span class="ap-status" style="background:' + c + '">' + esc(lbl) + '</span></div>';
    if (st.addr) html += '<div class="ap-row">📍 ' + esc(st.addr) + (st.city ? ", " + esc(st.city) : "") + '</div>';
    else if (st.city) html += '<div class="ap-row">📍 ' + esc(st.city) + '</div>';
    html += '<div class="ap-row" style="opacity:.7">Регион: ' + esc(st.region) + '</div>';
    if (reg) {
      if (reg.ai95_price_rub) html += '<div class="ap-row">АИ-95 ~' + esc(reg.ai95_price_rub) + ' ₽/л</div>';
      if (typeof reg.queues_hours === "number" && reg.queues_hours > 0) html += '<div class="ap-row">Очередь ~' + esc(reg.queues_hours) + ' ч</div>';
    }
    var cm = nearestComments(st, 2);
    cm.forEach(function (q) { html += '<div class="ap-quote">«' + esc(q.quote || "") + '»</div>'; });
    html += '<div class="ap-row" style="opacity:.55;font-size:10px;margin-top:5px">Наличие — оценка по сети/региону. Точка — OSM.</div>';
    if (azsState.hasFuelOnly) html += '<div class="ap-row" style="opacity:.55;font-size:10px">Фильтр «есть топливо»: честная OSINT-оценка, без подделки статуса колонок.</div>';
    html += '</div>';
    return html;
  }

  function renderAzsStations() {
    if (!L_az.cluster) return;
    L_az.cluster.clearLayers();
    var st = (S.azsStations && S.azsStations.stations) || [];
    var shown = 0, markers = [];
    st.forEach(function (s) {
      if (azsState.brands && !azsState.brands.has(s.brand)) return;
      var lvl = stationLevel(s);
      if (azsState.level && lvl !== azsState.level) return;
      if (azsState.hasFuelOnly && !azsLevelHasFuel(lvl)) return;
      var dist = azsState.userPos ? haversineKm(azsState.userPos.lat, azsState.userPos.lon, s.lat, s.lon) : null;
      var m = L.marker([s.lat, s.lon], { icon: azsStationIcon(lvl, false) });
      m.bindPopup(azsStationPopup(s, dist), POPUP_OPTS);
      m._azs = s;
      m._lvl = lvl;
      markers.push(m);
      shown++;
    });
    if (L_az.cluster.addLayers) L_az.cluster.addLayers(markers);
    else markers.forEach(function (m) { L_az.cluster.addLayer(m); });
    var cnt = document.getElementById("azsCount"); if (cnt) cnt.textContent = shown;
  }

  function azsMeIcon() {
    return L.divIcon({ className: "azs-divicon", html: '<div class="azs-me-pin">📍</div>', iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -12] });
  }
  function locateAzsUser() {
    var msgEl = document.getElementById("azsGeoMsg");
    if (!navigator.geolocation) { if (msgEl) msgEl.textContent = "Геолокация не поддерживается браузером."; showToast("Геолокация не поддерживается браузером."); return; }
    if (msgEl) msgEl.textContent = "Определяю местоположение…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      azsState.userPos = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      if (msgEl) msgEl.textContent = "";
      if (L_az.me) {
        L_az.me.clearLayers();
        L.marker([azsState.userPos.lat, azsState.userPos.lon], { icon: azsMeIcon(), zIndexOffset: 900 })
          .bindPopup("Вы здесь").addTo(L_az.me);
      }
      if (maps.az) maps.az.setView([azsState.userPos.lat, azsState.userPos.lon], 12);
      renderAzsStations();
    }, function (err) {
      var msg = (err && err.code === 1) ? "Доступ к геолокации запрещён — разрешите его в настройках браузера." : "Не удалось определить местоположение.";
      if (msgEl) msgEl.textContent = msg;
      showToast(msg);
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  }

  function renderAzsBrandFilter() {
    var el = document.getElementById("azsBrands"); if (!el) return;
    var st = (S.azsStations && S.azsStations.stations) || [];
    var counts = {};
    st.forEach(function (s) { if (!counts[s.brand]) counts[s.brand] = { label: (s.brand === "other" ? "Прочие / без бренда" : s.brand_label), n: 0 }; counts[s.brand].n++; });
    var keys = Object.keys(counts).sort(function (a, b) { return counts[b].n - counts[a].n; });
    el.innerHTML = "";
    keys.forEach(function (k) {
      var lab = document.createElement("label");
      lab.innerHTML = '<input type="checkbox" checked data-brand="' + esc(k) + '"> ' + esc(counts[k].label) + ' (' + esc(counts[k].n) + ')';
      el.appendChild(lab);
    });
    Array.prototype.forEach.call(el.querySelectorAll("input"), function (inp) {
      inp.addEventListener("change", function () {
        var active = new Set();
        Array.prototype.forEach.call(el.querySelectorAll("input"), function (x) { if (x.checked) active.add(x.dataset.brand); });
        azsState.brands = (active.size === keys.length) ? null : active;
        renderAzsStations();
        if (AZS_ROUTE.line) recomputeTripStations();
      });
    });
  }
  function renderAzsLegend() {
    var el = document.getElementById("azsLegend"); if (!el) return;
    var order = ["calm", "strained", "limited", "severe", "critical"];
    var html = "";
    order.forEach(function (k) { html += '<span><i style="background:' + AZS_LVL[k] + '"></i>' + AZS_LBL[k] + '</span>'; });
    html += '<span><i style="background:' + AZS_UNKNOWN + '"></i>нет данных</span>';
    el.innerHTML = html;
  }

  function azsCommentPin() {
    return L.divIcon({ className: "azs-divicon", html: '<div class="voice-pin">🗣</div>', iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -8] });
  }
  function renderAzsComments(filterCities) {
    var listEl = document.getElementById("azsComments");
    var v = (S.voices && S.voices.voices) || [];
    if (filterCities && filterCities.length) {
      v = v.filter(function (q) { return q.city && filterCities.indexOf(q.city) >= 0; });
    }
    var cnt = document.getElementById("azsCommentsCount"); if (cnt) cnt.textContent = v.length;
    if (listEl) {
      listEl.innerHTML = "";
      if (!v.length) listEl.innerHTML = '<div class="note">Нет комментариев для выбранного маршрута.</div>';
      v.slice(0, 60).forEach(function (q) {
        var d = document.createElement("div");
        d.className = "voice-item";
        d.innerHTML = '<div class="voice-meta"><span class="voice-loc">' + esc(q.city || q.region || "") + '</span><span class="voice-date">' + esc(q.date ? rusDate(q.date) : "") + '</span></div>' +
          '<div class="voice-quote">«' + esc(q.quote || "") + '»</div>' +
          '<div class="voice-foot">' + esc(q.author_hint || "—") + ' · ' + esc(q.source || "") + (q.source_url ? ' <a href="' + safeUrl(q.source_url) + '" target="_blank" rel="noopener">↗</a>' : "") + '</div>';
        if (q.lat && q.lon) { d.style.cursor = "pointer"; bindButton(d, function () { if (maps.az) maps.az.setView([q.lat, q.lon], 9); }); }
        listEl.appendChild(d);
      });
    }
    if (L_az.comments) {
      L_az.comments.clearLayers();
      v.forEach(function (q) {
        if (!q.lat || !q.lon) return;
        L.marker([q.lat, q.lon], { icon: azsCommentPin(), zIndexOffset: 600 })
          .bindPopup('<div class="azs-pop"><div class="ap-row" style="opacity:.7">' + esc(q.city || q.region || "") + " · " + esc(q.date ? rusDate(q.date) : "") + '</div><div class="ap-quote">«' + esc(q.quote || "") + '»</div>' + (q.source_url ? '<div class="ap-row"><a href="' + safeUrl(q.source_url) + '" target="_blank" rel="noopener">' + esc(q.source || "источник") + ' ↗</a></div>' : "") + '</div>', POPUP_OPTS)
          .addTo(L_az.comments);
      });
    }
  }

  function distToSegKm(p, a, b) {
    var kx = 111.32 * Math.cos(p[0] * Math.PI / 180), ky = 110.57;
    var ax = a[1] * kx, ay = a[0] * ky, bx = b[1] * kx, by = b[0] * ky, px = p[1] * kx, py = p[0] * ky;
    var dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    var t = len2 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    var cx = ax + t * dx, cy = ay + t * dy;
    return Math.sqrt((px - cx) * (px - cx) + (py - cy) * (py - cy));
  }
  function distToPolylineKm(pt, line) {
    var min = Infinity;
    for (var i = 0; i < line.length - 1; i++) {
      var d = distToSegKm(pt, line[i], line[i + 1]);
      if (d < min) min = d;
    }
    return min;
  }

  var TRIP_BUFFER_KM = 5;
  function applyTrip(lineLatLngs, cities) {
    AZS_ROUTE.line = lineLatLngs;
    AZS_ROUTE.cities = cities || [];
    if (L_az.route) {
      L_az.route.clearLayers();
      L.polyline(lineLatLngs, { color: "#1b6ef3", weight: 4, opacity: .8 }).addTo(L_az.route);
    }
    recomputeTripStations();
    renderAzsComments(AZS_ROUTE.cities.length ? AZS_ROUTE.cities : null);
    try { maps.az.fitBounds(L.polyline(lineLatLngs).getBounds().pad(0.2)); } catch (e) {}
  }
  function recomputeTripStations() {
    var st = (S.azsStations && S.azsStations.stations) || [];
    var line = AZS_ROUTE.line; if (!line || !line.length) return;
    var along = [];
    st.forEach(function (s) {
      if (azsState.brands && !azsState.brands.has(s.brand)) return;
      if (distToPolylineKm([s.lat, s.lon], line) <= TRIP_BUFFER_KM) along.push(s);
    });
    var tally = { calm: 0, strained: 0, limited: 0, severe: 0, critical: 0, unknown: 0 };
    along.forEach(function (s) { tally[stationLevel(s)]++; });
    var ok = tally.calm + tally.strained, warn = tally.limited, bad = tally.severe + tally.critical;
    var el = document.getElementById("azsTrip");
    if (el) {
      el.innerHTML =
        '<div class="tr-row">Вдоль маршрута: <b>' + along.length + '</b> АЗС (±' + TRIP_BUFFER_KM + ' км)</div>' +
        '<div class="tr-row">' +
        '<span class="tr-chip" style="background:' + AZS_LVL.calm + ';color:#fff">🟢 ' + ok + '</span>' +
        '<span class="tr-chip" style="background:' + AZS_LVL.limited + ';color:#000">🟡 ' + warn + '</span>' +
        '<span class="tr-chip" style="background:' + AZS_LVL.critical + ';color:#fff">🔴 ' + bad + '</span>' +
        '<span class="tr-chip" style="background:' + AZS_UNKNOWN + ';color:#fff">⚪ ' + tally.unknown + '</span>' +
        '</div>' +
        '<div class="tr-row" style="opacity:.6;font-size:10px">' + esc('🟢 доступно · 🟡 лимиты · 🔴 дефицит/сухо · ⚪ нет данных') + '</div>' +
        (bad > 0 ? '<div class="tr-row" style="color:' + AZS_LVL.critical + '">⚠ Есть участки острого дефицита — заправляйтесь заранее.</div>' : '<div class="tr-row" style="color:' + AZS_LVL.calm + '">Топливо вдоль маршрута в целом доступно (оценка).</div>');
    }
  }
  function clearTrip() {
    tripRequestId++; // invalidate any in-flight geocode/OSRM request from a previous build
    AZS_ROUTE.line = null; AZS_ROUTE.cities = [];
    if (L_az.route) L_az.route.clearLayers();
    var el = document.getElementById("azsTrip"); if (el) el.innerHTML = "";
    renderAzsComments(null);
    Array.prototype.forEach.call(document.querySelectorAll("#azsPresets button"), function (b) { b.classList.remove("active"); });
  }
  function renderAzsPresets() {
    var el = document.getElementById("azsPresets"); if (!el) return;
    var routes = (S.azsRoutes && S.azsRoutes.routes) || [];
    el.innerHTML = "";
    routes.forEach(function (r) {
      var b = document.createElement("button");
      b.textContent = r.name;
      b.addEventListener("click", function () {
        tripRequestId++; // preset build supersedes any in-flight custom-route request
        Array.prototype.forEach.call(el.querySelectorAll("button"), function (x) { x.classList.remove("active"); });
        b.classList.add("active");
        applyTrip(r.waypoints, r.cities || []);
      });
      el.appendChild(b);
    });
  }

  function geocode(q) {
    var url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=ru,ua&accept-language=ru&q=" + encodeURIComponent(q);
    return fetch(url, { headers: { "Accept": "application/json" } }).then(function (r) { return r.json(); }).then(function (a) {
      if (!a || !a.length) throw new Error("город не найден: " + q);
      return [parseFloat(a[0].lat), parseFloat(a[0].lon)];
    });
  }
  function osrmRoute(from, to) {
    var url = "https://router.project-osrm.org/route/v1/driving/" + from[1] + "," + from[0] + ";" + to[1] + "," + to[0] + "?overview=full&geometries=geojson";
    return fetch(url).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.routes || !j.routes.length) throw new Error("маршрут не построен");
      return j.routes[0].geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
    });
  }
  function bindAzsRouteUI() {
    var locBtn = document.getElementById("azsLocateBtn");
    if (locBtn) bindButton(locBtn, locateAzsUser);
    var fuelChk = document.getElementById("azsFuelOnly");
    if (fuelChk) fuelChk.addEventListener("change", function () {
      azsState.hasFuelOnly = fuelChk.checked;
      renderAzsStations();
      if (AZS_ROUTE.line) recomputeTripStations();
    });
    var btn = document.getElementById("azsRouteBtn"), clr = document.getElementById("azsRouteClear");
    var fromEl = document.getElementById("azsFrom"), toEl = document.getElementById("azsTo");
    var tripEl = document.getElementById("azsTrip");
    if (clr) clr.addEventListener("click", clearTrip);
    if (btn) btn.addEventListener("click", function () {
      var f = (fromEl.value || "").trim(), t = (toEl.value || "").trim();
      if (!f || !t) { if (tripEl) tripEl.innerHTML = '<div class="tr-row" style="color:' + AZS_LVL.severe + '">Укажите оба города.</div>'; return; }
      if (tripEl) tripEl.innerHTML = '<div class="tr-row">Строю маршрут…</div>';
      Array.prototype.forEach.call(document.querySelectorAll("#azsPresets button"), function (b) { b.classList.remove("active"); });
      var reqId = ++tripRequestId;
      Promise.all([geocode(f), geocode(t)]).then(function (pts) {
        return osrmRoute(pts[0], pts[1]).then(function (line) {
          if (reqId !== tripRequestId) return; // superseded by a newer build/reset — drop stale response
          applyTrip(line, [f, t]);
        });
      }).catch(function (e) {
        if (reqId !== tripRequestId) return;
        if (tripEl) tripEl.innerHTML = '<div class="tr-row" style="color:' + AZS_LVL.critical + '">Не удалось построить маршрут (' + esc(e.message || "ошибка") + '). Попробуйте пресет-коридор.</div>';
      });
    });
  }

  /* ---------- AZS (fuel availability) ---------- */
  /* Чистый градиент: зелёный → лайм → жёлтый → оранжевый → красный */
  var AZS_LVL = { calm: "#2f9e57", strained: "#e8c520", limited: "#ef9a1a", severe: "#dd4f1c", critical: "#d23a2e" };
  var AZS_LBL = { calm: "штатно", strained: "перебои", limited: "лимиты", severe: "острый дефицит", critical: "сухо" };
  function azsIcon(r) {
    var c = AZS_LVL[r.level] || "#7a7e85";
    var pulse = (r.level === "severe" || r.level === "critical") ? '<circle cx="14" cy="14" r="12" fill="none" stroke="' + c + '" stroke-width="1.6" opacity=".5"><animate attributeName="r" values="9;14;9" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values=".6;0;.6" dur="2s" repeatCount="indefinite"/></circle>' : '';
    var html = '<div class="azs-pin"><svg width="28" height="28" viewBox="0 0 28 28">' + pulse +
      '<circle cx="14" cy="14" r="9" fill="' + c + '" stroke="#fff" stroke-width="2"/>' +
      '<text x="14" y="18" font-size="13" text-anchor="middle" fill="#fff" font-weight="800">⛽</text>' +
      '</svg></div>';
    return L.divIcon({ className: "", html: html, iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -12] });
  }
  function azsPopup(r) {
    var c = AZS_LVL[r.level] || "#7a7e85", lbl = (AZS_LBL[r.level] || r.level || "—").toUpperCase();
    var h = '<div class="pp-h">⛽ ' + esc(r.region) + '</div>';
    h += '<span class="pp-st" style="background:' + c + '">' + esc(lbl) + '</span>';
    if (r.estimate) h += '<span class="pp-st" style="background:#5a5f66;margin-left:4px">ОЦЕНКА</span>';
    // честная свежесть: дата обновления именно этого региона (не общий штамп файла) + пометка «устарело» >7 дн.
    var _upd = (r.updated || "").slice(0, 10);
    if (_upd) {
      var _ud = new Date(_upd + "T00:00:00Z");
      var _age = isNaN(_ud.getTime()) ? -1 : Math.floor((Date.now() - _ud.getTime()) / 86400000);
      var _stale = _age > 7;
      h += '<div class="pp-kv" style="' + (_stale ? "color:#c9760a;font-weight:700" : "opacity:.65") + '"><span>Обновлено</span><span>' + esc(rusDate(_upd)) + (_age >= 0 ? " · " + (_age === 0 ? "сегодня" : _age === 1 ? "вчера" : _age + " дн. назад") : "") + (_stale ? " ⚠" : "") + '</span></div>';
    }
    if (r.note) h += '<div class="pp-note" style="margin:4px 0;font-size:11px;opacity:.85">' + esc(r.note) + '</div>';
    if (typeof r.queues_hours === "number" && r.queues_hours > 0)
      h += '<div class="pp-kv"><span>Очереди</span><span>~' + esc(r.queues_hours) + ' ч</span></div>';
    if (r.ai95_price_rub) h += '<div class="pp-kv"><span>АИ-95</span><span>' + esc(r.ai95_price_rub) + ' ₽/л</span></div>';
    if (r.diesel_price_rub) h += '<div class="pp-kv"><span>ДТ</span><span>' + esc(r.diesel_price_rub) + ' ₽/л</span></div>';
    if (r.networks && r.networks.length) {
      h += '<div class="pp-dmg" style="margin-top:6px"><b>Сети АЗС:</b></div>';
      r.networks.forEach(function (n) {
        var nc = n.status === "closed" ? "#a01d14" : n.status === "limited" ? "#df8f17" : n.status === "open" ? "#2f9e57" : "#7a7e85";
        var ns = n.status === "closed" ? "закрыто" : n.status === "limited" ? "лимит" : n.status === "open" ? "работает" : "—";
        h += '<div class="pp-kv"><span>' + esc(n.name) + '</span><span style="color:' + nc + ';font-weight:700">' + esc(ns) + (n.limit_l ? " ≤" + esc(n.limit_l) + "л" : "") + '</span></div>';
        if (n.note) h += '<div class="pp-note" style="margin:2px 0 4px;font-size:11px">' + esc(n.note) + '</div>';
      });
    }
    if (r.source_urls && r.source_urls.length)
      h += srcHtml(r.source_urls[0], 'источник');
    return h;
  }
  function renderAzs() {
    if (!L_ru.azs) return;
    L_ru.azs.clearLayers();
    var a = S.availability; if (!a || !a.regions) return;
    a.regions.forEach(function (r) {
      if (typeof r.lat !== "number" || typeof r.lon !== "number") return;
      L.marker([r.lat, r.lon], { icon: azsIcon(r), zIndexOffset: 400 })
        .bindPopup(azsPopup(r), POPUP_OPTS).addTo(L_ru.azs);
    });
  }

  /* ---------- VOICES (public quotes) ---------- */
  var SENT_ICO = { complaint: "😠", panic: "😱", relief: "😌", info: "ℹ️", sarcasm: "😏", praise: "👍" };
  var TOPIC_LBL = { queue: "очередь", limit: "лимит", price: "цена", closed: "закрыто", talon: "талоны", empty: "пусто", available: "есть" };
  function voiceFresh(q) {
    // relative freshness from `seen` (когда агент нашёл цитату); fallback на date
    var s = q.seen || q.date; if (!s) return "";
    var d = new Date(s + "T00:00:00Z"); if (isNaN(d)) return "";
    var days = Math.floor((Date.now() - d.getTime()) / 86400000);
    if (days <= 0) return '<span class="voice-fresh" style="color:#d23a2e">● сегодня</span>';
    if (days === 1) return '<span class="voice-fresh" style="color:#e07a18">● вчера</span>';
    if (days <= 7) return '<span class="voice-fresh" style="color:#9fc63a">● ' + days + ' дн</span>';
    return "";
  }
  function renderVoices() {
    var el = document.getElementById("voicesList"); if (!el) return;
    var v0 = (S.voices && S.voices.voices) || [];
    // сортировка по seen (или date) убыванию — самые недавно найденные сверху
    var v = v0.slice().sort(function (a, b) {
      return String(b.seen || b.date || "").localeCompare(String(a.seen || a.date || ""));
    });
    var cnt = document.getElementById("voicesCount"); if (cnt) cnt.textContent = v.length;
    if (!v.length) { el.innerHTML = '<div class="note">Голоса собираются… (агент FUEL-VOICES публикует каждые 8ч)</div>'; return; }
    el.innerHTML = v.map(function (q, i) {
      var ico = SENT_ICO[q.sentiment] || "🗣";
      var topic = TOPIC_LBL[q.topic] || q.topic || "";
      return '<div class="voice-item" role="button" tabindex="0" data-vi="' + i + '">' +
        '<div class="voice-meta"><span class="voice-ico">' + esc(ico) + '</span>' +
        '<span class="voice-loc">' + esc(q.city || q.region || "") + '</span>' +
        (topic ? '<span class="voice-topic">' + esc(topic) + '</span>' : '') +
        voiceFresh(q) +
        '<span class="voice-date">' + esc(q.date ? rusDate(q.date) : "") + '</span></div>' +
        '<div class="voice-quote">«' + esc(q.quote || "") + '»</div>' +
        '<div class="voice-foot">' + esc(q.author_hint || "—") + ' · ' + esc(q.source || "") +
        (q.source_url ? ' <a href="' + safeUrl(q.source_url) + '" target="_blank" rel="noopener">↗</a>' : '') + '</div></div>';
    }).join("");
    Array.prototype.forEach.call(el.querySelectorAll(".voice-item"), function (it) {
      bindButton(it, function (e) {
        if (e.target.tagName === "A") return;
        var q = v[+it.dataset.vi];
        if (!q || typeof q.lat !== "number") return;
        var btn = document.querySelector('#layerToggles button[data-layer=azs]');
        if (btn && !btn.classList.contains("active")) btn.click();
        maps.ru.flyTo([q.lat, q.lon], 7, { duration: .6 });
      });
    });
  }

  /* ---------- GRID (electricity) ---------- */
  var GRID_C = { operational: "#2f9e57", damaged: "#df8f17", down: "#a01d14" };
  var GRID_LBL = { operational: "работает", damaged: "повреждена", down: "выведена" };
  var BLACKOUT_C = { partial: "#df8f17", rolling: "#e8911c", total: "#a01d14" };
  function gridIcon(s) {
    var c = GRID_C[s.status] || "#7a7e85";
    var pulse = s.status === "down" ? '<circle cx="14" cy="14" r="11" fill="none" stroke="' + c + '" stroke-width="1.6" opacity=".6"><animate attributeName="r" values="8;13;8" dur="1.8s" repeatCount="indefinite"/><animate attributeName="opacity" values=".7;0;.7" dur="1.8s" repeatCount="indefinite"/></circle>' : '';
    var html = '<div><svg width="28" height="28" viewBox="0 0 28 28">' + pulse +
      '<rect x="4" y="4" width="20" height="20" rx="4" fill="' + c + '" stroke="#fff" stroke-width="2"/>' +
      '<path d="M15 7 L9 15 L13 15 L11 21 L19 12 L14 12 Z" fill="#fff"/>' +
      '</svg></div>';
    return L.divIcon({ className: "", html: html, iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -12] });
  }
  function gridPopup(s) {
    var c = GRID_C[s.status] || "#7a7e85", lbl = (GRID_LBL[s.status] || s.status || "—").toUpperCase();
    var h = '<div class="pp-h">⚡ ' + esc(s.name) + '</div>';
    h += '<span class="pp-st" style="background:' + c + '">' + esc(lbl) + '</span>';
    if (s.operator) h += '<div class="pp-kv"><span>Оператор</span><span>' + esc(s.operator) + '</span></div>';
    if (s.status_since) h += '<div class="pp-kv"><span>Статус с</span><span>' + esc(rusDate(s.status_since)) + '</span></div>';
    if (s.damage) h += '<div class="pp-dmg">⚠ ' + esc(s.damage) + '</div>';
    if (s.source_url) h += srcHtml(s.source_url, 'источник');
    return h;
  }
  function blackoutPopup(b) {
    var c = BLACKOUT_C[b.scope] || "#df8f17";
    var scope = { partial: "ЧАСТИЧНОЕ", rolling: "ВЕЕРНОЕ", total: "ПОЛНОЕ" }[b.scope] || b.scope;
    var h = '<div class="pp-h">🔌 ' + esc(b.region) + '</div>';
    h += '<span class="pp-st" style="background:' + c + '">' + esc(scope) + '</span>';
    if (b.affected_population) h += '<div class="pp-kv"><span>Затронуто</span><span>' + esc(b.affected_population) + '</span></div>';
    if (b.cause) h += '<div class="pp-kv"><span>Причина</span><span>' + esc(b.cause) + '</span></div>';
    if (b.since) h += '<div class="pp-kv"><span>С</span><span>' + esc(rusDate(b.since)) + '</span></div>';
    if (b.note) h += '<div class="pp-note">' + esc(b.note) + '</div>';
    if (b.source_url) h += srcHtml(b.source_url, 'источник');
    return h;
  }
  /* ---------- WAREHOUSES (крупные РЦ маркетплейсов) ---------- */
  // Слой выключен по умолчанию, поэтому data/warehouses.json грузится лениво — по первому
  // включению кнопки, а не у каждого посетителя карты.
  var whPromise = null;
  function loadWarehouses() {
    if (S.warehouses) return Promise.resolve(true);
    if (whPromise) return whPromise;
    whPromise = fetchData("warehouses")
      .then(function (d) { S.warehouses = d; return true; })
      .catch(function () { whPromise = null; return false; });   // false → вызывающий снимет слой
    return whPromise;
  }
  var WH_BRAND = { wb: { c: "#8b2fa8", label: "Wildberries" }, ozon: { c: "#0b63d6", label: "Ozon" } };
  function whIcon(w) {
    var b = WH_BRAND[w.operator] || { c: "#7a7e85" };
    var burned = w.status === "hit" && w.damage === "burned";
    // сгоревшие — красный с пульсом, чтобы читались среди полусотни обычных точек
    var c = burned ? "#d23a2e" : (w.status === "hit" ? "#df8f17" : b.c);
    var pulse = burned ? '<circle cx="13" cy="13" r="10" fill="none" stroke="' + c + '" stroke-width="1.6" opacity=".6"><animate attributeName="r" values="7;12;7" dur="1.8s" repeatCount="indefinite"/><animate attributeName="opacity" values=".7;0;.7" dur="1.8s" repeatCount="indefinite"/></circle>' : '';
    var html = '<div><svg width="26" height="26" viewBox="0 0 26 26">' + pulse +
      '<rect x="4" y="6" width="18" height="14" rx="2" fill="' + c + '" stroke="#fff" stroke-width="2"/>' +
      '<path d="M4 10 H22" stroke="#fff" stroke-width="1.6"/>' +
      (burned ? '<path d="M13 12 q2 2 0 4 q-2-2 0-4" fill="#fff"/>' : '') +
      '</svg></div>';
    return L.divIcon({ className: "", html: html, iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -11] });
  }
  function whPopup(w) {
    var b = WH_BRAND[w.operator] || { c: "#7a7e85", label: w.operator };
    var burned = w.status === "hit" && w.damage === "burned";
    // не «работает»: проект не проверяет работу каждого склада, он фиксирует только удары
    var st = w.status !== "hit" ? { t: "УДАРОВ НЕ ЗАФИКСИРОВАНО", c: "#2f8f4e" }
      : burned ? { t: "ПОРАЖЁН, ПОЖАР", c: "#d23a2e" } : { t: "ПОРАЖЁН", c: "#df8f17" };
    var h = '<div class="pp-h">📦 ' + esc(b.label) + ' — ' + esc(w.name) + '</div>';
    h += '<span class="pp-st" style="background:' + st.c + '">' + st.t + '</span>';
    h += '<div class="pp-kv"><span>Тип</span><span>' + (w.type === "ffc" ? "фулфилмент-центр" : "распределительный центр") + '</span></div>';
    if (w.region) h += '<div class="pp-kv"><span>Регион</span><span>' + esc(w.region) + '</span></div>';
    if (w.date) h += '<div class="pp-kv"><span>Дата удара</span><span>' + esc(rusDate(w.date)) + '</span></div>';
    if (w.note) h += '<div class="pp-note">' + esc(w.note) + '</div>';
    if (w.source_url) h += srcHtml(w.source_url, 'источник');
    return h;
  }
  function renderWarehouses() {
    if (!L_ru.warehouses) return;
    L_ru.warehouses.clearLayers();
    var d = S.warehouses; if (!d) return;
    (d.warehouses || []).forEach(function (w) {
      if (typeof w.lat !== "number" || typeof w.lon !== "number") return;
      L.marker([w.lat, w.lon], { icon: whIcon(w), zIndexOffset: w.status === "hit" ? 400 : 300 })
        .bindPopup(whPopup(w), POPUP_OPTS).addTo(L_ru.warehouses);
    });
  }

  function renderGrid() {
    if (!L_ru.grid) return;
    L_ru.grid.clearLayers();
    var g = S.grid; if (!g) return;
    (g.substations || []).forEach(function (s) {
      if (typeof s.lat !== "number" || typeof s.lon !== "number") return;
      L.marker([s.lat, s.lon], { icon: gridIcon(s), zIndexOffset: 350 })
        .bindPopup(gridPopup(s), POPUP_OPTS).addTo(L_ru.grid);
    });
    (g.blackout_regions || []).forEach(function (b) {
      if (typeof b.lat !== "number" || typeof b.lon !== "number") return;
      var c = BLACKOUT_C[b.scope] || "#df8f17";
      L.circleMarker([b.lat, b.lon], { radius: 18, color: c, weight: 2, fillColor: c, fillOpacity: 0.18, dashArray: "4,4" })
        .bindPopup(blackoutPopup(b), POPUP_OPTS).addTo(L_ru.grid);
    });
  }

  /* ---------- TICKER (fade carousel) ---------- */
  var tkItems = [], tkIdx = 0, tkTimer = null, tkPaused = false, tkWired = false;
  function renderTicker() {
    if (!S.state) return;
    var items = (S.state.events || []).map(function (e) { return '<b>' + esc(rusDate(e.date)) + '</b> ' + esc(e.text); });
    var df = (S.state.deficit_regions || []).map(function (d) { return esc(d.region) + ' [' + esc(d.level) + ']'; }).join(" · ");
    if (df) items.push('<b>ДЕФИЦИТ</b> ' + df);
    tkItems = items;
    if (tkIdx >= tkItems.length) tkIdx = 0;
    tkWire();
    tkShow();
    tkStart();
  }
  function tkShow() {
    var el = document.getElementById("ticker");
    if (el) el.innerHTML = tkItems.length ? tkItems[tkIdx % tkItems.length] : "";
  }
  function tkStart() {
    tkStop();
    if (tkItems.length < 2) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    tkTimer = setInterval(function () {
      if (tkPaused) return;
      var el = document.getElementById("ticker"); if (!el) return;
      el.classList.add("tk-out");
      setTimeout(function () {
        tkIdx = (tkIdx + 1) % tkItems.length;
        tkShow();
        el.classList.remove("tk-out");
      }, 380);
    }, 4200);
  }
  function tkStop() { if (tkTimer) { clearInterval(tkTimer); tkTimer = null; } }
  function tkWire() {
    if (tkWired) return; tkWired = true;
    var f = document.querySelector(".ticker"); if (!f) return;
    ["mouseenter", "focusin"].forEach(function (ev) { f.addEventListener(ev, function () { tkPaused = true; }); });
    ["mouseleave", "focusout"].forEach(function (ev) { f.addEventListener(ev, function () { tkPaused = false; }); });
  }

  /* ---------- CLOCK ---------- */
  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  function tickClock() {
    if (!nextSyncAt) return;
    var rem = Math.max(0, Math.floor((nextSyncAt - Date.now()) / 1000));
    var el = document.getElementById("nextSync");
    if (el) el.textContent = "T-" + pad(Math.floor(rem / 60)) + ":" + pad(rem % 60);
  }
  function renderSyncMeta() {
    if (!S.state) return;
    var m = S.state.meta || {};
    if (m.generated_at) {
      var d = new Date(new Date(m.generated_at).getTime() + 3 * 3600 * 1000); // МСК = UTC+3
      document.getElementById("lastSync").textContent = "sync " + pad(d.getUTCDate()) + "." + pad(d.getUTCMonth() + 1) + " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + " МСК";
    }
    if (m.data_mode) document.getElementById("modePill").textContent = m.data_mode.split("/")[0].trim();
    var fb = document.getElementById("ssFallback"); if (fb) fb.classList.toggle("hidden", !usedFallback);
  }
  function loadVersion() {
    fetch("/version.json").then(function (r) { return r.json(); }).then(function (data) {
      var el = document.getElementById("ssVersion");
      if (el && data && data.version) el.textContent = "v" + data.version;
    }).catch(function () {});
  }

  /* ---------- ANALYTICS DROPDOWN (закрытие по тапу вне меню, включая карту) ---------- */
  // ponytail: index.html уже закрывает меню по клику на document, но клики внутри Leaflet-карты
  // до document не долетают (Leaflet глушит propagation своим click-delay механизмом) —
  // поэтому вешаем закрытие напрямую на map 'click' в местах, где карты создаются.
  function closeAnalyticsDropdown() {
    document.querySelectorAll(".tab-dropdown-menu").forEach(function (m) { m.style.display = ""; });
  }

  /* ---------- TABS + CONTROLS ---------- */
  function initTabs() {
    Array.prototype.forEach.call(document.querySelectorAll("#tabs button"), function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(document.querySelectorAll("#tabs button"), function (x) { x.classList.remove("active"); x.removeAttribute("aria-current"); });
        b.classList.add("active");
        b.setAttribute("aria-current", "true");
        var view = b.dataset.view;
        Array.prototype.forEach.call(document.querySelectorAll(".view"), function (v) { v.classList.remove("active"); });
        document.getElementById("view-" + view).classList.add("active");
        // отдельный адрес для вкладки: #azs / #crimea… (russia = чистый путь). Клик пишет URL → ссылкой можно делиться.
        // guard по URL: клик, вызванный из popstate, не пишет дубль истории.
        try {
          var _u = location.pathname + (view === "russia" ? "" : "#" + view);
          if (location.pathname + location.hash !== _u) history.pushState(null, "", _u);
        } catch (e) {}
        if (view === "russia") setTimeout(function () { maps.ru.invalidateSize(); }, 60);
        if (view === "crimea") { if (!crimeaReady) { initCrMap(); renderCrimea(); } loadAzsData().then(renderCrimea); setTimeout(function () { maps.cr.invalidateSize(); }, 60); }
        if (view === "azs") {
          if (!azsReady) initAzMap();
          loadAzsData().then(function () {
            renderAzsTab();
            setTimeout(function () { maps.az.invalidateSize(); }, 60);
          });
        }
      });
    });
    // deep-link: ?view=azs (или #azs) открывает нужную вкладку при загрузке (для ссылок из Telegram-бота/новостей)
    try {
      var _dv = (new URLSearchParams(location.search).get("view") || (location.hash || "").replace("#","")).toLowerCase();
      if (_dv) { var _tb = document.querySelector('#tabs button[data-view="' + _dv + '"]'); if (_tb) _tb.click(); }
    } catch (e) {}
    // back/forward: восстанавливаем вкладку из адреса (click-guard выше не даст дубль истории)
    window.addEventListener("popstate", function () {
      var v = ((location.hash || "").replace("#", "").toLowerCase()) || "russia";
      var tb = document.querySelector('#tabs button[data-view="' + v + '"]');
      if (tb && !tb.classList.contains("active")) tb.click();
    });
  }
  function initControls() {
    Array.prototype.forEach.call(document.querySelectorAll("#regionMode button"), function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll("#regionMode button").forEach(function (x) { x.classList.remove("active"); });
        b.classList.add("active"); regionMode = b.dataset.mode; renderRegions();
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("#layerToggles button"), function (b) {
      b.addEventListener("click", function () {
        var on = b.classList.toggle("active"), name = b.dataset.layer, lg = L_ru[name];
        if (!lg) return;
        if (name === "strikes") {
          var bar = document.getElementById("strikeBar");
          if (on) { maps.ru.addLayer(lg); renderStrikes(); bar.classList.remove("hidden"); }
          else { maps.ru.removeLayer(lg); stopPlay(); bar.classList.add("hidden"); }
          return;
        }
        if (name === "warehouses") {
          if (!on) { maps.ru.removeLayer(lg); return; }
          maps.ru.addLayer(lg);
          // датасет тянем только при включении слоя; при сбое не оставляем «включённый» пустой
          // слой — иначе отсутствие складов читается как «складов нет», а не «данные не пришли»
          loadWarehouses().then(function (ok) {
            if (!ok) { maps.ru.removeLayer(lg); b.classList.remove("active"); showToast("Слой складов не загрузился — попробуйте ещё раз"); return; }
            renderWarehouses();
          });
          return;
        }
        if (name === "roads") {
          // хотспоты кластеризуются отдельным слоем — прячем/показываем вместе с дорогами
          if (on) { maps.ru.addLayer(lg); if (L_ru.hotspots) maps.ru.addLayer(L_ru.hotspots); }
          else { maps.ru.removeLayer(lg); if (L_ru.hotspots) maps.ru.removeLayer(L_ru.hotspots); }
          return;
        }
        if (on) maps.ru.addLayer(lg); else maps.ru.removeLayer(lg);
      });
    });
    // Кандидаты в удары (radar tripwire) — тоггл добавляем из JS, чтобы не править index.html
    (function initCandidatesToggle() {
      var box = document.getElementById("layerToggles");
      if (box && !box.querySelector("[data-layer=candidates]")) {
        var btn = document.createElement("button");
        btn.setAttribute("data-layer", "candidates");
        btn.textContent = "❓ Кандидаты";
        btn.title = "Возможные удары с ленты radar-map.ru — НЕ подтверждено, требует проверки";
        btn.addEventListener("click", function () {
          var on = btn.classList.toggle("active");
          if (!L_ru.candidates) return;
          if (on) { maps.ru.addLayer(L_ru.candidates); renderCandidates(); }
          else maps.ru.removeLayer(L_ru.candidates);
        });
        box.appendChild(btn);
      }
      loadCandidates();
    })();
    // deep-link: ?layer=warehouses включает слой при загрузке — со статьи про склады маркетплейсов.
    // 🔴 Только ПОСЛЕ навешивания обработчиков выше: в initTabs() этот же click() уходил в пустоту.
    try {
      var _dl = (new URLSearchParams(location.search).get("layer") || "").toLowerCase();
      if (_dl) {
        var _lb = document.querySelector('#layerToggles button[data-layer="' + _dl + '"]');
        if (_lb && !_lb.classList.contains("active")) _lb.click();
      }
    } catch (e) {}
    // strike day-timeline controls
    var sl = document.getElementById("dayslider");
    if (sl) sl.addEventListener("input", function () { stopPlay(); SK.mode = "day"; SK.idx = +this.value; renderStrikes(); });
    var dp = document.getElementById("dayPrev"); if (dp) dp.addEventListener("click", function () { stopPlay(); setStrikeMode("day"); SK.idx = Math.max(0, SK.idx - 1); renderStrikes(); });
    var dn = document.getElementById("dayNext"); if (dn) dn.addEventListener("click", function () { stopPlay(); setStrikeMode("day"); SK.idx = Math.min(SK.dates.length - 1, SK.idx + 1); renderStrikes(); });
    Array.prototype.forEach.call(document.querySelectorAll("#strikeBar .sb-preset"), function (b) {
      b.addEventListener("click", function () { stopPlay(); setStrikeMode(b.dataset.preset); renderStrikes(); });
    });
    // выбор диапазона по датам (от–до)
    var df = document.getElementById("dayFrom"), dt = document.getElementById("dayTo");
    function applyRange() { stopPlay(); SK.mode = "range"; SK.from = df.value; SK.to = dt.value; renderStrikes(); }
    if (df) df.addEventListener("change", applyRange);
    if (dt) dt.addEventListener("change", applyRange);
    var pl = document.getElementById("dayPlay"); if (pl) pl.addEventListener("click", function () { if (SK.playing) stopPlay(); else startPlay(); });
    Array.prototype.forEach.call(document.querySelectorAll("#histFilter button"), function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll("#histFilter button").forEach(function (x) { x.classList.remove("active"); });
        b.classList.add("active"); histFilter = b.dataset.f; renderHistory();
      });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
