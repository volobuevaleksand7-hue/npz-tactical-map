# /world — спецификация данных и агентов (методика v0.2; страница открыта 13.10.2026)

Страница: `world.html` → `/world` (публичная, в меню главной и sitemap; старый `/lab/world` → 301). Данные: `data/world/*.json`,
страница читает их с RAW GitHub (как app.js), локально — относительным путём.

## Регионы (id → состав по ISO3, Natural Earth `ISO_A3`)
- `europe` — ЕС-27 + NOR, GBR, CHE, ISL, балканы (SRB, BIH, MNE, MKD, ALB, XKX), UKR, MDA, BLR
- `russia_cis` — RUS, KAZ, UZB, TKM, KGZ, TJK, AZE, ARM, GEO
- `middle_east` — SAU, IRN, IRQ, KWT, ARE, QAT, BHR, OMN, YEM, ISR, PSE, JOR, LBN, SYR, TUR, EGY
- `east_asia` — CHN, JPN, KOR, PRK, TWN, MNG + ЮВА (VNM, THA, MYS, SGP, IDN, PHL, MMR, KHM, LAO, BRN, TLS) + AUS, NZL
- `south_asia` — IND, PAK, BGD, LKA, NPL, BTN, AFG, MDV
- `north_america` — USA, CAN, MEX
- `latin_america` — остальная Америка
- `africa` — остальная Африка (кроме EGY)

## Узкие места (PortWatch `portname`)
hormuz «Strait of Hormuz» → middle_east, south_asia, east_asia
bab_el_mandeb «Bab el-Mandeb Strait» → europe, middle_east
suez «Suez Canal» → europe
malacca «Malacca Strait» → east_asia
bosporus «Bosporus Strait» → europe, russia_cis
cape «Cape of Good Hope» → africa (рост трафика = обход, сигнал)

## data/world/series.json (пишет agents/world/collect.py, без LLM)
```json
{"generated_at":"ISO","series":{"<id>":{"label":"…","unit":"…","source":"FRED","url":"…","license":"…",
 "freq":"daily|weekly|monthly","as_of":"YYYY-MM-DD","value":0.0,"stale":false,"error":null,
 "history":[["YYYY-MM-DD",0.0], ...]}}}
```
id: `brent_spot` (FRED DCOILBRENTEU), `wti_spot`, `ulsd_nyh` (DDFUELNYH), `gasoline_nyh` (DGASNYH),
`diesel_retail_us` (GASDESW), `us_crude_stocks`, `us_distillate_stocks` (EIA WPSR xls),
`eu_diesel_retail`, `eu_gasoline_retail` (EU Oil Bulletin, среднее ЕС с налогами, €/1000 л),
`gpr_daily` (Caldara-Iacoviello), `gdelt_shortage_<region>` (доля статей «fuel shortage»),
`chokepoint_<id>_tankers` (PortWatch n_tanker), `iea_stocks_days_<europe|pacific|north_america>`.
История: до 5 лет для расчёта процентилей; цены и крэк (brent_spot, wti_spot, ulsd_nyh, gasoline_nyh) — 10 лет (FRED `cosd` = 10,2 года назад), причём точки старше года хранятся недельными средними (метка — понедельник), свежий год — дневной, файл ≈250 КБ. Ошибка источника → `error` строкой, прежние значения
сохраняются, `stale:true` если `as_of` старше 2× частоты.

## data/world/index.json (пишет agents/world/index.py, детерминированно)
```json
{"generated_at":"ISO","methodology_version":"0.2",
 "brand":{"short":"ИТН","short_en":"FTI","ru":"Индекс топливной напряжённости","en":"Fuel Tension Index"},
 "world":{"value":63,"level":"crisis","delta_1d":4,"coverage":0.8},
 "regions":{"<id>":{"name":"Европа","value":56|null,"level":"…","delta_1d":3,"coverage":0.7,
   "components":[{"id":"chokepoints","label":"…","score":0-100,"weight":0.25,"raw":"…","as_of":"…","source":"…"}]}}}
```
Уровни: 0–24 calm «спокойно», 25–49 tense «напряжённо», 50–74 crisis «кризис», 75–100 critical «критично».
Компоненты и веса (v0.2): chokepoints 30, shortage_news 15, retail 15, stocks 15, prices 10, diesel_crack 5,
georisk 5, phys_premium 5 (пока нет бесплатного фьючерса — компонент отсутствует, не подменять; вес остаётся в знаменателе coverage). Сумма = 100.
Нормировка: цены и крэк — процентиль к 10 годам (недельная часть истории весит ×5, чтобы календарное время учитывалось поровну),
GPR, розница, запасы — процентиль к 5 годам, новости — процентиль к собственной истории.
Проливы (линейная шкала, не процентиль): отклонение 7-дн. среднего танкеров от медианы года; падение 0% → 0 баллов,
падение на 80% и глубже → 100 (то есть пустой пролив = 100); для Мыса Доброй Надежды рост на 50% → 100.
Балл региона по проливам = худший из его проливов (max), а не среднее.
**Пропуск компонента не перераспределяет вес**: value = Σ(score·w)/Σ(w доступных), а `coverage` = Σw доступных;
coverage < 0.5 → `value:null` («мало данных»). Мировой = среднее регионов с весами импорта (константы в index.py).

## data/world/index-history.json
`[{"date":"YYYY-MM-DD","world":63,"regions":{"europe":56,…}}]` — одна запись в сутки, перезапись за текущий день.

## data/world/events.json — опубликованные карточки
Схема как в seed (id, occurred_at, type, region, status confirmed|reported, title, summary, fuel_effect,
lat, lon, precision point|zone, radius_km, photo{url,page,license,author}|null, sources[]) + `review`
(`approved` — владелец; `lab` — видно только в лаборатории) + `index_effect` (текст, напр. «Ближний Восток: компонент проливов ↑»).

## data/world/events-queue.json — кандидаты от агента (не публикуются)
Схема как у events.json, плюс `found_at`, `agent`, `checks{schema,urls_alive,neutral_lexicon,two_independent_sources}`,
`verdict` (`ready|needs_source|rejected`), `reject_reason`. Кандидат без URL отбрасывается сразу.

## Агентская система (VPS hermes, через общий лок и git-sync.sh)

| Роль | Кто | Когда | Пишет | LLM |
|---|---|---|---|---|
| 1. Сборщик рядов | `agents/world/collect.py` | каждые 6 ч (:35) | series.json | нет |
| 2. Расчёт индекса | `agents/world/index.py` | сразу после сборщика | index.json, index-history.json | нет |
| 3. Разведчик событий | Haiku 5.5 по `agents/world/prompt-events.md` (GDELT + WebSearch) | 3 раза в сутки | events-queue.json | да, только черновик |
| 4. Валидатор | `agents/world/validate-events.py` | после разведчика | поле `checks/verdict` в очереди | нет |
| 5. Редактор | владелец: `ready`-кандидаты уходят в Telegram (`agents/tg-send`) с кнопками-командами; «да» → `agents/world/approve.py <id>` | 1–2 раза в день | events.json | нет |
| 6. Сторож | `agents/world/watch.py` (встроить в существующий watchdog) | каждый час | incidents.md + один алерт | нет |

Правила:
- Публикуется только то, что прошло валидатор И одобрено владельцем. Агент не может писать в events.json.
- Удары/захваты/атаки на суда: `confirmed` только при двух независимых издателях (не перепечатка одного Reuters/UKMTO).
- Лексика — тот же словарь, что `sanitize-strikes.py`; украинский язык и лозунги — reject.
- Индекс считает только скрипт; события на балл не влияют (только текст `index_effect`, подтверждённый сменой ряда).
- Ряд устарел (2× частоты) → сторож пишет инцидент, компонент выпадает, падает `coverage`; < 0.5 → «мало данных».
- Внедрение cron — только после «да» Сергея; до этого прогон вручную на Маке.

## Что изменилось в 0.2 и почему
v0.1 вышел сжатым кверху (мир 87, регионы 76–94, всё «критично»): Brent ($125) и ULSD стояли на p98–99 за 3 года и одинаково
задирали все регионы, а проливы по процентилю дельты почти не различали Ормуз (0,9 танкера при медиане 3) и Малакку.
1. Окно цен 3 → 10 лет: 2022 год служит ориентиром.
2. Общие для всех регионов компоненты (prices, diesel_crack, georisk) — 20% вместо 30%; вес региональных (проливы, розница, запасы, новости) вырос.
3. Проливы: процентиль → линейная шкала, регион берёт худший пролив. Ближний Восток/Южная и Восточная Азия ≈89 (Ормуз), Европа ≈53, Африка ≈8.
4. В index.json появилось поле `brand` (одна константа BRAND в index.py). Имя утверждено 13.10.2026: «Индекс топливной напряжённости» (ИТН) / Fuel Tension Index (FTI).
Известные слабости: у регионов без розницы/запасов/проливов (Латинская Америка, Африка) значение держится на общих компонентах
(и Латинская Америка остаётся «мало данных», coverage 0,35); запасы IEA без сезонной поправки; GDELT-процентиль по 71 дню шумит.
