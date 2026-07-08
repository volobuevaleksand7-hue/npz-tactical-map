# @BPLAlert_bot — анонимный алерт-бот (runbook)

Второй инстанс того же `hermes/bot/poll.py`, что и `@NpzFuel_Bot`, но под отдельным
анонимным Telegram-аккаунтом (Erhan08263) и со своей папкой данных. Публичное лицо
проекта не связано с владельцем. `@NpzFuel_Bot` продолжает работать параллельно.

Развёрнут на Hermes VPS 2026-07-09 (v1.7.0). Кода не форкали — разница только в env.

## Конфигурация (env)

| Переменная | Значение | Зачем |
|---|---|---|
| `NPZ_BOT_DIR` | `/root/.bpla-alert` | своя папка: token, subscribers.json, poll-state, radar-alert-state |
| `NPZ_REPORT_CHAT` | `609952529` (Sergey, основной) | куда слать отчёт о счётчике подписчиков |
| `NPZ_REPORT_TOKEN` | `/root/.npz-bot/token` | токен бота-отправителя отчётов (@NpzFuel_Bot) |
| `NPZ_OWNER_CHAT` | *(не задан)* | альт. ЛС-уведомление о каждой подписке через ЭТОГО бота; вытеснено REPORT_* |
| `NPZ_REPO` | `/root/npz-tactical-map` | общий репозиторий/данные |
| `NPZ_CHANNEL` | *(пока не задан)* | канал для сводок; включить, когда канал создан (см. ниже) |

### Счётчик подписчиков → отчёт через @NpzFuel_Bot

`poll.py` считает активных подписчиков и на новую подписку шлёт отчёт в
`NPZ_REPORT_CHAT` через `@NpzFuel_Bot` (`NPZ_REPORT_TOKEN`). Пороги (`_should_report`):
**≤25 — о каждом · 26–100 — каждый 5-й · 101–500 — каждый 10-й · >500 — каждый 50-й.**
Водяной знак `last_report_count` в `poll-state.json` — без повторов при колебаниях счётчика.
Тест логики порогов: `python3 hermes/bot/test_poll_report.py`.

Токен лежит в `/root/.bpla-alert/token` (chmod 600). В git НЕ коммитить.

## Cron (уже установлен, `crontab -l`)

```
# @BPLAlert_bot
* * * * *    NPZ_REPO=/root/npz-tactical-map NPZ_BOT_DIR=/root/.bpla-alert NPZ_REPORT_CHAT=609952529 NPZ_REPORT_TOKEN=/root/.npz-bot/token /usr/bin/python3 /root/npz-tactical-map/hermes/bot/poll.py >> /root/npz-tactical-map/agents/logs/bpla-bot.log 2>&1
*/10 * * * * NPZ_REPO=/root/npz-tactical-map NPZ_BOT_DIR=/root/.bpla-alert /usr/bin/python3 /root/npz-tactical-map/hermes/bot/radar_alerts.py --send >> /root/npz-tactical-map/agents/logs/bpla-bot.log 2>&1
```

- `poll.py` каждую минуту — обрабатывает `/start`, кнопки таймера/регионов, шлёт
  владельцу уведомление о новой подписке.
- `radar_alerts.py --send` каждые 10 минут — рассылает подписчикам тревоги по их
  региону и интервалу (10м/30м/1ч/2ч/6ч/12ч/24ч).

Лог: `agents/logs/bpla-bot.log`. Бэкап crontab перед правкой: `/root/crontab.backup.*`.

## Канал (сводки) — включить, когда создан

Механизм уже есть в `broadcast.py` (env `NPZ_CHANNEL`). Бот сам создать канал не
может — владелец создаёт его вручную с аккаунта Erhan08263 и добавляет `@BPLAlert_bot`
**админом**. После этого добавить в crontab (сводки 08:00/20:00 МСК = 05:00/17:00 UTC):

```
0 5,17 * * * NPZ_REPO=/root/npz-tactical-map NPZ_BOT_DIR=/root/.bpla-alert NPZ_CHANNEL=@<username_канала> /usr/bin/python3 /root/npz-tactical-map/hermes/bot/broadcast.py --briefing morning >> /root/npz-tactical-map/agents/logs/bpla-bot.log 2>&1
```

(В канал уходят только сводки/редкие посты — основной поток тревог идёт в личку бота.)

## Плашки на сайте → бот

- `index.html`: закрываемый баннер над картой (localStorage `tgAlertClosed`).
- `radar.html`: CTA в подвале ленты (`.feed-cta`).
- Обе ведут на `https://t.me/BPLAlert_bot`.

## Проверка

```
curl -s "https://api.telegram.org/bot$(cat /root/.bpla-alert/token)/getMe"   # @BPLAlert_bot
tail -f /root/npz-tactical-map/agents/logs/bpla-bot.log
cat /root/.bpla-alert/subscribers.json
```
