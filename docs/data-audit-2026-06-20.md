# Аудит данных и источников npz-tactical-map — 2026-06-20

Собран по запросу: что за данные, какие агенты их собирают, как; + разведка новых источников и улучшений (3 агента-разведчика).

---

## 1. ТЕКУЩАЯ КАРТИНА: данные → агент → метод

### Живые (4 облачные cloud-рутины, claude.ai RemoteTrigger, 24/7)

| Файл | Агент (cron UTC) | Метод сбора |
|---|---|---|
| `strikes.json` | **npz-data** `7 */6` | WebSearch рус+англ по городам + нефте-объектам |
| `fuel-state.json` (НПЗ/дефицит) | **npz-data** (npz+market) | WebSearch |
| `history-crimea.json` | **npz-data** (history) | WebSearch |
| `roads.json` | **npz-data** (roads) | WebSearch |
| `fuel-availability.json` | **fuel-availability** `23 */4` | WebSearch + СПбМТСБ + STALE-проход |
| `fuel-voices.json` | **fuel-voices** `41 */8` | Telegram t.me/s/ (5 каналов) + Я.Карты/drive2/drom |
| `grid-state.json` | **grid-status** `51 */6` | WebSearch |

### 🔴 Дыры
- `forecast.json` + `economy.json` — **НЕТ агента**, зависли на 2026-06-11 (9 дней). forecast-промпт есть, cron не назначен; economy не имел агента никогда.
- `azs-stations.json` — статичный (ручная регенерация из OSM + редеплой).
- Фронт показывает `lastSync` только из `fuel-state.meta.generated_at` → смерть любого другого агента невидима (так и умерли economy/forecast).
- Баннер «9 ИИ-агентов» = по факту 4 рутины.
- Источники почти всё на WebSearch; Telegram — 5 каналов; нет спутника/API/трекеров.

---

## 2. НОВЫЕ ИСТОЧНИКИ (проверены, бесплатно)

### 2A. Telegram-каналы (через t.me/s/ WebFetch, без авторизации)

**Удары + НПЗ + пожары:**
- `@exilenova_plus` — лучший единый: удары + НПЗ + пожары + **спутник/NASA FIRMS**. 178K, лаг минуты. 🔴
- `@radarrussiia` — реал-тайм гео-алерты ПВО по областям («опасность/отбой»). 🔴
- `@noel_reports` (англ кросс-чек), `@milinfolive` (прорус — баланс сланта).

**Топливо изнутри РФ:**
- `@nefte_baza`, `@oil_capital` — дефицит, лимиты АЗС, цены 95-го по регионам, загрузка НПЗ, ФАС. Нейтрал-отраслевые. 🔴

**Голоса людей (наш дефицитный тип):**
- `@Crimeanwind` — видео очередей/талонов/жалоб по Крыму. 🔴
- `@chp_krd`, `@RndCHP` — ЧП-очевидцы Кубань/Ростов.
- Flamp, 2ГИС, Otzovik — накопительные отзывы об АЗС вне Я.Карт/drive2/drom.

❌ Мёртвые: `@neftegram` (стух фев-2026), ВЧК-ОГПУ (снесён).

### 2B. Структурные трекеры (для сверки списка)
- **Caspian Policy Center — Live Map of Russian Refineries Hit** (24 НПЗ/61 удар, кликабельно).
- **Wikipedia «2025 Russian fuel crisis»** + страницы инцидентов — таймлайн со ссылками.
- **Reuters refinery-outage factboxes** — поимённый список НПЗ offline + мощность (млн т) + % РФ. 🔴 (через перепечатки Moscow Times/Militarnyi — бесплатно).
- **CREA monthly reports** (energyandcleanair.org) — экспорт нефтепродуктов/санкции, авторитетный нарратив.

---

## 3. СТРУКТУРНЫЕ ДАННЫЕ / API (бесплатные, для автоматизации)

### 🔴 Tier-1 (бесплатно, лёгкий API, максимальный эффект)
1. **NASA FIRMS Area API** — спутниковое детектирование пожаров → **автоподтверждение ударов по НПЗ**. CSV, ключ бесплатный (firms.modaps.eosdis.nasa.gov/api/map_key/), лимит 5000/10мин. Запрос: `api/area/csv/[KEY]/VIIRS_SNPP_NRT/[W,S,E,N]/[1-5дней]`. VIIRS 375м, NRT ~3ч после пролёта. **Киллер-фича.**
2. **GDELT DOC 2.0 API** — бесплатный автопоток событий «удар по НПЗ», **без ключа**, JSON, обновление 15 мин. `api.gdeltproject.org/api/v2/doc/doc?query=...&format=json`. `timelinevol` спайк = ранний сигнал.
3. **OSM / Overpass** — контуры НПЗ (`industrial=refinery`) для геофенсинга FIRMS-пожаров (fire-pixel внутри полигона = подтверждение). Бесплатно, без ключа.
4. **Global Energy Monitor GOIT** — трубопроводы/инфра, GIS-выгрузка, CC BY 4.0.
5. **Wikidata SPARQL / Wikipedia** — таблица НПЗ coords+мощность одним запросом (бесплатно).
6. **SPIMEX (СПбМТСБ) bulletins/indexes** — оптовые цены АИ-95/92/ДТ, бесплатный скрейп XLS/витрины (spimex.com/markets/oil_products/indexes/regional/).

### 🟡 Tier-2 (бесплатно, ручной/лимит — для качества)
7. Reuters factboxes (мощность offline). 8. ACLED (верифицированные удары, free-tier+ключ, лимиты). 9. CREA monthly (экспорт/выручка). 10. Росстат (розничные цены, XLS). 11. Bruegel Russian crude oil tracker (бесплатный датасет экспорта).

**Архитектура авто-верификации:** OSM-контуры (геофенс) → **FIRMS** (пожар-факт) → **GDELT** (новость-факт) → **ACLED** (верификация) = автоматический перекрёстно-подтверждаемый слой ударов почти без ручного труда и без платных подписок.

**Помечено ПРОВЕРИТЬ:** код страны РФ в GDELT (RS vs RU); прямые XLS SPIMEX (строгий TLS); refinery-слой в GEM; мощности в Wikidata; JSON-эндпоинты FIRMS; URL цен Росстата.

---

## 4. УЛУЧШЕНИЯ МЕТОДОЛОГИИ (по impact/effort)

| # | Улучшение | Impact | Усилие | Как |
|---|---|---|---|---|
| 1 | **Воскресить forecast.json + economy.json** 5-й рутиной | 🔴 выс | низ | новый промпт economy + 1 RemoteTrigger, cron 2×/нед, читает fuel-state |
| 2 | **Дедуп ударов** `дата+город` → `дата+город+цель+время` | 🔴 выс | низ | правка update-prompt-strikes.md |
| 3 | **Watchdog-страж** — следит за generated_at всех файлов, пинг в Telegram при тишине | 🔴 выс | сред | agents/healthcheck.py + рутина 3ч + @ramasclaude_bot |
| 4 | Поле `confidence` (confirmed/reported/rumored) + анти-bias (укр завышают / рос «всё отбито») | выс | сред | правка 4 промптов + бейдж во фронте |
| 5 | Кросс-верификация ≥2 источника → `sources[]` вместо `source_url` | выс | сред | правка промптов + фронт рендерит список |
| 6 | **Тепловая карта цен** — `ai95_price_rub` уже собирается, лежит в попапе | сред | низ (фронт) | choropleth-слой в app.js |
| 7 | Счётчик «дни простоя НПЗ» (`today - status_since`) + тренд «выбыло мощностей» | сред | низ | фронт + append capacity-timeline.json |
| 8 | Новые TG-каналы в промпты агентов (см. §2A) | выс | низ | правка strikes/npz/voices/availability промптов |
| 9 | STALE-проход для strikes/grid/roads (как у availability/voices) | сред | низ | абзац в 3 промпта |
| 10 | Слой экспортных нефтепортов (`export_terminals[]` в схеме есть, агент не трогает) | сред | низ | шаг в update-prompt-npz.md |

**Топ-3 к немедленному внедрению:** #1 (мёртвые слои), #2 (потеря ударов), #3 (невидимые сбои).

---

## 5. РЕКОМЕНДОВАННЫЙ ПОРЯДОК (фазы)
- **Фаза 1 (правки промптов, без новых систем, делается сразу):** #8 новые TG-каналы, #2 дедуп, #4 confidence+анти-bias, #9 STALE-проход, #10 порты.
- **Фаза 2 (новые рутины):** #1 forecast+economy, #3 watchdog.
- **Фаза 3 (фронт):** #6 тепловая карта цен, #7 дни простоя/тренд.
- **Фаза 4 (автоматизация-флагман):** FIRMS+GDELT+OSM авто-подтверждение ударов (новый скрипт-агент). Самый большой эффект, самый большой объём.

---
*Разведка: 3 агента (источники / структурные данные / методология). Gemini-агент не отработал — OAuth `<redacted-gmail>` для gemini CLI протух (Google отключил free-tier Code Assist); нужен GEMINI_API_KEY из AI Studio. Ветку структурных данных доделал general-purpose агент.*
