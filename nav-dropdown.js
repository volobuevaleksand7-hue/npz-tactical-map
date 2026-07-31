// Выпадашка «Аналитика» на лендингах: на десктопе (реальная мышь, hover работает) клик по
// «📊 Аналитика ▾» ведёт на /analytics — меню и так раскрывается по наведению (CSS :hover
// на .nav-dropdown, см. news.css). На тач-устройствах hover ненадёжен (особенно планшеты
// в ландшафте >768px, меню было не открыть) — там клик закрепляет меню (класс .open), а
// /analytics всё равно достижим пунктом «Все статьи · каталог →» внутри меню. Закрытие —
// клик-вне / Esc. Единый источник правды: build-nav.py линкует этот файл во все лендинги,
// чтобы инлайн-JS не дрейфовал по 30+ страницам (раньше — 4 разных копии + сводки без JS вовсе).
// Зеркалит поведение главной карты (index.html, .tab-dropdown.open).
(function () {
  var hoverCapable = function () {
    return !!(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches);
  };
  document.querySelectorAll('.nav-dropdown > a').forEach(function (a) {
    a.addEventListener('click', function (e) {
      if (hoverCapable()) return; // десктоп: не мешаем клику уйти на /analytics
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
