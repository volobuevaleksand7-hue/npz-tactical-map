# Incidents — инбокс автоинцидентов для Hermes

Сюда автоматические сторожа (сейчас `agents/summary-watchdog.py`) пишут **OPEN**-инциденты,
которые Hermes должен разобрать. Это не журнал (журнал — `AGENT_ACTIVITY.md`), а короткий
список «что сломалось и что с этим сделать».

## Протокол для Hermes (обязательно)

1. На **каждом** запуске, сразу после `git pull --rebase` и чтения `AGENT_ACTIVITY.md`,
   прочитай этот файл. Любой блок со `status: OPEN` — задача с приоритетом сразу за
   указаниями оператора.
2. Выполни шаги из тела инцидента (они конкретные и самодостаточные).
3. Когда починил — поменяй в блоке `status: OPEN` → `status: RESOLVED` и допиши
   `resolved: <дата МСК> — <что сделал>`. Закоммить через `git-sync.sh` как обычную работу
   и оставь строку в `AGENT_ACTIVITY.md`.
4. Сторож сам закроет свой инцидент (`RESOLVED (авто)`), если проблема исчезнет к его
   следующему прогону (8:15/20:15 МСК). Но НЕ жди его — чини OPEN сам.
5. RESOLVED-блоки старше ~7 дней можно удалять при уборке.

Формат блока (STATUS = OPEN либо RESOLVED — это лишь пример, не живой инцидент):

```
## [STATUS] <id>
status: STATUS
opened: <дата МСК> — <кто/что завёл>
<диагноз>
Что сделать:
- <шаг 1>
- <шаг 2>
```

<!-- INCIDENTS BELOW (newest first) -->

## [RESOLVED] cover-fallback-2026-07-19
status: RESOLVED
opened: 2026-07-19 08:15 МСК — summary-watchdog
Карточка за 2026-07-19 на месте, но обложка = заглушка og-image. Обычно самолечение чинит само (Codex работает и на VPS, и на Маке); если висит — вероятно кончились image-кредиты Codex-воркспейса.
Что сделать:
- `python3 hermes/scripts/build-covers.py --dates 2026-07-19` (Codex-first) → `python3 agents/gen-news.py` → git-sync + деплой;
- если Codex «out of credits» — пополнить воркспейс, либо разово `NPZ_COVERS_ALLOW_OPENROUTER=1` при живом OpenRouter-ключе.

resolved: 2026-07-19 20:15 МСК — проблема исчезла (авто, сторож)
## [RESOLVED] card-missing-2026-07-12
status: RESOLVED
opened: 2026-07-12 08:15 МСК — summary-watchdog
resolved: 2026-07-12 11:55 МСК — Opus/Mac: причина — пайплайн пропустил пересборку (последний gen-news 00:55Z, до удара по Сызрани). Сгенерил обложку (Codex) + `gen-news.py` + деплой. Карточка за 12.07 живая.
На живом /news НЕТ карточки-сводки за 2026-07-12.
Что сделать:
- если в data/strikes.json уже есть удары за 2026-07-12 → `python3 agents/gen-news.py` + git-sync + деплой;
- если ударов за 2026-07-12 нет → прогони сборщик strikes (agents/update-prompt-strikes.md) за эту дату, затем gen-news;
- проверь https://npz-tactical-map.vercel.app/news
