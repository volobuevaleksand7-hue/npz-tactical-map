# ТЗ — 3 фичи одним воркфлоу (2026-07-10)

Из бэклога `docs/backlog-top10-ideas.md`: **#4 внутренний поиск**, **#2 «АЗС рядом»** (флагман),
+ **SEO-статья** под фичу «АЗС рядом». Разработка — 3 параллельными субагентами с
**непересекающимся владением файлами** (без worktree). Интеграция + браузер-верификация +
релиз — оркестратор (не субагенты; origin двигается, gate `ALLOW_FRONTEND_RELEASE=1`).

Работа в `~/Documents/npz-tactical-map`. Субагенты: **НЕ** `git commit`/`push`, **НЕ** трогают
чужие файлы. Тон статьи — нейтральный OSINT, даты в UI по-русски («10 июля 2026»).

## Владение файлами (гарантия отсутствия конфликтов записи)

| Агент | Пишет | НЕ трогает |
|---|---|---|
| **A · #4 поиск** | `search.js`, `search.css`, `agents/build-search-index.py`, `data/search-index.json` (ген), `404.html` | index.html, app.js, styles.css, build-nav.py |
| **B · #2 АЗС рядом** | `app.js` (лог. АЗС), `styles.css` (доп. блок), АЗС-view разметка в `index.html` **и** `karta-azs.html` | build-nav-регионы, 404, search-файлы |
| **C · #3 статья** | `agents/azs-pages.py` (новый entry `azs-ryadom`) | index.html, app.js, styles.css (build-nav НЕ гоняет — это делает оркестратор) |

index.html в build-фазе пишет только B (АЗС-view регион). C откладывает build-nav → нет гонки за header.

## A — #4 Внутренний поиск (статический JS)

- `agents/build-search-index.py` → `data/search-index.json`: записи из `data/seo-topics.jsonl`
  (title из primary_kw/labels, url, keywords, type), уникальные города ударов из `data/strikes.json`
  (→ ссылка на регион-страницу если есть, иначе на главную с фокусом), список НПЗ из `refineries.html`/`npz/`.
  Идемпотентно, без сети. Оставить runnable-selfcheck (`--check`: индекс непустой, все url начинаются с `/`).
- `search.js` + `search.css`: оверлей (🔍 в шапке открывает full-screen), инпут, живой substring/fuzzy-поиск
  по индексу, результаты сгруппированы (Города / Статьи / Удары / НПЗ), клавиатура (↑↓/Enter/Esc). Без бэкенда.
- `404.html`: встроить тот же поиск как точку входа (битые ссылки из соцсетей) + топ-5 разделов.
- **Вернуть оркестратору**: точные строки `<link>`/`<script>` для шелла и HTML кнопки 🔍 для шаблона `build-nav.py`.

## B — #2 «АЗС рядом» (флагман, в app.js)

Механизм уже есть: `renderAzsStations()` фильтрует по `azsState.brands`/`azsState.level`;
`stationLevel(st)` даёт уровень. Добавить:
- **📍 Рядом со мной**: кнопка в `#azsPanel` (блок «Карта поездки» или новый блок) → `navigator.geolocation`
  → центр карты на юзере + маркер «вы здесь» + zoom ~12 + ближайшие АЗС с расстоянием (км) в попапе.
  Ошибка/отказ геолокации — аккуратный тултип, не молчать.
- **⛽ Только где есть топливо**: тумблер → `azsState.hasFuelOnly` → в `renderAzsStations` отсекать
  `severe`/`critical`/`unknown` (оставить `calm`/`strained`/`limited`). Честный контраст с gdebenzin
  (тот фейкает статусы через Math.sin от OSM id) — подчеркнуть в подписи фильтра/попапе.
- Разметку продублировать в `index.html` **и** `karta-azs.html` (view `#view-azs` идентичен). CSS — доп. блок в конце `styles.css`.
- Мобайл-first (главный интент). Runnable-selfcheck логики фильтра, если вынести чистую функцию.

## C — #3 SEO-статья «АЗС рядом»

- Новый entry в `agents/azs-pages.py` (мясо — как `gde-est-benzin`; прочитать `agents/gen-fuel-pages.py`
  для схемы секций/FAQ). Slug **`azs-ryadom`**, type `tool`.
- primary_kw **«азс рядом со мной»**; кластер: заправки рядом со мной, ближайшая азс, где заправиться рядом,
  карта азс рядом. Не каннибализировать `/gde-est-benzin` и `/karta-azs` (кросс-ссылки, разный интент:
  тут — «найти ближайшую работающую заправку прямо сейчас через геолокацию»).
- Контент: есть такой честный бесплатный сервис (фича «Рядом со мной» + фильтр «есть топливо» на `/karta-azs`),
  чем отличается от фейковых карт статусов, как пользоваться, FAQ. CTA на `/karta-azs`.
- **НЕ** запускать `azs-pages.py`/build-nav (это делает оркестратор). Вернуть готовый entry + текст контента.

## Интеграция + релиз (оркестратор, последовательно)

1. A: добавить кнопку 🔍 в шаблон `build-nav.py` (→ на всех страницах) + include search.js/css в шелл; прогнать `build-search-index.py`.
2. C: `python3 agents/azs-pages.py azs-ryadom --dry-run` (ген страницы + реестр + sitemap + nav).
3. `build-nav.py` + `check-ia.py` — целостность IA.
4. Браузер-верификация (preview `npz-verify`, порт 8811): поиск-оверлей, АЗС геолокация+фильтр, новая статья + пункт в меню.
5. Релиз: `version.json` + `CHANGELOG.md` + SW-bump (`?v=` хэши + `sw.js`), `ALLOW_FRONTEND_RELEASE=1`,
   `git rebase origin/main`, push (`GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue) git -c credential.helper= -c credential.helper='!gh auth git-credential' push origin main`; `gh auth switch` не использовать).
6. Верификация прода.
