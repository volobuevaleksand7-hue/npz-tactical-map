(function () {
  "use strict";
  // Friendly, one-time subscribe nudge for the main map. Replaces the static
  // #tgAlertBanner: slides in from the left AFTER the reader engages with the
  // map (pan/zoom/click) — i.e. once they're a bit loyal, gdebenz-style — with
  // a 45s fallback so a purely passive reader still sees it once.
  // Self-contained (injects its own CSS) so it can drop onto any map page.
  // ponytail: shown-once + dismiss tracked in localStorage; edit the 3 copy
  // constants below to tune. BOT is a single line to swap if the handle changes.

  var BOT   = "https://t.me/BPLAlert_bot"; // рабочий бот (в коде везде он); поменять на @fuelalert = одна строка
  var TITLE = "Не теряйте карту 💚";
  var BODY  = "Сайт могут заблокировать. В Telegram всегда рабочая ссылка на карту, оповещения о тревогах и сводки об ударах и дефиците топлива.";

  var K = "sub_nudge_x";
  // Telegram-сторож: синий диск, серьёзные глаза/брови, самолётик снизу (сибling к guard-щиту VPN)
  var TG_ICON =
    '<svg class="guard-face" viewBox="0 0 26 26" aria-hidden="true">' +
      '<circle class="sh-body" cx="13" cy="13" r="11"/>' +
      '<g class="face">' +
        '<path class="brow" d="M8 9.6 L11 10.5"/><path class="brow" d="M18 9.6 L15 10.5"/>' +
        '<circle class="eye" cx="9.9" cy="12.2" r="1.5"/><circle class="eye" cx="16.1" cy="12.2" r="1.5"/>' +
        '<path class="plane" d="M7.6 17.6 L18.6 14.3 L13.3 19.9 L12.3 17 Z"/>' +
      '</g>' +
    '</svg>';
  var st; try { st = localStorage.getItem(K); } catch (e) {}
  if (st === "done") return; // уже подписался / поставил на экран — больше не показываем

  function done() { try { localStorage.setItem(K, "done"); } catch (e) {} }
  function track(goal) {
    try { if (window.ym) ym(110490245, "reachGoal", goal); } catch (e) {}
    try { if (window.va) va("event", { name: goal }); } catch (e) {}
  }

  function build() {
    var d = document.createElement("div");
    d.className = "sub-nudge";
    d.innerHTML =
      '<button type="button" class="sub-nudge-x" aria-label="Закрыть">×</button>' +
      '<div class="sub-nudge-t">' + TITLE + '</div>' +
      '<div class="sub-nudge-b">' + BODY + '</div>' +
      '<a class="sub-nudge-tg" href="' + BOT + '" target="_blank" rel="noopener">✈️ Telegram — подписаться</a>' +
      '<a class="sub-nudge-ins" href="/install">📲 Добавить на экран</a>';
    d.querySelector(".sub-nudge-tg").addEventListener("click", function () { track("sub_tg"); done(); });
    d.querySelector(".sub-nudge-ins").addEventListener("click", function () { track("sub_install"); done(); });
    return d; // крестик провязывает wireDock (сворачивает в язычок, не удаляет)
  }

  // крестик → свернуть в язычок у левого края (общий dock из vpn-nudge.js); fallback — удалить
  function wireDock(card, sd) {
    var xbtn = card.querySelector(".sub-nudge-x");
    var dockFn = window.__nudgeDock;
    if (dockFn) {
      var d = dockFn(card, { key: K, label: "Подписка в Telegram", icon: TG_ICON, pos: "top:38%", accent: "#2AABEE", startDocked: !!sd });
      xbtn.addEventListener("click", d.collapse);
    } else {
      xbtn.addEventListener("click", function () { done(); card.remove(); });
    }
  }

  var shown = false;
  function show() {
    if (shown) return;
    shown = true;
    var d = build();
    document.body.appendChild(d);
    wireDock(d, false);
    // двойной rAF, чтобы transition от начального translateX сработал
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        d.classList.add("in");
        setTimeout(function () { d.classList.add("blink"); }, 500);
      });
    });
  }

  // на загрузке пользователь ранее свернул попап → показываем сразу язычком
  function startDocked() {
    var d = build();
    d.classList.add("in");        // покоящийся transform = 0
    d.classList.add("nudge-out"); // но свёрнут (перебивает .in), без анимации до вставки
    document.body.appendChild(d);
    wireDock(d, true);
  }

  function arm() {
    var map = document.getElementById("map");
    if (!map) { return; }
    var fired = false, t;
    function trigger() {
      if (fired) return;
      fired = true;
      map.removeEventListener("pointerdown", trigger, true);
      map.removeEventListener("wheel", trigger, { passive: true });
      clearTimeout(t);
      show();
    }
    map.addEventListener("pointerdown", trigger, true); // пан/клик по метке
    map.addEventListener("wheel", trigger, { passive: true }); // зум колесом
    t = setTimeout(trigger, 45000); // ponytail: fallback — пассивный читатель тоже увидит 1 раз
  }

  var css = document.createElement("style");
  css.textContent =
    ".sub-nudge{position:fixed;left:0;top:38%;z-index:1300;width:300px;max-width:calc(100vw - 28px);" +
    "background:var(--surface,#fff);border:1px solid var(--line,#e4e4e7);border-radius:0 14px 14px 0;" +
    "box-shadow:0 8px 30px rgba(0,0,0,.22);padding:26px 14px 13px;" +
    "transform:translateX(-115%);transition:transform .45s cubic-bezier(.22,1,.36,1)}" +
    ".sub-nudge.in{transform:translateX(0)}" +
    ".sub-nudge.blink{animation:subBlink .55s ease 1}" +
    "@keyframes subBlink{0%,100%{box-shadow:0 8px 30px rgba(0,0,0,.22)}" +
    "50%{box-shadow:0 0 0 3px var(--teal,#12a594),0 8px 30px rgba(0,0,0,.22)}}" +
    ".sub-nudge-x{position:absolute;top:5px;right:8px;background:none;border:none;color:var(--ink-dim,#8a8a8a);" +
    "font-size:19px;line-height:1;cursor:pointer;padding:2px 5px}" +
    ".sub-nudge-x:hover{color:var(--ink,#111)}" +
    ".sub-nudge-t{color:var(--ink,#111);font-size:14.5px;font-weight:800;line-height:1.25;font-family:var(--disp,inherit)}" +
    ".sub-nudge-b{color:var(--ink-dim,#5a5a5a);font-size:12px;line-height:1.4;margin:6px 0 11px}" +
    ".sub-nudge-tg,.sub-nudge-ins{display:block;text-align:center;padding:9px 10px;border-radius:9px;" +
    "font-size:12.5px;font-weight:800;text-decoration:none;font-family:var(--disp,inherit)}" +
    ".sub-nudge-tg{background:var(--teal,#12a594);color:#fff!important}" +
    ".sub-nudge-tg:hover{filter:brightness(1.08)}" +
    ".sub-nudge-ins{margin-top:7px;background:transparent;color:var(--ink,#111)!important;border:1px solid var(--line,#d4d4d8)}" +
    ".sub-nudge-ins:hover{border-color:var(--teal,#12a594)}" +
    "@media(max-width:560px){.sub-nudge{left:10px;right:10px;top:10px;width:auto;border-radius:14px;" +
    "transform:translateY(-140%)}.sub-nudge.in{transform:translateY(0)}}";
  document.head.appendChild(css);

  var entry = (st === "dock") ? startDocked : arm;
  if (document.readyState !== "loading") entry();
  else document.addEventListener("DOMContentLoaded", entry);
})();
