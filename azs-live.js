// azs-live.js — ПРОД-виджет «реальное наличие топлива» на карте АЗС (/karta-azs).
// Обкатан в песочнице /karta-azs-lab (azs-lab.js) и промоушен по ТЗ §9. Прод app.js
// не трогается — фича живёт overlay-скриптом поверх него (тот же приём, что в lab).
// ТЗ: docs/agents/tz-fuel-availability-2026-07.md
//
// «Я тут»: отметка наличия топлива — device-local (localStorage) + общий бэкенд
// /api/azs-votes (Upstash Redis) для агрегата по водителям и перекраски маркеров.
// Рубильник: любая ошибка API → остаёмся на device-local + регион-оценке, карта не пустеет.
// Хук: shim в karta-azs.html отдаёт window.__azsMap → popupopen → marker._azs (id станции).
(function () {
  "use strict";

  var VOTES_KEY = "azs-lab-votes";
  var CID_KEY = "azs-lab-cid";

  // ponytail: 3 ч — калибровочный порог «протухания», подбирается на реальных данных.
  // ?labttl=<секунды> укорачивает его для ручного теста, чтобы не ждать три часа.
  var TTL_MS = (function () {
    var m = /[?&]labttl=(\d+)/.exec(location.search);
    return m ? parseInt(m[1], 10) * 1000 : 3 * 60 * 60 * 1000;
  })();

  var STATUSES = [
    { k: "yes",   icon: "✅", label: "Есть",    short: "Есть топливо" },
    { k: "no",    icon: "⛔", label: "Нет",     short: "Нет топлива" },
    { k: "queue", icon: "⏳", label: "Очередь", short: "Очередь" },
    { k: "limit", icon: "🔢", label: "Лимит",   short: "Лимит на литры" }
  ];
  function statusBy(k) {
    for (var i = 0; i < STATUSES.length; i++) if (STATUSES[i].k === k) return STATUSES[i];
    return null;
  }

  // ─── storage ───────────────────────────────────────────────────────────────
  function loadVotes() {
    try { return JSON.parse(localStorage.getItem(VOTES_KEY)) || {}; } catch (_) { return {}; }
  }
  function saveVote(id, status, now) {
    var v = loadVotes();
    v[id] = { status: status, observed_at: now || Date.now() };
    try { localStorage.setItem(VOTES_KEY, JSON.stringify(v)); } catch (_) {}
    return v[id];
  }
  function getVote(id) { return loadVotes()[id] || null; }

  // Анонимный id устройства — задел под будущий общий бэкенд (сейчас никуда не уходит).
  function cid() {
    var c = null;
    try { c = localStorage.getItem(CID_KEY); } catch (_) { return "nostore"; }
    if (!c) {
      c = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : "cid-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      try { localStorage.setItem(CID_KEY, c); } catch (_) {}
    }
    return c;
  }

  // ─── time ──────────────────────────────────────────────────────────────────
  function isStale(vote, now) { return ((now || Date.now()) - vote.observed_at) > TTL_MS; }
  function ago(ts, now) {
    var s = Math.max(0, ((now || Date.now()) - ts) / 1000);
    if (s < 60) return "только что";
    var m = Math.floor(s / 60); if (m < 60) return m + " мин назад";
    var h = Math.floor(m / 60); if (h < 24) return h + " ч назад";
    return Math.floor(h / 24) + " дн назад";
  }

  // ─── общий бэкенд (Upstash через /api/azs-votes) ─────────────────────────────
  // Рубильник: любая ошибка сети/сервера → null, виджет остаётся device-local,
  // карта не пустеет (нет SPOF на бэкенде).
  var API = "/api/azs-votes";
  function fetchAgg(id) {
    return fetch(API + "?ids=" + encodeURIComponent(id))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j ? j[id] : null; })
      .catch(function () { return null; });
  }
  function postVote(id, status) {
    return fetch(API, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ station_id: id, status: status, cid: cid() })
    }).catch(function () { /* локально уже сохранено */ });
  }
  function fetchAggMany(ids) {
    return fetch(API + "?ids=" + encodeURIComponent(ids.join(",")))
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; }); // рубильник
  }

  // ─── css ───────────────────────────────────────────────────────────────────
  function injectCss() {
    if (document.getElementById("azs-lab-css")) return;
    var s = document.createElement("style");
    s.id = "azs-lab-css";
    s.textContent = [
      ".azs-lab-w{margin-top:7px;padding-top:7px;border-top:1px solid rgba(0,0,0,.12)}",
      ".azs-lab-q{font-size:11px;font-weight:700;margin-bottom:5px}",
      ".azs-lab-btns{display:flex;gap:4px;flex-wrap:wrap}",
      ".azs-lab-b{flex:1 1 auto;min-width:58px;cursor:pointer;border:1px solid rgba(0,0,0,.18);",
      "background:#fff;border-radius:6px;padding:5px 4px;font:600 11px/1.15 inherit;color:#222;",
      "white-space:nowrap;transition:transform .06s}",
      ".azs-lab-b:hover{background:#f2f2f2}.azs-lab-b:active{transform:scale(.95)}",
      ".azs-lab-mine{font-size:11px;font-weight:700;display:flex;align-items:center;gap:5px;flex-wrap:wrap}",
      ".azs-lab-age{font-weight:400;opacity:.6}",
      ".azs-lab-edit{cursor:pointer;text-decoration:underline;opacity:.6;font-weight:400}",
      ".azs-lab-stale{color:#8a6d00;background:#fff6d5;border-radius:5px;padding:4px 6px;",
      "font-size:10px;margin-bottom:5px}",
      ".azs-lab-note{font-size:10px;opacity:.55;margin-top:4px}",
      ".azs-lab-comm{margin-bottom:7px}",
      ".azs-lab-comm-line{font-size:11px;font-weight:700}",
      ".azs-lab-verdict{font-size:12px;font-weight:800;padding:5px 7px;border-radius:6px;margin-bottom:5px}",
      ".azs-lab-vsub{display:block;font-size:10px;font-weight:500;opacity:.85;margin-top:2px}",
      ".azs-lab-v-yes{background:#e7f5ec;color:#1a7f37}",
      ".azs-lab-v-no{background:#fce9e7;color:#c0271a}",
      ".azs-lab-v-warn{background:#fff6d5;color:#8a6d00}"
    ].join("");
    document.head.appendChild(s);
  }

  // ─── widget ────────────────────────────────────────────────────────────────
  // 🔴 НЕ звать popup.update() — он перерисовывает контент из исходной HTML-строки
  // и стирает наш виджет. Нужен только пересчёт позиции под новую высоту.
  function reflow(popup) {
    if (!popup) return;
    try { if (popup._updatePosition) popup._updatePosition(); } catch (_) {}
    try { if (popup._adjustPan) popup._adjustPan(); } catch (_) {}
  }

  // box = комм-строка (общий агрегат) + self-блок (своя отметка/кнопки), обновляются раздельно.
  function render(box, station, popup) {
    box.textContent = "";
    var comm = document.createElement("div"); comm.className = "azs-lab-comm"; box.appendChild(comm);
    var self = document.createElement("div"); self.className = "azs-lab-self"; box.appendChild(self);
    renderSelf(self, comm, station, popup);
    loadCommunity(comm, station, popup);
  }

  // Пороги слияния §4.5 — калибровочные ручки, поднять при спаме/шуме.
  var MIN_VOTES = 1;   // сколько свежих отметок, чтобы вообще перебить регион-оценку
  var CONF_MIN = 0.3;  // порог confidence (1 единодушная свежая ≈0.33 — на грани, помечаем «1 водитель»)
  var NEAR_TIE = 0.6;  // доля веса победителя ниже → «мнения расходятся»
  function verdictClass(k) { return k === "yes" ? "azs-lab-v-yes" : k === "no" ? "azs-lab-v-no" : "azs-lab-v-warn"; }

  // Общий агрегат из бэкенда + вердикт слияния (§4.5): живое бьёт регион-оценку,
  // если свежих отметок достаточно и они согласованы. Ошибка → пусто (рубильник).
  function loadCommunity(comm, station, popup) {
    fetchAgg(station.id).then(function (agg) {
      comm.textContent = "";
      if (!agg) return; // API недоступен — молча остаёмся на своих отметках
      if (!agg.count) {
        var empty = document.createElement("div");
        empty.className = "azs-lab-comm-line";
        empty.textContent = "👥 За 6 ч отметок ещё нет — будьте первым.";
        comm.appendChild(empty);
        reflow(popup);
        return;
      }

      var wins = agg.count >= MIN_VOTES && agg.confidence >= CONF_MIN;
      var st = statusBy(agg.top_status);

      // 1) вердикт — только когда живое перебивает регион-оценку
      if (wins) {
        var v = document.createElement("div");
        if (agg.top_share < NEAR_TIE) {
          v.className = "azs-lab-verdict azs-lab-v-warn";
          v.textContent = "⚠️ Свежие отметки расходятся — ситуация меняется";
        } else {
          v.className = "azs-lab-verdict " + verdictClass(agg.top_status);
          v.appendChild(document.createTextNode("⛽ Сейчас: " + (st ? st.icon + " " + st.short : agg.top_status)));
          var sub = document.createElement("span");
          sub.className = "azs-lab-vsub";
          sub.textContent = "по отметкам водителей · " + agg.count + (agg.count === 1 ? " отметка" : "")
            + (agg.last_observed_at ? " · " + ago(agg.last_observed_at) : "");
          v.appendChild(sub);
        }
        comm.appendChild(v);
      }

      // 2) детальная строка
      var segs = STATUSES.filter(function (s) { return agg.breakdown[s.k]; })
        .map(function (s) { return s.icon + agg.breakdown[s.k]; }).join("  ");
      var line = document.createElement("div");
      line.className = "azs-lab-comm-line";
      line.textContent = "👥 За 6 ч: " + segs;
      if (agg.last_observed_at) {
        var a = document.createElement("span");
        a.className = "azs-lab-age";
        a.textContent = "  · последняя " + ago(agg.last_observed_at);
        line.appendChild(a);
      }
      comm.appendChild(line);

      // 3) живого мало — честно указываем на регион-оценку выше (нативный бейдж попапа)
      if (!wins) {
        var hint = document.createElement("div");
        hint.className = "azs-lab-note";
        hint.textContent = "Пока мало отметок — ориентир: оценка по сети/региону выше.";
        comm.appendChild(hint);
      }

      // 4) дисклеймер
      var note = document.createElement("div");
      note.className = "azs-lab-note";
      note.textContent = "Сообщения водителей, не гарантия.";
      comm.appendChild(note);
      reflow(popup);
    });
  }

  function renderSelf(self, comm, station, popup) {
    self.textContent = "";
    var vote = getVote(station.id);
    var stale = vote && isStale(vote);
    if (!vote || stale) { renderButtons(self, comm, station, popup, stale ? vote : null); return; }

    var st = statusBy(vote.status);
    var mine = document.createElement("div");
    mine.className = "azs-lab-mine";
    mine.appendChild(document.createTextNode("Ваша отметка: " + (st ? st.icon + " " + st.short : vote.status)));
    var age = document.createElement("span");
    age.className = "azs-lab-age";
    age.textContent = "· " + ago(vote.observed_at);
    mine.appendChild(age);
    var edit = document.createElement("span");
    edit.className = "azs-lab-edit";
    edit.textContent = "изменить";
    edit.addEventListener("click", function () { renderButtons(self, comm, station, popup, null); });
    mine.appendChild(edit);
    self.appendChild(mine);
    reflow(popup);
  }

  function renderButtons(self, comm, station, popup, staleVote) {
    self.textContent = "";
    if (staleVote) {
      var warn = document.createElement("div");
      warn.className = "azs-lab-stale";
      var sv = statusBy(staleVote.status);
      warn.textContent = "Ваша отметка «" + (sv ? sv.short : staleVote.status) + "» устарела ("
        + ago(staleVote.observed_at) + ") — неподтверждено, отметьте заново.";
      self.appendChild(warn);
    }
    var q = document.createElement("div");
    q.className = "azs-lab-q";
    q.textContent = "Вы здесь? Отметьте за 2 сек:";
    self.appendChild(q);

    var row = document.createElement("div");
    row.className = "azs-lab-btns";
    STATUSES.forEach(function (s) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "azs-lab-b";
      b.textContent = s.icon + " " + s.label;
      b.addEventListener("click", function () {
        saveVote(station.id, s.k);       // на устройстве — мгновенно
        postVote(station.id, s.k);       // в общий бэкенд — фоном (ошибка не критична)
        cacheDrop(station.id);           // свой голос — сброс кэша, чтобы recolor увидел смену
        renderSelf(self, comm, station, popup);
        loadCommunity(comm, station, popup); // подтянуть свежий агрегат с учётом своей отметки
        if (scheduleRecolor) scheduleRecolor(); // маркер может сменить цвет от своей отметки
      });
      row.appendChild(b);
    });
    self.appendChild(row);
    reflow(popup);
  }

  function onPopupOpen(e) {
    var mk = e.popup && e.popup._source;
    if (!mk || !mk._azs || !mk._azs.id) return;             // не станция АЗС — не трогаем
    var el = e.popup.getElement();
    var host = el && el.querySelector(".azs-pop");
    if (!host || host.querySelector(".azs-lab-w")) return;   // уже вставлено в этот попап
    injectCss();
    var box = document.createElement("div");
    box.className = "azs-lab-w";
    host.appendChild(box);
    render(box, mk._azs, e.popup);
  }

  // ─── перекраска маркеров по слитому статусу (§4.5) ───────────────────────────
  // Маркеры строит app.js (регион-оценка). Здесь снаружи перекрашиваем ВИДИМЫЕ
  // станции, где живое чисто побеждает: тот же кружок + яркое кольцо-гало (провенанс
  // «live» на карте). Протухли/перестали побеждать → откат на исходную регион-иконку.
  var LIVE_COLORS = { yes: "#2f9e57", no: "#d23a2e", queue: "#ef9a1a", limit: "#e8c520" };
  var scheduleRecolor = null;

  // ─── клиентский кэш агрегатов для перекраски ─────────────────────────────────
  // recolorVisible гоняется на каждый moveend/zoomend; при панораме одни и те же
  // станции (в основном пустые) перезапрашивались десятками → жгли Upstash
  // (free ~10k команд/день). Кэшируем агрегат по станции на короткое окно: повторный
  // проход по уже виденным = 0 обращений к API. Свой голос сбрасывает запись (cacheDrop).
  // Попап (fetchAgg) намеренно НЕ кэшируем — он редкий, ручной, и должен быть максимально
  // свежим (свежее «нет» под ударами). Жжёт лимит именно bulk-перекраска, её и кэшируем.
  // ponytail: TTL 60с — калибровочная ручка; голоса капают медленно, но свежесть не душим.
  //           Кэш ограничен числом станций (~9609 мелких записей) — прунинг не нужен.
  var AGG_TTL_MS = 60 * 1000;
  var aggCache = {};                              // id → { agg, at }
  function cacheGet(id, now) {
    var e = aggCache[id];
    return (e && (now || Date.now()) - e.at < AGG_TTL_MS) ? e : null;
  }
  function cachePut(id, agg, now) { aggCache[id] = { agg: agg, at: now || Date.now() }; }
  function cacheDrop(id) { delete aggCache[id]; }

  function liveIcon(status) {
    var c = LIVE_COLORS[status] || "#7a7e85";
    var html = '<div style="width:36px;height:36px;display:flex;align-items:center;justify-content:center">'
      + '<svg width="18" height="18" viewBox="0 0 18 18">'
      + '<circle cx="9" cy="9" r="8" fill="none" stroke="' + c + '" stroke-opacity=".9" stroke-width="2"/>'
      + '<circle cx="9" cy="9" r="5" fill="' + c + '" stroke="#000" stroke-opacity=".35" stroke-width="1"/>'
      + '</svg></div>';
    return L.divIcon({ className: "azs-divicon azs-lab-live", html: html, iconSize: [36, 36], iconAnchor: [18, 18], popupAnchor: [0, -6] });
  }

  // Чистая победа живого (не near-tie) — только тогда трогаем цвет маркера.
  function winsClean(agg) {
    return agg && agg.count >= MIN_VOTES && agg.confidence >= CONF_MIN && agg.top_share >= NEAR_TIE;
  }

  function clusterGroup() {
    var g = null;
    window.__azsMap.eachLayer(function (l) {
      if (g || !l || typeof l.getLayers !== "function") return;
      var ls = l.getLayers();
      if (ls.length && ls.some(function (k) { return k && k._azs; })) g = l;
    });
    return g;
  }

  function recolorVisible() {
    if (!window.__azsMap) return;
    var grp = clusterGroup();
    if (!grp) return;
    var byId = {};
    grp.getLayers().forEach(function (m) {
      if (m._azs && m._azs.id && m._icon) byId[m._azs.id] = m; // только реально отрисованные (не в кластере)
    });
    var ids = Object.keys(byId);
    if (!ids.length) return;
    for (var i = 0; i < ids.length; i += 50) {         // сервер режет ids до 60 — чанкуем по 50
      applyChunk(byId, ids.slice(i, i + 50));
    }
  }
  // Применить один агрегат к маркеру: чистая победа живого → live-иконка + гало,
  // иначе (протухло/near-tie/пусто) откат на регион-иконку. Идемпотентно (гард по _liveStatus).
  function applyAgg(m, agg) {
    if (!m || !m.setIcon) return;
    if (winsClean(agg)) {
      if (m._liveStatus !== agg.top_status) {
        if (!m._origIcon) m._origIcon = m.getIcon ? m.getIcon() : m.options.icon;
        m.setIcon(liveIcon(agg.top_status));
        m._liveStatus = agg.top_status;
      }
    } else if (m._liveStatus) {              // перестало побеждать/протухло → назад на регион-иконку
      if (m._origIcon) m.setIcon(m._origIcon);
      m._liveStatus = null;
    }
  }

  function applyChunk(byId, chunk) {
    var now = Date.now(), toFetch = [];
    chunk.forEach(function (id) {
      var hit = cacheGet(id, now);
      if (hit) applyAgg(byId[id], hit.agg);   // из кэша — без сети
      else toFetch.push(id);
    });
    if (!toFetch.length) return;              // всё из кэша — ни одного обращения к API
    fetchAggMany(toFetch).then(function (res) {
      if (!res) return;                       // рубильник: сеть недоступна → маркеры регион-цветом
      var t = Date.now();
      toFetch.forEach(function (id) {
        cachePut(id, res[id], t);
        applyAgg(byId[id], res[id]);
      });
    });
  }

  function bind() {
    if (!window.__azsMap) return false;
    window.__azsMap.on("popupopen", onPopupOpen);
    var t;
    scheduleRecolor = function () { clearTimeout(t); t = setTimeout(recolorVisible, 400); };
    window.__azsMap.on("moveend", scheduleRecolor);
    window.__azsMap.on("zoomend", scheduleRecolor);
    setTimeout(recolorVisible, 1500); // первичный проход после отрисовки станций
    console.info("[azs-lab] «Я тут» подключён к карте АЗС (TTL " + Math.round(TTL_MS / 1000) + "s), перекраска маркеров вкл");
    return true;
  }

  // ─── self-check: открыть /karta-azs-lab?labtest=1 ──────────────────────────
  // Минимальная проверка логики, которая ломается первой: round-trip отметки,
  // определение протухания, словесный возраст, стабильность cid.
  function selfTest() {
    var id = "__selftest__", now = 1000000000000;
    var saved = saveVote(id, "queue", now);
    console.assert(getVote(id).status === "queue", "[azs-lab] round-trip: статус не сохранился");
    console.assert(getVote(id).observed_at === now, "[azs-lab] round-trip: время не сохранилось");
    console.assert(isStale(saved, now + TTL_MS + 1) === true, "[azs-lab] протухание не сработало");
    console.assert(isStale(saved, now + 1) === false, "[azs-lab] свежая отметка помечена протухшей");
    console.assert(ago(now, now) === "только что", "[azs-lab] ago(0)");
    console.assert(ago(now, now + 5 * 60000) === "5 мин назад", "[azs-lab] ago(5m)");
    console.assert(ago(now, now + 3 * 3600000) === "3 ч назад", "[azs-lab] ago(3h)");
    console.assert(cid() === cid() && cid().length > 3, "[azs-lab] cid пустой/нестабилен");
    // кэш агрегатов перекраски: hit в окне TTL, miss после TTL, drop чистит
    cachePut("__c__", { count: 2 }, now);
    console.assert(cacheGet("__c__", now + 1000) && cacheGet("__c__", now + 1000).agg.count === 2, "[azs-lab] кэш: свежий hit потерян");
    console.assert(cacheGet("__c__", now + AGG_TTL_MS + 1) === null, "[azs-lab] кэш: протухший всё ещё отдаётся");
    cacheDrop("__c__");
    console.assert(cacheGet("__c__", now) === null, "[azs-lab] кэш: drop не очистил");
    var v = loadVotes(); delete v[id];
    try { localStorage.setItem(VOTES_KEY, JSON.stringify(v)); } catch (_) {}
    console.info("[azs-lab] self-test done — молчание ассертов выше = логика цела");
  }

  if (!bind()) window.addEventListener("azsmapready", bind, { once: true });
  if (/[?&]labtest=1/.test(location.search)) selfTest();
})();
