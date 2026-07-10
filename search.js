// Внутренний поиск по сайту — статический индекс (data/search-index.json), без бэкенда.
// Две точки входа: оверлей (кнопка #searchOpenBtn / любой [data-search-open] / "/" или Ctrl+K)
// и инлайн-режим (контейнер #searchInlineMount — так встроен на 404.html). Обе используют
// один и тот же рендер результатов и одну и ту же клавиатурную навигацию.
(function () {
  "use strict";

  var INDEX_URL = "/data/search-index.json";
  var GROUP_ORDER = ["Города", "Статьи", "Удары", "НПЗ"];
  var MAX_PER_GROUP = 8;
  var MAX_TOTAL = 40;

  var indexPromise = null;
  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch(INDEX_URL)
        .then(function (r) { return r.json(); })
        .then(function (d) { return d.entries || []; })
        .catch(function () { return []; });
    }
    return indexPromise;
  }

  function norm(s) {
    return (s || "").toLowerCase().replace(/ё/g, "е");
  }

  // ponytail: fuzzy = "каждое слово запроса — подстрока где-то в тексте записи", не Левенштейн —
  // индекс маленький (~150 записей), полнотекстовый движок не нужен.
  function search(entries, query) {
    var tokens = norm(query).trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    var out = [];
    for (var i = 0; i < entries.length && out.length < MAX_TOTAL; i++) {
      var e = entries[i];
      var hay = e.text || norm(e.title);
      var ok = true;
      for (var t = 0; t < tokens.length; t++) {
        if (hay.indexOf(tokens[t]) === -1) { ok = false; break; }
      }
      if (ok) out.push(e);
    }
    return out;
  }

  function groupResults(list) {
    var byGroup = {};
    list.forEach(function (e) { (byGroup[e.group] = byGroup[e.group] || []).push(e); });
    return GROUP_ORDER.filter(function (g) { return byGroup[g] && byGroup[g].length; })
      .map(function (g) { return { group: g, items: byGroup[g].slice(0, MAX_PER_GROUP) }; });
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ---- общий рендер результатов + клавиатурная навигация ----
  function ResultsController(resultsEl) {
    this.el = resultsEl;
    this.flat = []; // плоский список видимых <a> для ↑↓
    this.active = -1;
  }

  ResultsController.prototype.render = function (groups, emptyMsg) {
    this.flat = [];
    this.active = -1;
    if (!groups.length) {
      this.el.innerHTML = emptyMsg ? '<div class="search-empty">' + escapeHtml(emptyMsg) + "</div>" : "";
      return;
    }
    var html = "";
    groups.forEach(function (g) {
      html += '<div class="search-group-h">' + escapeHtml(g.group) + "</div>";
      g.items.forEach(function (item) {
        html += '<a class="search-item" href="' + escapeHtml(item.url) + '">' +
          '<span class="search-item-title">' + escapeHtml(item.title) + "</span>" +
          '<span class="search-item-url">' + escapeHtml(item.url) + "</span></a>";
      });
    });
    this.el.innerHTML = html;
    this.flat = Array.prototype.slice.call(this.el.querySelectorAll(".search-item"));
  };

  ResultsController.prototype.move = function (delta) {
    if (!this.flat.length) return;
    if (this.active >= 0) this.flat[this.active].classList.remove("active");
    this.active = (this.active + delta + this.flat.length) % this.flat.length;
    var el = this.flat[this.active];
    el.classList.add("active");
    el.scrollIntoView({ block: "nearest" });
  };

  ResultsController.prototype.go = function () {
    var el = this.active >= 0 ? this.flat[this.active] : this.flat[0];
    if (el) location.href = el.getAttribute("href");
  };

  function wireInput(inputEl, controller, entriesPromise) {
    var lastQuery = "";
    inputEl.addEventListener("input", function () {
      var q = inputEl.value;
      if (q === lastQuery) return;
      lastQuery = q;
      entriesPromise.then(function (entries) {
        if (!q.trim()) { controller.render([], ""); return; }
        var hits = search(entries, q);
        controller.render(groupResults(hits), hits.length ? "" : "Ничего не найдено");
      });
    });
    inputEl.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); controller.move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); controller.move(-1); }
      else if (e.key === "Enter") { e.preventDefault(); controller.go(); }
    });
  }

  // ---- оверлей (страницы с шапкой) ----
  var overlay, overlayInput, overlayController, overlayOpener;

  function buildOverlay() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.className = "search-overlay";
    overlay.id = "searchOverlay";
    overlay.hidden = true;
    overlay.innerHTML =
      '<div class="search-overlay-scrim" data-search-close></div>' +
      '<div class="search-overlay-inner" role="dialog" aria-modal="true" aria-label="Поиск по сайту">' +
      '  <div class="search-box">' +
      '    <span class="search-ico">🔍</span>' +
      '    <input type="text" id="searchInput" class="search-input" placeholder="Город, НПЗ, статья…" autocomplete="off" aria-label="Поиск по сайту">' +
      '    <button type="button" class="search-close" data-search-close aria-label="Закрыть поиск">✕</button>' +
      "  </div>" +
      '  <div class="search-results" id="searchResults"></div>' +
      '  <div class="search-hint">↑↓ выбрать · Enter открыть · Esc закрыть</div>' +
      "</div>";
    document.body.appendChild(overlay);
    overlayInput = overlay.querySelector("#searchInput");
    overlayController = new ResultsController(overlay.querySelector("#searchResults"));
    wireInput(overlayInput, overlayController, loadIndex());
    overlay.querySelectorAll("[data-search-close]").forEach(function (el) {
      el.addEventListener("click", closeOverlay);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !overlay.hidden) closeOverlay();
    });
  }

  function openOverlay(opener) {
    buildOverlay();
    overlayOpener = opener || null;
    overlay.hidden = false;
    document.body.classList.add("search-lock");
    overlayInput.value = "";
    overlayController.render([], "");
    setTimeout(function () { overlayInput.focus(); }, 0);
  }

  function closeOverlay() {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.classList.remove("search-lock");
    if (overlayOpener && overlayOpener.focus) overlayOpener.focus();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("#searchOpenBtn, [data-search-open]");
    if (btn) { e.preventDefault(); openOverlay(btn); }
  });

  // "/" и Ctrl+K/Cmd+K открывают поиск из любого места сайта (когда фокус не в поле ввода)
  document.addEventListener("keydown", function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    var typing = tag === "INPUT" || tag === "TEXTAREA" || document.activeElement.isContentEditable;
    if ((e.key === "/" && !typing) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")) {
      e.preventDefault();
      openOverlay(null);
    }
  });

  // ---- инлайн-режим (404.html) ----
  function mountInline() {
    var mount = document.getElementById("searchInlineMount");
    if (!mount) return;
    mount.innerHTML =
      '<div class="search-box search-box-inline">' +
      '  <span class="search-ico">🔍</span>' +
      '  <input type="text" id="searchInlineInput" class="search-input" placeholder="Город, НПЗ, статья…" autocomplete="off" aria-label="Поиск по сайту">' +
      "</div>" +
      '<div class="search-results search-results-inline" id="searchInlineResults"></div>';
    var input = mount.querySelector("#searchInlineInput");
    var controller = new ResultsController(mount.querySelector("#searchInlineResults"));
    wireInput(input, controller, loadIndex());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountInline);
  } else {
    mountInline();
  }
})();
