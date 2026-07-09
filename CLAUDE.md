# npz-tactical-map — project memory

## 📍 КАНОН РАСПОЛОЖЕНИЯ (деанон-миграция 2026-07-07 — ЧИТАЙ ПЕРВЫМ)

Видишь где-то старый путь/аккаунт — он УСТАРЕЛ, верь этому блоку.

- **Локальный клон (Mac):** `~/Documents/npz-tactical-map` — единственный. НЕ `Alarm NPZ/`, НЕ `Projects/`.
- **Репозиторий:** `github.com/volobuevaleksand7-hue/npz-tactical-map` (public). Старый `sergeyramas/npz-tactical-map` теперь **PRIVATE-бэкап — им НЕ пользоваться**.
- **GitHub-аккаунт для push:** анонимный `volobuevaleksand7-hue` (`gh auth switch --user volobuevaleksand7-hue` если не активен). Коммит-identity анонимная — **НИКОГДА не коммить под реальным именем/почтой**.
- **Клон на VPS:** `/root/npz-tactical-map` на `hermes-vps`, push через ssh-алиас `github-npznew` (ключ `~/.ssh/npz_deploy_new`).
- **Данные сайта (RAW):** `raw.githubusercontent.com/volobuevaleksand7-hue/npz-tactical-map/main/`.
- **Деплой:** push в `main` (кроме `data/**`) → GitHub Action `deploy.yml` → Vercel (проект на аккаунте `sergeyramas`, деплой по токен-секрету на новом репо).
- **Кто пишет данные:** ТОЛЬКО Hermes VPS-крон (`npz-agent-hermes`). Облачные RemoteTrigger-рутины ВЫКЛючены и всё ещё указывают на СТАРЫЙ репо — **не включать без перенацеливания на новый репо + новый PAT**.

## Identity
Тактическая дашборд-карта состояния НПЗ РФ (удары/мощности/баланс/логистика/дефицит). Статический сайт на Vercel, данные в `data/fuel-state.json`, обновляются cron-агентами на VPS.

## Stack
- Frontend: vanilla HTML/CSS/JS + Leaflet 1.9 (CARTO dark tiles, без ключей). Без сборки.
- Data: единый `data/fuel-state.json` (схема: meta / national_balance / fuel_balance / refineries[] / export_terminals[] / pipelines[] / deficit_regions[] / events[]).
- Deploy: Vercel (framework = Other / static). Репо: github.com/volobuevaleksand7-hue/npz-tactical-map.
- Agents: VPS 193.28.186.23 cron, модель `claude-haiku-4-5-20251001`. См. `agents/`.

## Commands
- Локально: `python3 -m http.server 8080`
- Деплой: push в main → Vercel авто-редеплой
- Ручной прогон агента: `./agents/run-agent.sh agents/update-prompt-npz.md npz-status`

## Verification
- JSON валиден: `python3 -c "import json;json.load(open('data/fuel-state.json'))"`
- Карта грузится, маркеры зел/жёлт/красн, попапы открываются, тикер идёт, NEXT SYNC тикает.

## Guardrails
- Режим ОЦЕНКА — всегда показывать дисклеймер. Это OSINT, не официальные данные.
- Агенты меняют только status/даты/дефицит/события/meta. Координаты, названия, мощности — не трогать.
- **Обложки постов рендерит ТОЛЬКО Codex.** Любой агент, которому нужна обложка сводки (сайт `/news` + Telegram), идёт через `python3 hermes/scripts/build-covers.py` (внутри `codex exec image_gen`, img2img по фото события). НЕ рисовать самому, НЕ звать Gemini/др. модель. PIL-фолбэк `agents/gen_cover_today.py` — автоматический бэкстоп: если Codex недоступен (429/кредиты/не ответил), обложка генерится им, чтобы пост вышел с картинкой (не блокировать выпуск). В отчёте пометить, что обложка — фолбэк, чтобы можно было перегенерить через Codex после пополнения кредитов.
- **Нейтральный русскоязычный OSINT-тон — жёстко.** Карта/сводки — сухая фактология про топливную инфраструктуру РФ. ЗАПРЕЩЕНО: вербатим-репосты Telegram-каналов, украинский язык в данных, пропаганда/лозунги любой стороны («Слава Україні», «терорист», «орки», «доблестная ПВО»), офф-топик (сбитые самолёты/лётчики), `confidence` вне confirmed|reported|rumored. Гарант — `agents/sanitize-strikes.py` в pre-commit хуке (`.githooks/pre-commit`): вырезает такое из `data/strikes.json` при ЛЮБОМ коммите. Правила-первой-линии — в `agents/update-prompt-newswatch.md` и `update-prompt-strikes.md`.
- Раннер валидирует JSON и откатывает при поломке до пуша.

## ⛔ Общее рабочее дерево — координация (инцидент 2026-07-09)
Несколько агентов/сессий работают в ОДНОМ `~/Documents/npz-tactical-map`. За одну сессию параллельная сессия **трижды** снесла несохранённые UI-правки, гоняя `git pull --rebase --autostash` в общем дереве — autostash засташивал чужой незакоммиченный `app.js`/`index.html`/`analytics.html`. Официальный `agents/git-sync.sh` **безопасен** (коммитит `data/` первым, без `--autostash`); проблема — в РУЧНЫХ git-командах отдельных сессий.

ПРАВИЛА (обязательны для любого агента/сессии в этом репо):
- **НИКОГДА** не запускать `git pull --rebase --autostash` и `git add -A` в общем дереве. Данные — только `agents/git-sync.sh "<msg>"` (трогает лишь `data/`). Свои файлы — `git add <явный список>` + коммит СРАЗУ после правки (UI-shell → `ALLOW_FRONTEND_RELEASE=1`).
- **Не оставляй UI-правки незакоммиченными** — отредактировал `index.html`/`styles.css`/`app.js`/`*.html`, закоммить в тот же заход; любой чужой sync может их засташить.
- **Долгая/многофайловая UI-работа при активных других агентах → отдельный git worktree на ветку:** `git worktree add ../npz-<slug> -b <slug>`, работать там, `git push`, слить и удалить worktree. Общее дерево — один UI-редактор за раз.

## Data sources (seed)
Reuters (via liga.net), Meduza, Moscow Times, The Bell, Новая газета Европа, Euronews — см. source_url в JSON и ресёрч-отчёт от 2026-06-11.
