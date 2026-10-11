# /lab/world — спецификация данных и агентов (v0.1, закрытая лаборатория)

Страница: `lab/world.html` → `/lab/world` (noindex, нет в меню/sitemap). Данные: `data/world/*.json`,
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
История: до 5 лет для расчёта процентилей. Ошибка источника → `error` строкой, прежние значения
сохраняются, `stale:true` если `as_of` старше 2× частоты.

## data/world/index.json (пишет agents/world/index.py, детерминированно)
```json
{"generated_at":"ISO","methodology_version":"0.1",
 "world":{"value":63,"level":"crisis","delta_1d":4,"coverage":0.8},
 "regions":{"<id>":{"name":"Европа","value":56|null,"level":"…","delta_1d":3,"coverage":0.7,
   "components":[{"id":"chokepoints","label":"…","score":0-100,"weight":0.25,"raw":"…","as_of":"…","source":"…"}]}}}
```
Уровни: 0–24 calm «спокойно», 25–49 tense «напряжённо», 50–74 crisis «кризис», 75–100 critical «критично».
Компоненты и базовые веса: chokepoints 25, phys_premium 20 (пока нет бесплатного фьючерса — компонент
отсутствует, не подменять), prices 15, diesel_crack 10, retail 10, stocks 10, shortage_news 5, georisk 5.
Нормировка: процентиль к истории (цены 3 года, прочее 5 лет), «падение трафика» — 7-дн. среднее к медиане 365 дн.
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
