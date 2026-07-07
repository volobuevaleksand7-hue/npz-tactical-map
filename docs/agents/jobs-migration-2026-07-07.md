# Миграция `~/.hermes/cron/jobs.json` — 2026-07-07

Перестройка пайплайна публикаций (см. `docs/agents/audit-2026-07-07.md`,
`docs/npz-posting-style-v2.md`). Цель: один рендер (`hermes/bot/render.py`),
один дедуп (`hermes/bot/day_state.py`), один публикатор на формат
(сводка / молния / БПЛА-алерт). Ниже — точные джобы из `~/.hermes/cron/jobs.json`
на hermes-vps (id актуальны на 2026-07-07) и что с ними сделать.

**Правило применения:** выключать через `"enabled": false`, НЕ удалять джобу
(история/id может понадобиться). Проверять валидность JSON после каждой правки.

## Выключить (шлют в личку владельца, дублируют функциональность briefing/pipeline)

| id | name | schedule (UTC) | причина |
|---|---|---|---|
| `e3349b968fc7` | NPZ Morning Update | `0 8 * * *` | Дублирует BRIEFING; шлёт в личку 609952529, не в канал. Функциональность (обновить strikes/fuel-state) покрыта сборщиками `strikes`/`npz-status` (6ч) + NEWSWATCH. |
| `d12796c1987f` | NPZ Afternoon Update | `0 14 * * *` | Аналогично. Уже нерабочая (last_delivery_error: Chat not found). |
| `5be2ca0bad7e` | NPZ Evening Update | `0 20 * * *` | Аналогично. |

## Перевести на новые скрипты и время

| id | name | было | стало | действие |
|---|---|---|---|---|
| `fbfd237ab2ee` | NPZ MORNING BRIEFING | `0 7 * * *`, script=`npz-briefing-morning.sh` | `0 5 * * *` (05:00 UTC = 08:00 МСК) | Оставить script, но убедиться что `~/.hermes/scripts/npz-briefing-morning.sh` — **симлинк** на `hermes/cron-briefing.sh morning` (см. ниже). Обновить `schedule.expr` на `0 5 * * *`. |
| `80400595be27` | NPZ EVENING BRIEFING | `0 19 * * *`, script=`npz-briefing-evening.sh` | `0 17 * * *` (17:00 UTC = 20:00 МСК) | Аналогично; `npz-briefing-evening.sh` → симлинк на `hermes/cron-briefing.sh evening`. Обновить `schedule.expr` на `0 17 * * *`. |

## Оставить как есть (расписание не меняем)

| id | name | schedule (UTC) | комментарий |
|---|---|---|---|
| `442e756248de` | NPZ PUBLISH | `30 8,14,20 * * *`, script=`npz-publish.sh` | Оставить триггер как есть. Но: `npz-publish.sh` должен стать симлинком на `hermes/publish-vps.sh` (или вызывать его) — см. ниже. Внутри `publish-vps.sh` уже убран вызов editorial-дайджеста в канал (правка 2026-07-07). |
| `52be9f51fb63` | NPZ FUEL-VOICES | `41 */8 * * *` | Сборщик данных, не публикатор. Не трогать. |
| `fa4a26601b17` | NPZ WATCHDOG | `0 * * * *` | Health-монитор. Не трогать. |
| `449dbd8cf4ee` | NPZ COVER GENERATION | `0 7,19 * * *` | Обложки дня. Не трогать (можно сдвинуть на 15 мин раньше briefing при желании — не критично, сейчас 07:00/19:00 vs briefing 05:00/17:00 — обложка уже готова заранее). |
| `41c7f8787682` | NPZ Yandex Positions | `*/30 5-20 * * *` | SEO-мониторинг позиций, не публикатор. Не трогать. |
| `fc897ec9dd3b` | NPZ Subscriber Monitor | `*/5 * * * *`, script=`monitor_subscribers.py` | Служебное. Не трогать. |
| `134c39950ed9` | NPZ RADAR ALERTS | `*/10 * * * *` | БПЛА-алерты подписчикам — **НЕ ТРОГАТЬ** (директива п.5, отдельный канал алертов). |
| `09afef78d4cd` | NPZ RADAR FETCH | `*/5 * * * *` | Сборщик radar-state. Не трогать. |

## Требует правки промпта (не расписания)

| id | name | правка |
|---|---|---|
| `2f2bba9bb052` | NPZ NEWSWATCH | Промпт уже обновлён в `agents/update-prompt-newswatch.md` (убран `--dry-run`, добавлена ссылка на day_state/render.py). **На VPS промпт джобы хранится ВНУТРИ jobs.json** (поле `prompt`), это отдельная копия текста — нужно скопировать актуальный текст `agents/update-prompt-newswatch.md` в `jobs.json` вручную (через `hermes cron edit` или прямую правку JSON — с бэкапом). Ключевая замена: `python3 hermes/bot/strike_pipeline.py --dry-run` → `python3 hermes/bot/strike_pipeline.py` (без флага). |

## Симлинки скриптов (директива: копии → симлинки на репо)

`~/.hermes/scripts/` на VPS сейчас содержит **копии**, не симлинки:
- `npz-briefing-morning.sh`, `npz-briefing-evening.sh`, `npz-briefing.sh`, `npz-publish.sh`

Требуемое действие при деплое (см. основной отчёт, шаг «в»):
```bash
cd ~/.hermes/scripts
mkdir -p backup-2026-07-07
mv npz-briefing-morning.sh npz-briefing-evening.sh npz-briefing.sh npz-publish.sh backup-2026-07-07/
ln -s /root/npz-tactical-map/hermes/cron-briefing.sh npz-briefing-morning-base.sh   # если нужен параметризованный wrapper — см. ниже
```
Так как `cron-briefing.sh` принимает `$1` (morning|evening), а джоба `npz-briefing-morning.sh`
вызывается БЕЗ аргументов, симлинк не может напрямую параметризовать вызов.
Два варианта:
1. (проще, рекомендуется) Оставить `npz-briefing-morning.sh`/`npz-briefing-evening.sh`
   как маленькие **не гитуемые** обёртки на VPS вида
   `exec bash /root/npz-tactical-map/hermes/cron-briefing.sh morning`, обновляемые вручную
   при изменении сигнатуры (это уже фактически то, что там сейчас — только их надо
   ПЕРЕЗАПИСАТЬ этим одностроковым содержимым, а не оставлять старую логику-копию).
2. Разбить на `hermes/cron-briefing-morning.sh` и `hermes/cron-briefing-evening.sh`
   в репо (без аргументов) и симлинкать 1:1. Не делали в этом заходе — можно вынести
   отдельной задачей, если копии продолжат расходиться с репо.

`npz-publish.sh` → симлинк на `/root/npz-tactical-map/hermes/cron-publish.sh` (сигнатуры совпадают, без аргументов) — можно линковать 1:1 напрямую.

## Итоговая целевая карта каналов

| Формат | Публикатор | Канал/получатель |
|---|---|---|
| Утренняя/вечерняя сводка | `broadcast.py --briefing morning\|evening` | @NPZmap + активные подписчики + сайт `/news/<дата>` |
| Пополнение сводки (≤3/день) | `broadcast.py --update "..."` | editMessageCaption/Text того же поста |
| МОЛНИЯ TIER1 | `strike_pipeline.py` → `radar_publish.publish_strike_molniya` | @NPZmap + все активные подписчики, авто |
| МОЛНИЯ TIER2 | `strike_pipeline.py` → `radar_publish.publish_strike_tier2` | Владелец 609952529, кнопки «Опубликовать»/«Отклонить» → @NPZmap |
| БПЛА-алерт | `radar_alerts.py --send` | Подписчики (настройка /alerts), канал ≤1/30мин — НЕ ТРОГАЛИ |
| news.html/страница дня | `agents/gen-news.py` (вызывается из `broadcast.py --briefing` и `publish-vps.sh`) | сайт |

Всё, что раньше публиковало отдельно (`compute_digest`, `editorial_digest`) —
оставлено в коде, но не вызывается из publish-путей (`NPZ_LEGACY=1` для ручного теста).
