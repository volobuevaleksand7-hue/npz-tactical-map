// azs-lab.js — песочница скрытой страницы /karta-azs-lab (тест-копия /karta-azs).
// Здесь и ТОЛЬКО здесь живёт код новых фич «реальное наличие топлива»:
// краудсорс-виджет «Я тут», слой внешних отметок (спрос-драйв), guardrails по свежести.
// ТЗ: docs/agents/tz-fuel-availability-2026-07.md
// Прод-страница /karta-azs и общий app.js остаются нетронутыми, пока фича не доведена.
// ponytail: пока только видимая LAB-метка + маркер в консоли — фич ещё нет, наполняется по ТЗ.
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var b = document.createElement('div');
    b.textContent = '🧪 LAB — тест наличия топлива';
    b.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:99999;background:#d23a2e;' +
      'color:#fff;font:600 12px/1 system-ui,sans-serif;padding:6px 10px;border-radius:6px;' +
      'opacity:.9;pointer-events:none';
    document.body.appendChild(b);
  });
  console.info('[azs-lab] sandbox build active — фичи наличия топлива по ТЗ tz-fuel-availability');
})();
