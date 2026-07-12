# @BPLAlert_bot — анонимный алерт-бот (runbook)

Публичный анонимный бот тревог/ударов проекта «Топливный фронт РФ» под отдельным
Telegram-аккаунтом (Erhan08263). `@NpzFuel_Bot` работает параллельно (приватный).

> ⚠️ **Актуализировано 2026-07-12.** Раньше бот был «2-м инстансом `poll.py`» на cron.
> Сейчас архитектура другая — см. ниже. Старую схему (`poll.py` + `.bpla-alert`) не воскрешать.

## Архитектура (что реально крутится)

| Компонент | Что | Данные |
|---|---|---|
| **Демон** | systemd `npz-bpl-bot.service` → `hermes/bot/poll_bpl.py` (python-telegram-bot, long-poll) | обрабатывает `/start`, `/status`, `/radar`, `/regions`, `/interval`, `/alerts`, тумблеры, `/pause`, `/unsubscribe` |
| **Угрозы (радар)** | cron `*/2` `radar_alerts.py --send` | `data/radar-state.json` → подписчикам с активным регионом |
| **Удары (подтверждённые)** | cron `*/3` `strike_alerts.py --send` | `data/strikes.json` → подписчикам с `alerts.attacks` |

**Каноническая папка данных: `/root/.npz-bot-bpl/`** (`subscribers.json`, токен→`/root/.npz-bot/token-bplalert`, `radar-alert-state.json`, `strike-alert-state.json`). Демон: `Environment=NPZ_BPL_DIR=/root/.npz-bot-bpl`.

Устаревшие папки `/root/.bpla-alert`, `/root/.bpl-bot`, `/root/.npz-bot/bpl` — их
`subscribers.json` **симлинкнуты на канон** (2026-07-12, чтобы стрей-скрипт не разъехался
по базам). Бэкап перед сведением: `/root/bpl-dirs.backup.*.tgz`.

## Cron (live, `crontab -l`)

```
*/2 * * * * NPZ_REPO=/root/npz-tactical-map NPZ_BOT_DIR=/root/.npz-bot-bpl python3 .../radar_alerts.py --send   >> agents/logs/bpla-bot.log 2>&1
*/3 * * * * NPZ_REPO=/root/npz-tactical-map NPZ_BOT_DIR=/root/.npz-bot-bpl python3 .../strike_alerts.py --send  >> agents/logs/bpla-bot.log 2>&1
```

⚠️ Строка ежеминутного `poll.py` с `NPZ_BOT_DIR=/root/.bpla-alert` **закомментирована**
(2026-07-12): она конфликтовала с демоном за один токен (`getUpdates` → 409). Не включать.

## Значки в сообщениях (единый визуальный язык)

- Угроза: 🛩 БПЛА · 🚀 ракеты · 🛩🚀 вместе. Удар (уже прилетело): 💥🛩 / 💥🚀. Отбой: 🟢.
- Групповой алерт угроз — по значку на каждый регион + адаптивная шапка (`radar_alerts.format_group_text`).
- Удары — `strike_alerts.format_strike` (город, объект, дата рус + время МСК, карта).

## Типы уведомлений и интервал

`alerts.threats` (угрозы-радар) / `alerts.attacks` (удары) — тумблеры `/alerts`.
Интервал напоминаний — `/interval` или кнопки (10м…24ч / по изменениям).
**Сохранение настроек починено 2026-07-12** (`ensure_sub(subs=)` — был баг двойной загрузки).
Регресс-тест: `hermes/bot/test_poll_bpl_persist.py` (venv).

## Дедуп ударов / устойчивость

- `strike_alerts`: дедуп по `id` (или `date|time|city|target`), state `strike-alert-state.json`,
  init-guard (первый запуск засевает архив, историю не рассылает). Тест `test_strike_alerts.py`.
- `radar_alerts`: при 429/5xx/сети `last_sent` откатывается → повтор в след. прогоне; 403
  (заблокировал) не зацикливаем; не-HTTP ошибка не роняет прогон. Тест `test_radar_alerts.py`.

## Канал (сводки) — отложен

Бот сам канал не создаёт. Владелец создаёт с Erhan08263, добавляет `@BPLAlert_bot` админом,
даёт `@username` → включить `NPZ_CHANNEL=@...` в broadcast-cron (механизм в `broadcast.py`).

## Плашки на сайте → бот

`index.html` (баннер над картой, localStorage `tgAlertClosed`) и `radar.html` (`.feed-cta`) → `https://t.me/BPLAlert_bot`.

## Проверка

```
systemctl status npz-bpl-bot.service
tail -f /root/npz-tactical-map/agents/logs/bpla-bot.log
NPZ_BOT_DIR=/root/.npz-bot-bpl python3 hermes/bot/radar_alerts.py --dry-run    # кому уйдут угрозы
NPZ_BOT_DIR=/root/.npz-bot-bpl python3 hermes/bot/strike_alerts.py --dry-run   # кому уйдут удары
cat /root/.npz-bot-bpl/subscribers.json
```

⚠️ Токены в git НЕ коммитить (репо публичный). Известная мелочь: cron `sub-report.sh`
ссылается на несуществующий файл — задача молчит (не критично).
