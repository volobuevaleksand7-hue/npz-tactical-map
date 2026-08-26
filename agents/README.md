# Агенты-сборщики (routine)

Агенты крутятся на VPS по cron и держат данные свежими. После каждого изменения — `git push`. Сайт читает `data/*.json` **напрямую из GitHub raw-CDN**, поэтому обновление видно на карте без редеплоя Vercel (на следующем 5-минутном опросе фронта). Vercel хостит только статическую оболочку.

**Важно:** cron/Hermes-агенты не правят оболочку сайта (`index.html`, `styles.css`,
`app.js`, `radar.html`) и release-файлы (`version.json`, `CHANGELOG.md`) без
явного UI-release запроса. Перед такой работой читать `AGENT_ACTIVITY.md` и
`HERMES.md`; commit protected files требует `ALLOW_FRONTEND_RELEASE=1`.

## Модели по силе задачи + частота

| Агент | Файл | Модель | Частота |
|---|---|---|---|
| **NPZ-STATUS** | `data/fuel-state.json` (заводы/терминалы) | Haiku | 4×/сутки (00/06/12/18 UTC) |
| **FUEL-MARKET** | `data/fuel-state.json` (дефицит/баланс/меры) | Haiku | 4×/сутки |
| **HISTORY-CRIMEA** | `data/history-crimea.json` (хроника + Крым) | Haiku | 4×/сутки |
| **STRIKES** | `data/strikes.json` (удары по городам) | Haiku | 4×/сутки |
| **ROADS** | `data/roads.json` (дороги/топл. логистика) | Haiku | 4×/сутки |
| **FORECAST** | `data/forecast.json` (сценарный прогноз) | **Opus** | раз в неделю (вс 03:45 UTC) |

```
agents/
  run-agent.sh             # раннер: claude -p → валидация ВСЕХ data/*.json → commit → push
  update-prompt-npz.md     # NPZ-STATUS (статусы заводов/терминалов)
  update-prompt-market.md  # FUEL-MARKET (дефицит/баланс/меры)
  update-prompt-history.md # HISTORY-CRIMEA (хроника + Крым)
  update-prompt-forecast.md# FORECAST (Opus, раз в неделю)
  crontab.txt              # ⚠️ ОБРАЗЕЦ установки, НЕ живое расписание (см. шапку файла)
  fleet-snapshot.sh        # снимок всех 3 планировщиков -> docs/agents/FLEET-SNAPSHOT.md
  logs/                    # логи запусков
```

## Живое расписание флота

🔴 Расписание живёт в **трёх** местах, которые друг о друге не знают: `crontab -l`,
`~/.hermes/cron/jobs.json` (эти задания не видны ни в crontab, ни в syslog) и systemd
timers. Единственный достоверный список — снимок:

```bash
ssh hermes-vps 'cd /root/npz-tactical-map && bash agents/fleet-snapshot.sh'   # обновить
bash agents/fleet-snapshot.sh --check                                          # RC=1 если разошлось
```

Результат — `docs/agents/FLEET-SNAPSHOT.md`. Руками его не правят.

## Установка на VPS (hermes-vps, 104.252.77.253)

> ⚠️ Прежний адрес 193.28.186.23 выключен навсегда — не использовать.

```bash
ssh hermes-vps
git clone git@github.com:volobuevaleksand7-hue/npz-tactical-map.git /root/npz-tactical-map   # или https
cd /root/npz-tactical-map
chmod +x agents/run-agent.sh
mkdir -p agents/logs

# git push без пароля: настроить deploy key или gh auth (репо приватный/публичный — оба ок)
git config user.name  "npz-agent"
git config user.email "agent@volobuevaleksand7-hue"

# проверить вручную:
NPZ_REPO=/root/npz-tactical-map ./agents/run-agent.sh agents/update-prompt-npz.md npz-status

# поставить cron:
crontab -l | cat            # посмотреть текущий
( crontab -l 2>/dev/null; cat agents/crontab.txt ) | crontab -
```

## Модель

По умолчанию `claude-haiku-4-5-20251001` (самая дешёвая). Меняется через `NPZ_MODEL`.

## Безопасность данных

- Раннер валидирует JSON перед коммитом; при поломке — `git checkout` (откат), пуша нет.
- Агентам разрешены только `Read, Write, WebSearch, WebFetch`.
- Координаты/названия/мощности агенты не трогают — только статусы, даты, регионы дефицита, события и `meta`.
- Всё помечено бейджем «ОЦЕНКА» — это OSINT-агрегация, не официальные данные.
