// azs-lab.js — песочница скрытой страницы /karta-azs-lab (тест-копия /karta-azs).
// Здесь и ТОЛЬКО здесь живёт код новых фич «реальное наличие топлива».
// ТЗ: docs/agents/tz-fuel-availability-2026-07.md
// Прод-страница /karta-azs и общий app.js остаются нетронутыми, пока фича не доведена.
//
// v1 «Я тут»: отметка наличия топлива, живёт ТОЛЬКО на устройстве (localStorage).
// ponytail: device-local by design — общий краудсорс требует write-бэкенда (Vercel KV/Upstash),
//           это следующий отдельный шаг по ТЗ. Здесь обкатываем взаимодействие и свежесть.
// Хук: shim в karta-azs-lab.html отдаёт window.__azsMap → popupopen → marker._azs (id станции).
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
      ".azs-lab-note{font-size:10px;opacity:.55;margin-top:4px}"
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

  function render(box, station, popup) {
    box.textContent = "";
    var vote = getVote(station.id);
    var stale = vote && isStale(vote);
    if (!vote || stale) { renderButtons(box, station, popup, stale ? vote : null); return; }

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
    edit.addEventListener("click", function () { renderButtons(box, station, popup, null); });
    mine.appendChild(edit);
    box.appendChild(mine);
    var note = document.createElement("div");
    note.className = "azs-lab-note";
    note.textContent = "Отметка видна только вам на этом устройстве.";
    box.appendChild(note);
    reflow(popup);
  }

  function renderButtons(box, station, popup, staleVote) {
    box.textContent = "";
    if (staleVote) {
      var warn = document.createElement("div");
      warn.className = "azs-lab-stale";
      var sv = statusBy(staleVote.status);
      warn.textContent = "Ваша отметка «" + (sv ? sv.short : staleVote.status) + "» устарела ("
        + ago(staleVote.observed_at) + ") — неподтверждено, отметьте заново.";
      box.appendChild(warn);
    }
    var q = document.createElement("div");
    q.className = "azs-lab-q";
    q.textContent = "Вы здесь? Отметьте за 2 сек:";
    box.appendChild(q);

    var row = document.createElement("div");
    row.className = "azs-lab-btns";
    STATUSES.forEach(function (s) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "azs-lab-b";
      b.textContent = s.icon + " " + s.label;
      b.addEventListener("click", function () {
        saveVote(station.id, s.k);
        cid(); // анонимный id устройства заводим при первой отметке
        render(box, station, popup);
      });
      row.appendChild(b);
    });
    box.appendChild(row);
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

  function bind() {
    if (!window.__azsMap) return false;
    window.__azsMap.on("popupopen", onPopupOpen);
    console.info("[azs-lab] «Я тут» подключён к карте АЗС (TTL " + Math.round(TTL_MS / 1000) + "s)");
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
    var v = loadVotes(); delete v[id];
    try { localStorage.setItem(VOTES_KEY, JSON.stringify(v)); } catch (_) {}
    console.info("[azs-lab] self-test done — молчание ассертов выше = логика цела");
  }

  document.addEventListener("DOMContentLoaded", function () {
    var b = document.createElement("div");
    b.textContent = "🧪 LAB — тест наличия топлива";
    b.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:99999;background:#d23a2e;" +
      "color:#fff;font:600 12px/1 system-ui,sans-serif;padding:6px 10px;border-radius:6px;" +
      "opacity:.9;pointer-events:none";
    document.body.appendChild(b);
  });

  if (!bind()) window.addEventListener("azsmapready", bind, { once: true });
  if (/[?&]labtest=1/.test(location.search)) selfTest();
})();
