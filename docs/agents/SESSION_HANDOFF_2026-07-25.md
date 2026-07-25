# Handoff — npz-tactical-map — 2026-07-25

## Status
Всё сделано за сессию 24–25.07 **на проде**, дерево чистое. Раскрутка WB-кластера (оптимизирован чемпион + опубликованы **3 новые страницы**: `/sgorel-sklad-wildberries-chto-delat` v1.20.8, `/karta-skladov-wildberries` и `/udar-sklad-wildberries-peterburg` v1.20.9), нормализация данных по ударам, детерминированный пересчёт национального баланса, фикс heartbeat-бага ложных «мёртвых» агентов, и главное — вычищен `%`-баг в crontab VPS, который 7 дней молча глушил 3 сборщика. На VPS `health: healthy | stale 0/11 | dead 0`.

## Что живёт (проверять, не переписывать)
- WB-кластер = 7 live-страниц + `/udar-po-skladu-ozon` намеренно `planned`/404 (подтверждённых ударов по Ozon нет). 🔴 Новые удары по складам маркетплейсов — в существующие страницы (хроника / Петербург), НЕ новой страницей.
- Чемпион `/skolko-skladov-wildberries-ozon` — генератор `agents/gen-warehouses-page.py`, руками не править.
- Цифры панели национального баланса + таймлайн — генератор `agents/recalc-national-balance.py` (`--check`/`--demo`). 🔴 Цифры правит генератор, НЕ руки; в прозе (`national_balance.notes`) запрещено дублировать числа, которые считает код (правило в `agents/update-prompt-market.md`).
- Сборщики на VPS hermes (после фикса crontab): newswatch (10×/сут, главный), collect.py :05, strike-candidates.py :20, strike-confirm.py 33 */6, strike_pipeline, 10 data-агентов — снова живы, коммиты идут.
- `dead_count` в heartbeats = 0 (было ложных «5 не на связи»); ручной heartbeat через Write больше нигде не прописан в промптах.

## Read first (in order)
1. `docs/agents/SESSION_HANDOFF_2026-07-25.md` (этот файл)
2. `AGENT_ACTIVITY.md` (записи 24.07 и 25.07)
3. `docs/seo-playbook.md`

## In-session decisions
- 🔴 **Headline «мощностей выбито полностью» врал в 1.7× (64% вместо 39%):** агент писал в `capacity_offline_*` значение `throughput_shortfall`. Фикс — детерминированный пересчёт из `refineries[]` в `recalc-national-balance.py` + авто-фикс в `.githooks/pre-commit`.
- 🔴 **Плашка «5 агентов не на связи» была ложной:** агент без Bash-тула «выполнил» промпт-инструкцию писать heartbeat через Write и обрушил общий `data/heartbeats.json` с 12 ключей до 1. Убрал секцию ручного heartbeat из 5 промптов + в `agents/git-sync.sh` HEAD стал полом (union с более свежей меткой).
- 🔴 **ГЛАВНОЕ: три сборщика молча не запускались 7 дней (с 18.07):** неэкранированный `%` в crontab рубит команду (`$(date -u +%Y…)`) — bash падает с EOF-ошибкой, вся строка включая скрипт не выполняется. Экранировал `\%` в 4 строках crontab (бэкап `/root/crontab.bak.20260725-051054`). Проверено по коммитам `data(collect): 2026-07-25T06:05Z`, `data(strike-candidates): 2026-07-25T05:20Z`.
- `data/capacity-timeline.json` был сиротой (не дописывался с 12.07) — точку теперь пишет `recalc-national-balance.py`, ТОЛЬКО при изменении процента (панель берёт последние 12 точек; ежедневная запись схлопнула бы дугу с мая). Дуга 18% → 39%.
- Выполнены 2 анонимных git-пуша для параллельной флит-сессии (VPN-плашка «Международное освещение» на чемпионе); третий отклонён как non-fast-forward, чтобы не снести свои страницы.

## Next step
- ⏰ **26.07 10:00 МСК** — снять замер позиций WB-кластера через API Яндекс.Вебмастера (лаг ~2 сут), решить нужны ли реопты. 🔴 Не править реопт до замера.
- 🔴 `collect.py` запускается, но источник мёртв: YouTube отдаёт 404 на RSS с IP VPS (подтверждено — блок IP, не User-Agent: контрольный канал 404 с VPS и 200 с Мака), сам фид Newsader отдаёт 500 даже с чистого IP. Нужен новый источник/способ забора — решение за владельцем, не начинать без спроса.
- ⚠️ В `mimo-rotate` всплыл OpenRouter (`502 ResourceExhausted`), хотя по памяти его выпилили 22.07 — проверить конфиг ротации (расход).
- ⚠️ На VPS в корне репо мусорные untracked-файлы, включая `write_heartbeat.py` (след бага с heartbeat) — убрать при уборке.
- `strike-confirm.py` рабочий, но медленный: GDELT отдаёт 429 → backoff ~50с. 🔴 При диагностике не гонять `timeout N script | tail` — съедает вывод, создаёт ложное «скрипт молчит».

## First message
```
Продолжаю npz-tactical-map. Не начинай пока не скажу.

Прочитай:
1. `docs/agents/SESSION_HANDOFF_2026-07-25.md`
2. `AGENT_ACTIVITY.md` (записи 24.07 и 25.07)
3. `docs/seo-playbook.md`

🔴 Перед любой правкой: `git log --oneline -8` (сверить с параллельными сессиями), правки фронта — только с `ALLOW_FRONTEND_RELEASE=1`, push — точечным `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue)`, `gh auth switch` ЗАПРЕЩЁН. Живая копия — `/Users/sergeyrama/Documents/npz-tactical-map`, НЕ `Alarm NPZ`.

Затем жди мою команду.
```
