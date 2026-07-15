# Heartbeat Plan

## Problem

Cloud cron agents sometimes run but commit nothing (no news, or push fails).
The healthcheck sees a stale `generated_at` and cannot distinguish "agent alive, no news" from
"agent dead", firing false Telegram alerts.

## Solution: Heartbeat File

A separate `data/heartbeats.json` records when each agent last ran successfully,
independent of whether new data was committed.

## `data/heartbeats.json` Schema

```json
{
  "npz-status": "2026-06-20T18:07Z",
  "fuel-market": "2026-06-20T16:30Z",
  "strikes": "2026-06-20T17:00Z",
  "history-crimea": "2026-06-18T12:00Z",
  "roads": "2026-06-19T09:00Z",
  "forecast": "2026-06-17T22:00Z",
  "grid-status": "2026-06-20T15:00Z"
}
```

- Keys are agent labels (same as `<label>` in `run-agent.sh`).
- Values are ISO-8601 timestamps (with trailing `Z` or `+00:00`).
- The file is optional. If missing or unparseable, healthcheck treats all agents as having no heartbeat (never crashes).

## Label-to-Key Map (for `run-agent.sh` integration)

| `run-agent.sh` label | heartbeat key |
|-|-|
| `npz-status` | `npz-status` |
| `fuel-market` | `fuel-market` |
| `history-crimea` | `history-crimea` |
| `strikes` | `strikes` |
| `roads` | `roads` |
| `forecast` | `forecast` |
| `fuel-voices` | `fuel-voices` |
| `grid-status` | `grid-status` |

## How `run-agent.sh` Should Write a Heartbeat

After a successful agent exit (exit code 0), `run-agent.sh` should:

1. Read existing `data/heartbeats.json` (or `{}` if missing/invalid).
2. Update the key matching its `$LABEL` with the current UTC timestamp.
3. Write back `data/heartbeats.json` with `indent=1`.

This happens **regardless of whether the agent actually changed any data files**.
The heartbeat records "agent ran successfully", not "data changed".

Example shell snippet for `run-agent.sh`:

```bash
HB_FILE="data/heartbeats.json"
HB_TS=$(date -u +"%Y-%m-%dT%H:%MZ")
python3 -c "
import json, os
f = '$HB_FILE'
d = json.load(open(f)) if os.path.exists(f) else {}
d['$LABEL'] = '$HB_TS'
json.dump(d, open(f, 'w'), indent=1)
"
```

## Status Semantics (per file in `health.json`)

> **Обновлено 15.07.2026.** Данные и живость агента — ДВЕ ОРТОГОНАЛЬНЫЕ оси.
> Раньше `ok` ставился при свежих данных независимо от heartbeat, из-за чего
> мёртвый агент был невиден, пока его данные не успевали протухнуть.

| Status | Data age | Heartbeat age | Meaning | Alert? |
|-|-|-|-|-|
| `ok` | within threshold | within window | Data fresh, agent reporting | No |
| `dead` | within threshold | over window or missing | **Agent not reporting**, data merely hasn't expired yet (or another writer bumped `generated_at`) | **Yes** |
| `stale_alive` | over threshold | within window | Agent ran, no new data | **No** (suppress alert) |
| `stale_dead` | over threshold | over window or missing | Agent likely dead | **Yes** |
| `unknown` | no `generated_at` | any | Cannot determine data age | No |

## Thresholds (unchanged)

No changes to WATCH thresholds in this iteration. Proposals below for future consideration:

- `fuel-availability.json`: 12h is tight for a bi-daily agent; consider raising to 18h.
- `forecast.json` / `economy.json`: 200h (8.3 days) is appropriate for weekly forecast agents.
- `roads.json`: 48h is generous; consider tightening to 36h.

## Alert Keying

The Telegram alert should key off `dead_count`, **not** `stale_count`.

- `stale_count` — данные старше своего порога (включая `stale_alive`, где агент жив и просто нет новостей). Информационный.
- `dead_count` — агенты, **не вышедшие на связь** (heartbeat протух/отсутствует), НЕЗАВИСИМО от возраста их данных: `dead` + `stale_dead`.
- `overall: "degraded"` — только при `dead_count > 0`.
- `heartbeat_dead_count` — back-compat алиас `dead_count` (историческое поле, то же число).

**Почему изменено (15.07.2026):** раньше `dead_count` считал только `stale_dead`,
т.е. требовал, чтобы данные ТОЖЕ успели протухнуть. Флот, лежавший 19ч на
протухшем OAuth, показывал в баннере «1 агент не на связи» вместо десяти —
данные были в пределах порогов 18–36ч. Плюс `fuel-state.json` пишут два агента
(`npz-status` и `fuel-market`): живой `fuel-market` бампал `generated_at` и
маскировал мёртвый `npz-status`. Баннер (`app.js:589`) печатает `dead_count`
и подписан «не на связи» — теперь смысл поля совпадает с подписью.

## Heartbeat Freshness Window

**Per-agent, ≈2× cron-интервала + буфер** (таблица `WATCH` в `agents/healthcheck.py`).

Глобальные **72ч** убраны 15.07.2026. Их обоснование — «agents run at most daily
(forecast is weekly)» — устарело: в crontab давно 6-часовые рутины
(`0,6,12,18`), `fuel-availability` `*/4`, `fuel-voices` `*/8`, radar `*/10мин`, а
`forecast`/`economy` бегают **ежедневно** (03:30/04:30), а не раз в неделю. 72ч
для 6-часового агента — это 12× интервала: авария становилась видна только через
трое суток.

| Агент | Cron | Окно |
|-|-|-|
| strikes / npz-status / history-crimea / roads / grid-status | `0,6,12,18` (6ч) | 15ч |
| fuel-availability | `*/4` | 10ч |
| fuel-voices | `*/8` | 20ч |
| radar-state | `*/10мин` | 2ч |
| forecast / economy | ежедневно 03:30 / 04:30 | 50ч |

🔴 **Держать в синхроне с crontab.** Меняешь расписание агента — меняй окно,
иначе watchdog либо слепнет, либо начнёт ложно краснеть.
Проверка логики: `python3 agents/healthcheck.py --selfcheck`.

## Files

| File | Modified by |
|-|-|
| `agents/healthcheck.py` | Healthcheck cron (reads heartbeats, writes health.json) |
| `data/heartbeats.json` | `run-agent.sh` (writes after each successful agent run) |
| `data/health.json` | Healthcheck output (consumed by frontend / Telegram bot) |
