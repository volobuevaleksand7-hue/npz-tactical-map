# Handoff — npz-tactical-map — 2026-07-10 (топ-10 бэклог)

## Status
Внедряем топ-10 идей из `docs/backlog-top10-ideas.md` по «полкам». **Полка C** (#10 перф/self-host,
#7 RSS, #9 /metodologiya) → v1.14.0 и **Полка A** (#1 единая шапка через build-nav + head-линт)
→ v1.16.0 — обе в проде, проверены. Остались полки B/D/E/F + #5.
(Отдельный трек «обложки/АЗС» — в `SESSION_HANDOFF_2026-07-10.md`, не смешивать.)

## ⚠️ Первым делом
- Работать в **`~/Documents/npz-tactical-map`**, НЕ в `~/Documents/Alarm NPZ` (устаревшая копия, сессия открывается там).
- Origin двигается каждые ~10 мин (data Гермеса) → перед push всегда `git rebase origin/main`; пуш: `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue) git -c credential.helper= -c credential.helper='!gh auth git-credential' push origin main` (`gh auth switch` НЕ использовать — глобальный, ломает другие проекты). Push в main = авто-деплой в прод.
- Гейт pre-commit (7 файлов): `index.html·styles.css·app.js·radar.html·version.json·CHANGELOG.md·.vercelignore` → `ALLOW_FRONTEND_RELEASE=1`.

## Read first (in order)
1. `docs/backlog-top10-ideas.md` — 10 идей + порядок
2. `docs/superpowers/specs/2026-07-10-unified-header-generator-design.md` — спек #1 (эталон подхода)
3. `CLAUDE.md` — правила проекта

## In-session decisions
- **build-nav владеет всем `<header class="news-header">`**: новая hand-страница = пустой `<header class="news-header"></header>`, build-nav наполняет лого+меню+футер. radar/index — свои шапки, не трогать.
- **Логотип унифицирован `/news`→`/`**; /news доступен пунктом «Сводки».
- **Head — линтом в check-ia** (warnings), НЕ централизуем. Остаток 3 known-warning: `404` (og — уйдёт в идею #3), `sources`/`support` (legacy/скрытая, свои inline-стили) — приемлемо.
- Эталон-флоу (нравится пользователю): разведка → правки сам последовательно → браузер-верификация (preview_* конфиг `npz-verify`, порт 8811) → релиз (версия+CHANGELOG+SW-bump) → rebase+push → верификация прода.

## Next step
Выбрать следующую полку (спросить пользователя): **B #4** внутренний поиск (статический JS — платит и полке B, и строке поиска в 404) · **#5** месячные хабы `/news/2026-06/` (разблокирован после #1) · флагман **E #2** «АЗС рядом» (геолокация + фильтр «есть топливо»).

## First message
```
Продолжаю npz-tactical-map (внедряем топ-10 идей по полкам). Не начинай пока не скажу.

Прочитай:
1. `~/Documents/npz-tactical-map/docs/agents/SESSION_HANDOFF_2026-07-10-backlog.md`
2. `~/Documents/npz-tactical-map/docs/backlog-top10-ideas.md`

Полки A и C уже в проде (v1.16.0). Дальше на выбор: #4 (поиск), #5 (месячные хабы, разблокирован) или флагман #2 (АЗС рядом). Жди мою команду.
```
