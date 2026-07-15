(function () {
  "use strict";
  // Карточка «свежая сводка с обложкой» для карт (idea Серёги 14.07). Карты —
  // точки входа с высоким отказом (/karta-bpla ~22%): читатель посмотрел и ушёл.
  // Эта плашка справа-сверху показывает ОБЛОЖКУ последней сводки (на картинке уже
  // город удара + подпись что произошло) → клик уводит читать /news/<дата>, а не
  // закрывать вкладку. Растит глубину визита (#5 бэклога роста).
  // Самодостаточна (инжектит свой CSS), докается в общий window.__nudgeDock из
  // vpn-nudge.js — одна карточка открыта за раз, не перекрывает VPN/подписку.
  // ponytail: данные тянет из уже деплоящегося /data/news-archive.json (no-cache),
  // обложку строит по предсказуемому имени /assets/cover-<дата>.png; при 404
  // обложки карточка просто не показывается (не ломает страницу).

  var K = "art_nudge";          // localStorage: 'dock' | 'seen:<date>'
  var GOAL = "art_read";
  var MONTHS = ["января","февраля","марта","апреля","мая","июня","июля",
                "августа","сентября","октября","ноября","декабря"];

  function seenState() { try { return localStorage.getItem(K) || ""; } catch (e) { return ""; } }
  function markSeen(date) { try { localStorage.setItem(K, "seen:" + date); } catch (e) {} }
  function track() {
    try { if (window.ym) ym(110490245, "reachGoal", GOAL); } catch (e) {}
    try { if (window.va) va("event", { name: GOAL }); } catch (e) {}
  }

  function rusDate(iso) {
    var p = String(iso).split("-");
    if (p.length !== 3) return iso;
    return parseInt(p[2], 10) + " " + MONTHS[parseInt(p[1], 10) - 1];
  }

  // Заголовок из strikes сводки: «<город> и ещё N ударов» (стиль страниц /news).
  function makeTitle(brief) {
    var s = (brief && brief.strikes) || [];
    if (!s.length) return "Итоги дня: удары и дефицит топлива";
    var city = s[0].city || "";
    var extra = s.length - 1;
    if (!city) return s.length + " ударов за сутки";
    if (extra <= 0) return "Удар: " + city;
    return city + " и ещё " + extra + " " + plural(extra, "удар", "удара", "ударов");
  }
  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
    return many;
  }

  // есть ли уже раскрытая соседняя плашка (vpn/sub)? тогда уступаем — стартуем язычком
  function siblingOpen() {
    return !!document.querySelector(".vpn-nudge:not(.nudge-out), .sub-nudge:not(.nudge-out)");
  }

  function build(date, title) {
    var cover = "/assets/cover-" + date + ".png";
    var href = "/news/" + date;
    var d = document.createElement("div");
    d.className = "art-nudge";
    d.innerHTML =
      '<button type="button" class="art-nudge-x" aria-label="Закрыть">×</button>' +
      '<a class="art-nudge-lnk" href="' + href + '">' +
        '<img class="art-nudge-img" src="' + cover + '" alt="Сводка за ' + rusDate(date) + '" loading="lazy">' +
        '<div class="art-nudge-body">' +
          '<div class="art-nudge-kick">📰 Свежая сводка · ' + rusDate(date) + '</div>' +
          '<div class="art-nudge-t">' + title + '</div>' +
          '<div class="art-nudge-cta">Читать сводку →</div>' +
        '</div>' +
      '</a>';
    d.querySelector(".art-nudge-lnk").addEventListener("click", function () { track(); markSeen(date); });
    return d;
  }

  function wireDock(card, date, startDocked) {
    var xbtn = card.querySelector(".art-nudge-x");
    var dockFn = window.__nudgeDock;
    if (dockFn) {
      var d = dockFn(card, { key: K, label: "Свежая сводка", icon: NEWS_ICON, side: "right",
                             pos: "top:60%", accent: "#d23a2e", startDocked: !!startDocked });
      xbtn.addEventListener("click", d.collapse);
    } else {
      xbtn.addEventListener("click", function () { markSeen(date); card.remove(); });
    }
  }

  // газета-иконка для язычка (сибling к щиту VPN / самолётику подписки)
  var NEWS_ICON =
    '<svg class="guard-face" viewBox="0 0 26 26" aria-hidden="true">' +
      '<circle class="sh-body" cx="13" cy="13" r="11"/>' +
      '<g class="face" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round">' +
        '<rect x="8" y="8" width="10" height="10" rx="1.2"/>' +
        '<path d="M10 11h6M10 13.5h6M10 16h4"/>' +
      '</g>' +
    '</svg>';

  var shown = false;
  function show(date, title, forceDock) {
    if (shown) return;
    shown = true;
    var d = build(date, title);
    // обложки нет (404) → не показываем сломанную карточку
    d.querySelector(".art-nudge-img").addEventListener("error", function () {
      d.remove();
    });
    var dock = forceDock || siblingOpen();
    document.body.appendChild(d);
    if (dock) {
      d.classList.add("in"); d.classList.add("nudge-out"); // сразу язычком
      wireDock(d, date, true);
    } else {
      wireDock(d, date, false);
      void d.offsetWidth; // форс-reflow → переход играет надёжно даже в фоновой вкладке
      d.classList.add("in");
    }
  }

  function css() {
    var s = document.createElement("style");
    s.textContent =
      ".art-nudge{position:fixed;right:0;top:78px;z-index:1250;width:290px;max-width:calc(100vw - 28px);" +
      "background:var(--surface,#fff);border:1px solid var(--line,#e4e4e7);border-right:none;" +
      "border-radius:14px 0 0 14px;box-shadow:0 8px 30px rgba(0,0,0,.22);overflow:hidden;" +
      "transform:translateX(115%);transition:transform .45s cubic-bezier(.22,1,.36,1)}" +
      ".art-nudge.in{transform:translateX(0)}" +
      ".art-nudge.nudge-out{transform:translateX(115%)}" +
      ".art-nudge-x{position:absolute;top:6px;right:9px;z-index:2;background:rgba(0,0,0,.45);border:none;" +
      "color:#fff;font-size:16px;line-height:1;cursor:pointer;padding:1px 7px;border-radius:20px}" +
      ".art-nudge-x:hover{background:rgba(0,0,0,.7)}" +
      ".art-nudge-lnk{display:block;text-decoration:none;color:inherit}" +
      ".art-nudge-img{display:block;width:100%;height:150px;object-fit:cover;background:var(--surface2,#f0f0f0)}" +
      ".art-nudge-body{padding:11px 14px 13px}" +
      ".art-nudge-kick{color:var(--red,#d23a2e);font-size:10.5px;font-weight:800;letter-spacing:.3px;text-transform:uppercase}" +
      ".art-nudge-t{color:var(--ink,#111);font-size:14px;font-weight:800;line-height:1.28;margin:5px 0 8px;font-family:var(--disp,inherit)}" +
      ".art-nudge-cta{color:var(--teal,#12a594);font-size:12.5px;font-weight:800}" +
      ".art-nudge-lnk:hover .art-nudge-cta{text-decoration:underline}" +
      "@media(max-width:560px){.art-nudge{right:10px;left:10px;top:10px;width:auto;border-radius:14px;border-right:1px solid var(--line,#e4e4e7);" +
      "transform:translateY(-140%)}.art-nudge.in{transform:translateY(0)}.art-nudge.nudge-out{transform:translateY(-140%)}" +
      ".art-nudge-img{height:130px}}";
    document.head.appendChild(s);
  }

  function init() {
    css();
    fetch("/data/news-archive.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.briefs) return;
        var dates = Object.keys(j.briefs).sort().reverse();
        resolveCover(dates, j.briefs, 0);
      })
      .catch(function () {});
  }

  // Свежайшая дата, у которой РЕАЛЬНО есть обложка: сводка Гермеса может опережать
  // генерацию обложки (build-covers). Пре-probe детач-картинкой — показываем карточку
  // только когда обложка загрузилась (значит и в DOM отрисуется мгновенно, из кеша).
  // ponytail: окно отставания обложки ≤1 сутки → 3 попытки с запасом.
  function resolveCover(dates, briefs, i) {
    if (i >= dates.length || i >= 3) return; // обложек нет в разумном окне → карточку не показываем
    var date = dates[i];
    var probe = new Image();
    probe.onload = function () { dispatch(date, makeTitle(briefs[date])); };
    probe.onerror = function () { resolveCover(dates, briefs, i + 1); };
    probe.src = "/assets/cover-" + date + ".png";
  }

  function dispatch(date, title) {
    var st = seenState();
    var docked = (st === "seen:" + date || st === "dock"); // видел эту дату / ранее свернул → язычком
    arm(date, title, docked);
  }

  // показать после первого взаимодействия (пан/скролл/клик) или через 10с —
  // ловим «вовлечённого, но собравшегося уйти» читателя, не долбим сразу
  function arm(date, title, forceDock) {
    if (forceDock) { show(date, title, true); return; }
    var fired = false, t;
    function trigger() {
      if (fired) return;
      fired = true;
      document.removeEventListener("pointerdown", trigger, true);
      document.removeEventListener("wheel", trigger, { passive: true });
      window.removeEventListener("scroll", trigger, { passive: true });
      clearTimeout(t);
      show(date, title, false);
    }
    document.addEventListener("pointerdown", trigger, true);
    document.addEventListener("wheel", trigger, { passive: true });
    window.addEventListener("scroll", trigger, { passive: true });
    t = setTimeout(trigger, 10000);
  }

  if (document.readyState !== "loading") init();
  else document.addEventListener("DOMContentLoaded", init);
})();
