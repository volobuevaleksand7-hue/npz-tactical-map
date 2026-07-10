# Единый генератор шапки (идея #1, полка A)

**Дата:** 2026-07-10 · **Статус:** утверждён к реализации

## Проблема
`build-nav.py` уже владеет nav + footer + drawer + dropdown-JS + cache-bust на всех
`news-nav`-лендингах (nav/footer-«треть аудита» закрыта ещё 2026-07-09). Остаётся
дублирование: обёртка `<header class="news-header">` + логотип копируются руками на
каждом лендинге. Итог — расхождение: 86 страниц ведут логотипом на `/news` («Все
сводки»), 4 (help/analytics/404) — на `/` («На карту»). Новая hand-страница требует
ручного копирования всей шапки.

## Решение (Scope: шапка+футер, head — линтом)

### A. build-nav владеет всем `<header class="news-header">`
- `LOGO_HTML` — канонический логотип: `href="/"`, `title="На карту"`, `⛽ ТОПЛИВНЫЙ ФРОНТ РФ`.
- `HEADER_RE = <header class="news-header">.*?</header>` (DOTALL).
- `build_header(rows, current)` = `<header>` + `news-header-inner` + `LOGO_HTML` + `build_nav(...)`.
- В `main()`: страница с `<header class="news-header">` → заменяем весь header (`HEADER_RE`),
  иначе (radar: `topbar`, нет news-header) → как сейчас, только внутренний nav (`NAV_RE`).
- **Намеренная правка поведения:** логотип на 86 страницах меняется `/news → /` (логотип =
  домой = карта; /news доступен пунктом «Сводки»). Убирает расхождение — цель #1.
- Новая hand-страница = пустой `<header class="news-header"></header>` → build-nav наполняет.

### B. Head-линт в check-ia.py (не блокирующий, warnings)
Для каждой live-лендинг-страницы проверять обязательные head-элементы: `canonical`,
`og:type/url/title/description/image`, `twitter:card`, `viewport-fit=cover`, `theme-color`,
`/fonts.css`, `/styles.css`. Ловит head-находки аудита (install/support без OG, нет
viewport-fit) без рискованной централизации head.

### C. Починить то, что линт вскроет
Доставить недостающие OG/viewport-fit на страницах, которые линт отметит.

## Не делаем (YAGNI)
Шаренный head-блок и хвостовые скрипты (theme-init/SW) — не централизуем (линт вместо
этого). radar/index беспоковые шапки не трогаем (только их внутренний nav, как сейчас).

## Blast-radius / риск
Ядро: `agents/build-nav.py` (+HEADER_RE/LOGO/build_header), `agents/check-ia.py` (+линт).
Механически ~90 лендингов при первом прогоне (шапки почти идентичны). Гейт:
index.html/radar.html/version.json/CHANGELOG.md. Риск низкий — regex-замена как у nav/footer.

## Проверка
`build-nav.py` + `check-ia.py` зелёные; браузер: лендинг/radar/index шапки целы, логотип
на месте, меню работает; страница с пустым `<header>`-маркером наполняется.
