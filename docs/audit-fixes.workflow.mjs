export const meta = {
  name: 'npz-audit-fixes',
  description: 'Применить фиксы аудита npz-tactical-map (SEO, навигация, мобайл, desktop) + верификация',
  whenToUse: 'После аудита дизайна/SEO — прогнать приоритетные исправления по репозиторию и проверить их вживую',
  phases: [
    { title: 'SEO-чистка',   detail: 'sitemap-мусор, /seo/ закрыть, дубль moskovskij, кастомная 404' },
    { title: 'Навигация',    detail: 'единое меню/футер через build-nav.py, news в scope, radar nav, перелинковка' },
    { title: 'Мобайл',       detail: 'radar/крым/азс панели, хит-зоны маркеров, talony overflow, шрифт, viewport-fit' },
    { title: 'Desktop/меты', detail: 'шапка index, h1/OG на install/support/sources, alt-тексты' },
    { title: 'Верификация',  detail: 'локальный сервер + playwright: overflow, свёрнутость панелей, 404, sitemap' },
  ],
}

// ─────────────────────────────────────────────────────────────────────────────
// ВАЖНО перед запуском (не забыть — иначе работа потеряется/не закоммитится):
//  1) git-sync делает hard-reset дерева на origin и сносит незакоммиченные правки
//     (см. memory npz-git-sync-hard-reset-hazard). На время прогона поставь фоновый
//     sync на паузу ИЛИ дай фазе коммита отработать сразу.
//  2) Коммит index.html/styles.css требует ALLOW_FRONTEND_RELEASE=1 (frontend-gate).
//     Мобайл/desktop-фазы правят styles.css → коммит этих фаз идёт под гейтом.
//  3) Фазы идут ПОСЛЕДОВАТЕЛЬНО (await между ними) намеренно: они делят общие файлы
//     (sitemap.xml, styles.css, app.js, radar.html) — параллель = конфликт правок.
//     Параллелим только независимые проверки в фазе верификации.
//  4) Запуск: Workflow({ scriptPath: 'docs/audit-fixes.workflow.mjs' }) из репо
//     ~/Documents/npz-tactical-map. Ничего не деплоит — деплой (vercel --prod) руками
//     после ревью диффа.
// ─────────────────────────────────────────────────────────────────────────────

const REPO = '/Users/sergeyrama/Documents/npz-tactical-map'

const FIX_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['done', 'skipped', 'files_touched', 'notes'],
  properties: {
    done:          { type: 'array', items: { type: 'string' }, description: 'Что реально сделано, по пунктам' },
    skipped:       { type: 'array', items: { type: 'string' }, description: 'Что не тронуто и почему' },
    files_touched: { type: 'array', items: { type: 'string' }, description: 'Изменённые/созданные/удалённые файлы' },
    notes:         { type: 'string', description: 'Риски, ручные шаги, что проверить глазами' },
  },
}

const CHECK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['check', 'pass', 'detail'],
  properties: {
    check:  { type: 'string' },
    pass:   { type: 'boolean' },
    detail: { type: 'string', description: 'Замеры/наблюдения; при провале — конкретно что не так' },
  },
}

const common = `Репозиторий: ${REPO} (статический сайт, чистые HTML/CSS/JS, без сборки).
Меню генерится из data/seo-topics.jsonl через agents/build-nav.py; проверяльщик agents/check-ia.py.
Правь минимально и по месту, стиль соседнего кода не ломай. НИЧЕГО не коммить и не деплоить —
это делает оператор после ревью. Верни отчёт строго по схеме.`

// ── Фаза 1. SEO-чистка ───────────────────────────────────────────────────────
phase('SEO-чистка')
const seo = await agent(`${common}

Задачи (файл:строка из аудита):
1) Удалить чужой контент под доменом: файлы exilenova.html и radarrusiia.html (сырые снепшоты Telegram-виджетов, чужие title/canonical, укр. текст). Убрать их <loc> из sitemap.xml (строки ~447 и ~538).
2) Разрулить дубль: moskovskij-npz.html в корне побайтово равен npz/moskovskij-npz.html и сам канонизируется на /npz/moskovskij-npz, но всё ещё в sitemap.xml (~496). Убрать корневой <loc> из sitemap И добавить 301-редирект в vercel.json: { "source": "/moskovskij-npz", "destination": "/npz/moskovskij-npz", "permanent": true }. Корневой файл можно удалить (редирект перекроет).
3) Закрыть внутреннюю SEO-разведку от публикации: добавить строку "seo/" в .vercelignore (сейчас там есть docs/, hermes/, dashboard/, но не seo/ — semantic-core.json и wordstat-выгрузки отдают HTTP 200 на проде).
4) Кастомная 404: Vercel сейчас отдаёт голую заглушку. Создать 404.html (или настроить в vercel.json) в стиле сайта — шапка/лого, ссылка на карту (/) и радар (/radar), короткий блок «раздела нет — вот главное». Использовать существующие styles.css-классы, не изобретать дизайн.
5) Обратный проход в agents/check-ia.py: добавить проверку «каждый <loc> из sitemap.xml есть либо в TOP_URLS, либо в реестре seo-topics.jsonl» → warning на осиротевшие/мусорные URL (чтобы п.1–2 больше не всплывали).`,
  { label: 'fix:seo', phase: 'SEO-чистка', schema: FIX_SCHEMA, agentType: 'general-purpose' })
log(`SEO-чистка: ${(seo?.done || []).length} пунктов, файлов: ${(seo?.files_touched || []).length}`)

// ── Фаза 2. Навигация и перелинковка ─────────────────────────────────────────
phase('Навигация')
const nav = await agent(`${common}

Проблема: на сайте ТРИ разные реализации меню + разнобой футеров; новостной раздел (news.html + 56 news/*.html) отрезан от /radar и /analytics.

Задачи:
1) Включить news/*.html в scope генератора: agents/build-nav.py сейчас берёт только ROOT.glob("*.html") + npz/*.html. Расширить, чтобы news.html и news/ГГГГ-ММ-ДД.html получали в шапку пункты «Радар БПЛА» и «Аналитика» (сейчас в news-nav только 4 пункта — Сводки/Карта НПЗ/Карта АЗС/Источники). Регенерировать затронутые страницы скриптом, не руками.
2) radar.html: у него класс nav (не news-nav), поэтому NAV_RE в build-nav.py его не матчит и «Аналитика» там — простая ссылка на хаб вместо группового дропдауна. Привести к единому меню (либо расширить regex, либо унифицировать класс). Радар — самая посещаемая страница, до лендинга должен быть 1 клик.
3) Перелинковка сводок: в шаблон news/ГГГГ-ММ-ДД.html (блок brief-nav, ~строки 277-281) добавить 2-3 контекстные ссылки на тематические статьи (/deficit, /attacks, /talony, /crisis) — сейчас сводки линкуются только prev/next и никогда на лендинги.
4) Футер: на сайте 4 разных футера (ticker / news-footer / голый div / нет вовсе). Свести SEO-лендинги и analytics к единому брендированному news-footer со ссылкой на карту и брендингом. Генерировать из build-nav.py, а не руками.
5) Чип «Свежее» на index (FRESH:START, build-nav.py ~171 newest_page()) сейчас указывает на последнюю запись реестра без фильтра и уводит на /help (type=reference). Фильтровать по типам {region, explainer, forecast, tool}, исключая reference.

После правок ОБЯЗАТЕЛЬНО прогнать agents/build-nav.py и agents/check-ia.py, приложить их вывод в notes.`,
  { label: 'fix:nav', phase: 'Навигация', schema: FIX_SCHEMA, agentType: 'general-purpose' })
log(`Навигация: ${(nav?.done || []).length} пунктов`)

// ── Фаза 3. Мобайл ───────────────────────────────────────────────────────────
phase('Мобайл')
const mob = await agent(`${common}

50% трафика — мобильные, это приоритет. Все фиксы копируют уже работающий на табе «Россия» паттерн (app.js:291 стартует со свёрнутой шторкой) — новая архитектура НЕ нужна.

Задачи (файл:строка):
1) 🔴 radar.html:439 — панель .panel открыта по умолчанию (aria-expanded="true", .collapsed не навешивается). На 375px карты видно ~39%. При innerWidth<=768 сразу добавлять .panel.collapsed на старте, как в app.js:291.
2) 🔴 app.js:996 initPanelExpand() — панели табов «Крым» (#crimeaPanel) и «АЗС» (#azsPanel, #azsCommentsCard) вообще не сворачиваются на мобиле (в списке только panelLeft/panelFeed/panelVoices). Завести тот же collapse-toggle/FAB для Крым и АЗС; на табе АЗС сейчас до 74% экрана перманентно закрыто.
3) 🔴 app.js:1287 — маркеры АЗС iconSize:[18,18], хит-зона в 2.4× меньше 44px. Увеличить прозрачным паддингом хит-area до ~36px, ВИЗУАЛ точки не менять.
4) 🟡 talony.html:150 — таблица .talon-table без обёртки даёт горизонтальный overflow +68px на 375px (единственная на сайте). Обернуть в контейнер с overflow-x:auto (как ftable/refinery-table).
5) 🟡 news.css:196,246 — тело сводок/аналитики 13px. Поднять .strike-detail и .balance-notes до 14-15px.
6) 🟡 Утилитарные кнопки < 44px: styles.css:799 (nav-burger 40×40), :95 (theme 34×30), :106,109 (install/donate иконки ~30). Поднять высоту до 40-44px. На radar.html:570 leaflet zoomControl ~30px — CSS override .leaflet-control-zoom a{width/height} или свой контрол.
7) 🟡 Добавить viewport-fit=cover на radar.html:6, news.html:5, deficit.html:5 (на index уже есть) — иначе шапки не красятся под чёлку.
8) 🔴 Мобильная главная карта: центр не адаптирован под узкий viewport — кластеры ударов уезжают за левый край (в кадре Казахстан). Подобрать center/zoom (или fitBounds по маркерам РФ) при innerWidth<=768, чтобы европейская часть РФ была в кадре.

styles.css и app.js трогает и следующая desktop-фаза — эта фаза идёт раньше и завершается до неё, конфликта нет.`,
  { label: 'fix:mobile', phase: 'Мобайл', schema: FIX_SCHEMA, agentType: 'general-purpose' })
log(`Мобайл: ${(mob?.done || []).length} пунктов`)

// ── Фаза 4. Desktop и меты ───────────────────────────────────────────────────
phase('Desktop/меты')
const desk = await agent(`${common}

Задачи:
1) 🔴 Шапка index.html на 1440px: вкладка «РОССИЯ» наезжает на логотип, справа теснятся 11+ элементов. Дать логотипу нresearченный отступ / прижать группу вкладок, при нехватке места — увести часть в дропдаун. Проверить, что на 1280-1440px ничего не наезжает.
2) 🟡 install.html — нет <h1> вообще (заголовок сделан div.ins-h ~строка 47): заменить на <h1 class="ins-h">. Достроить OG/Twitter-теги на install.html и support.html (сейчас отсутствуют og:type/url/title/description/image, twitter:card) и og:image на sources.html — по образцу help.html/talony.html, og-image.png уже есть.
3) 🟢 alt-тексты: analytics.html строки ~142,151,160,177,186,211,220,229,246,255 — 10 картинок analytics-*-generated.png с alt="" — заполнить осмысленным alt. Точечные img без alt на index/radar/help/sources — проверить и дозаполнить.
4) 🟢 Косметика сводок: заголовок дня иногда не согласован с обложкой (обложка «Тверь», заголовок «Удар по терминалу в Батайск») и падеж («в Батайске»). Проверить генератор заголовков сводки — если это шаблон, отметить в notes, руками единичные не правь.`,
  { label: 'fix:desktop', phase: 'Desktop/меты', schema: FIX_SCHEMA, agentType: 'general-purpose' })
log(`Desktop/меты: ${(desk?.done || []).length} пунктов`)

// ── Фаза 5. Верификация (независимые проверки — параллельно) ──────────────────
phase('Верификация')
const verifyPrompt = (check, how) => `${common}

Проверка вживую после фиксов. Подними локальный сервер из ${REPO}
(python3 -m http.server 8099 в фоне) и проверь: ${how}
Верни строго по схеме: check="${check}", pass=true/false, detail с замерами. Сервер по завершении погаси.`

const checks = await parallel([
  () => agent(verifyPrompt('mobile-overflow',
    `playwright (уже есть в ~/Library/Caches/ms-playwright) на viewport 375×812 открой /talony, /radar, /news, /deficit, /moskva; для каждой замерь document.documentElement.scrollWidth - clientWidth. PASS если ≤2px везде (особенно talony, где было +68).`),
    { label: 'verify:overflow', phase: 'Верификация', schema: CHECK_SCHEMA, agentType: 'general-purpose' }),

  () => agent(verifyPrompt('radar-panel-collapsed',
    `playwright 375×812, открой /radar, дождись карты. Проверь, что .panel имеет класс collapsed на старте и карта видна ≥60% высоты. Сделай скриншот в scratchpad. PASS если панель свёрнута по умолчанию.`),
    { label: 'verify:radar', phase: 'Верификация', schema: CHECK_SCHEMA, agentType: 'general-purpose' }),

  () => agent(verifyPrompt('news-links-radar-analytics',
    `grep по news.html и одной news/ГГГГ-ММ-ДД.html: есть ли ссылки href на /radar и /analytics. PASS если обе присутствуют в шапке новостного шаблона.`),
    { label: 'verify:nav', phase: 'Верификация', schema: CHECK_SCHEMA, agentType: 'general-purpose' }),

  () => agent(verifyPrompt('sitemap-clean',
    `Проверь sitemap.xml: НЕТ <loc> с exilenova, radarrusiia и корневым /moskovskij-npz. Проверь, что "seo/" есть в .vercelignore, а 404.html существует. PASS если всё так.`),
    { label: 'verify:seo', phase: 'Верификация', schema: CHECK_SCHEMA, agentType: 'general-purpose' }),

  () => agent(verifyPrompt('touch-targets',
    `playwright 375×812 на /: проверь bounding-box высоты #navBurger, кнопки темы, install/donate — все ≥40px. И маркер АЗС на табе АЗС ≥36px хит-зоны. PASS если так.`),
    { label: 'verify:touch', phase: 'Верификация', schema: CHECK_SCHEMA, agentType: 'general-purpose' }),
]).then(r => r.filter(Boolean))

const failed = checks.filter(c => !c.pass)
log(`Верификация: ${checks.length - failed.length}/${checks.length} PASS`)

return {
  fixes: { seo, nav, mobile: mob, desktop: desk },
  verification: checks,
  failed: failed.map(c => `${c.check}: ${c.detail}`),
  next: failed.length
    ? 'Есть провалы верификации — разобрать перед деплоем.'
    : 'Все проверки прошли. Ревью диффа → git commit (ALLOW_FRONTEND_RELEASE=1 для styles.css/index.html) → vercel --prod --yes.',
}
