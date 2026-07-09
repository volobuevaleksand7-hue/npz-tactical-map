// Выпадашка «Аналитика» на лендингах: клик закрепляет меню (класс .open) на ВСЕХ вьюпортах —
// :hover ненадёжен на тач-планшетах в ландшафте (>768px), меню было не открыть. Закрытие —
// клик-вне / Esc. Единый источник правды: build-nav.py линкует этот файл во все лендинги,
// чтобы инлайн-JS не дрейфовал по 30+ страницам (раньше — 4 разных копии + сводки без JS вовсе).
// Зеркалит поведение главной карты (index.html, .tab-dropdown.open).
(function () {
  // preventDefault на всех вьюпортах: клик по «📊 Аналитика ▾» открывает меню, а не уводит
  // на /analytics — каталог достижим пунктом «Все статьи · каталог →» внутри меню.
  document.querySelectorAll('.nav-dropdown > a').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      this.parentElement.classList.toggle('open');
    });
  });
  var closeDrops = function () {
    document.querySelectorAll('.nav-dropdown.open').forEach(function (d) { d.classList.remove('open'); });
  };
  document.addEventListener('click', function (e) { if (!e.target.closest('.nav-dropdown')) closeDrops(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeDrops(); });
})();
