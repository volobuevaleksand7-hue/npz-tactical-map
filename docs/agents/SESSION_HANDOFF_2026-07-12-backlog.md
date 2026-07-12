# Session Handoff — npz-tactical-map — 2026-07-12 (backlog tail)

## Status
Прод v1.18.0 стабилен; остаётся 4 задачи из top10-бэклога, идём в режиме Subagent-Driven Development.

## Read first (по порядку)
1. `docs/backlog-top10-ideas.md`
2. `CLAUDE.md`
3. `docs/agents/SESSION_HANDOFF_2026-07-10-backlog.md`

## Остаток бэклога (порядок = приоритет)
- **#6** Компактный KPI-бар на мобильной главной (эффект 🟡 / усилие 🟢) — 3 цифры на первом экране (~35% выбывших мощностей · N НПЗ стоит · удары 7д) + свайп-шторка; данные из `data/fuel-state.json` + `strikes.json`; правки app.js/styles.css/index.html.
- **#5** Месячные хабы архива `/news/2026-06/` (🟡/🟡) — SEO под «удары по нпз июнь 2026», генератор рядом с `agents/gen-news.py`.
- **#8** Embed-виджет радара `/embed/radar` (iframe «угрозы сейчас: N регионов») для форумов/Telegram, обратные ссылки.
- **#3-хвост** На 404 добавить мини-статус (N НПЗ стоит / удары 7д) поверх готовых поиска + топ-5.

## Грабли
- 🔴 Фоновый git-sync/Гермес-racer в общем дереве: hard-reset + автостеш со сдвигом индексов → длинную работу вести в изолированном `git worktree add --detach origin/main <dir>`; стеш искать по содержимому, не по индексу. См. память про git-sync hazard.
- Фронт-гейт pre-commit (index.html/styles.css/app.js/radar.html/version.json/CHANGELOG.md/.vercelignore) — коммит только с `ALLOW_FRONTEND_RELEASE=1`.
- Навбар/меню/`/analytics` генерятся `agents/build-nav.py` из `data/seo-topics.jsonl` — руками не трогать; новая страница = реестр + build-nav.py + check-ia.py. Лейблы — в LABELS/HUB build-nav.py.
- `karta-azs.html` — клон index.html, build-nav его не берёт → регионы INDEX-MENU/DRAWER синкать вручную.
- Push: origin двигается ~раз в 10 мин (данные Гермеса) → `git rebase origin/main` перед пушем; пуш только `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue)` inline (никакого `gh auth switch`). Релиз = version.json + CHANGELOG.md + SW cache-bump (sw.js CACHE + ?v).
- UI: русские даты («12 июля 2026»), нейтральный OSINT-тон.
- Локальный preview — свой `python3 -m http.server` из правильного дерева (launch.json смотрит на устаревшую копию/8088); clean-URL rewrite только на Vercel, локально открывать `.html`. Верификация — через браузер (claude-in-chrome), не только тесты.

## Next step
Начать с #6 (KPI-бар) через скилл `superpowers:subagent-driven-development`, дальше по списку.

## First message
```
Продолжаем npz-tactical-map (папка ~/Documents/npz-tactical-map, НЕ «Alarm NPZ»). Прочитай сначала docs/agents/SESSION_HANDOFF_2026-07-12-backlog.md, затем docs/backlog-top10-ideas.md — там весь контекст остатка бэклога (4 задачи) и критичные грабли проекта (git-sync hard-reset, фронт-гейт, build-nav.py, push-рецепт).

Первый шаг: задача #6 — компактный KPI-бар на мобильной главной (эффект 🟡, усилие 🟢, быстрая победа). Запусти скилл superpowers:subagent-driven-development и веди работу через него, задача за задачей по приоритету из хэндоффа.

Жди мою команду.
```
