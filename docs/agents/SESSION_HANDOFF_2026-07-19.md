# Session Handoff — npz-tactical-map — 2026-07-19

## Status
Сессия 18-19.07 закрыла цепочку «волна дронов + публикация»: боевой автопаблиш включён, клоббер radar-state устранён, кандидаты в удары разобраны. Всё в проде. Осталось: W30-замер SEO (дата настала) и публикация /npz-lukojla (черновик готов).

## Read first
1. `docs/agents/SESSION_HANDOFF_2026-07-19.md` — этот файл
2. auto-memory (инжектится): npz-volna-dronov-detector, npz-stuck-strike-candidates, npz-growth-backlog, npz-articles-2026-07-17
3. `CLAUDE.md` репо — правила проекта
4. `docs/agents/tz-volna-close-2026-07.md` — ТЗ по волне (задачи 1-3 сделаны, задача 4 = автопаблиш включён)

## In-session decisions
- Боевой автопаблиш волн ВКЛЮЧЁН: export NPZ_WAVE_AUTOPUBLISH=1 в /root/.npz-agent.env на VPS. 🔴 нужен именно export (Python читает os.environ). Откат: убрать строку. Бэкап env рядом.
- Клоббер radar-state устранён: hermes-cron job 09afef78d4cd (fetch-radar.py, region-схема без cities) выключен через `hermes cron pause`. Гонка двух писателей одного файла; штатный update-radar-state достаточен.
- 14 кандидатов в удары РАЗОБРАНЫ: реальные удары НЕ терялись (strikes.json полная), все 14 = дубли/кликбейт Newsader. Фикс prune_stale (collect.py, коммит 5d6cd413) авто-истекает застойные негеокодированные. Newsader дал 0/14 полезных — вопрос ценности источника открыт для владельца.
- Radar Digest jobs (6e8c277c8dc8, 2746584f38d1) выключены (были enabled+error). Мусор дерева VPS (15 fuel-артефактов) в карантине /root/.npz-junk-quarantine-2026-07-18/ (mv, обратимо).

## Коммиты сессии (origin/main, прод)
effb0808 (детектор FRESH_SEC 45→90 + EMPTY-guard), 51120a4c (фантомы «ИДЁТ СЕЙЧАС» на /volna-dronov), 3c88b404 (бэкфилл волны 2026-07-16-2050), 761c6c78 (откат страниц при провале build-nav), fae1dfce + 05062c10 (корневой фикс: автопаблиш/krupnejshie коммитят свои файлы; спасена застрявшая волна 17.07), dc060d10 (future-date validator дыра meta{}).

## Next step
W30-замер SEO через API Вебмастера (кластеры «карта БПЛА» база 15.07 поз 6.8, «сколько НПЗ» поз 7.7 — лаг данных 1-2д прошёл) ЛИБО публикация /npz-lukojla (черновик+чек-лист готовы в ~/.npz-stagger/lukojla-draft/, слот был 18.07).

## Открытые долги
@BPLAlert_bot заморожен — чинить дефолт regions=["all"]/60мин ДО нового аккаунта; strikes 46/217 без title, 8 без source_url; TARGET_RE в collect ловит «мост» (оффтоп); бэклог роста — Google-канал/ВК-посев/almost-there.

## 🔴 Грабли для next Claude
Фронт/данные-правки только из чистого worktree на origin/main (дерево Мака hard-ресетится фоновым git-sync); push токеном `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue)` inline, gh auth switch ЗАПРЕЩЁН; строго нейтральный OSINT-тон; в дереве VPS бывают активные параллельные сессии — не трогать чужие незакоммиченные правки.

## First message
```
Продолжаю npz-tactical-map. Не начинай пока не скажу.

Прочитай по порядку:
1. docs/agents/SESSION_HANDOFF_2026-07-19.md
2. auto-memory: npz-volna-dronov-detector, npz-stuck-strike-candidates, npz-growth-backlog, npz-articles-2026-07-17
3. CLAUDE.md репо
4. docs/agents/tz-volna-close-2026-07.md

Первый шаг на выбор: W30-замер SEO через API Вебмастера ИЛИ публикация /npz-lukojla (черновик в ~/.npz-stagger/lukojla-draft/).

🔴 Грабли: правки только из чистого worktree на origin/main (git-sync хард-ресетит дерево Мака); push только GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue) inline, gh auth switch запрещён.

Жди мою команду.
```
