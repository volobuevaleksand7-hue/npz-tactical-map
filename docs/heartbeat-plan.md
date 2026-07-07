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

| Status | Data age | Heartbeat age | Meaning | Alert? |
|-|-|-|-|-|
| `ok` | within threshold | any | Data fresh | No |
| `stale_alive` | over threshold | within 72h | Agent ran, no new data | **No** (suppress alert) |
| `stale_dead` | over threshold | >72h or missing | Agent likely dead | **Yes** |
| `unknown` | no `generated_at` | any | Cannot determine data age | No |

## Thresholds (unchanged)

No changes to WATCH thresholds in this iteration. Proposals below for future consideration:

- `fuel-availability.json`: 12h is tight for a bi-daily agent; consider raising to 18h.
- `forecast.json` / `economy.json`: 200h (8.3 days) is appropriate for weekly forecast agents.
- `roads.json`: 48h is generous; consider tightening to 36h.

## Alert Keying

The Telegram alert should key off `dead_count`, **not** `stale_count`.

- `stale_count` includes `stale_alive` agents that are working fine but produced no new data.
- `dead_count` only counts `stale_dead` agents that haven't checked in within the heartbeat window.
- `overall: "degraded"` is set only when `dead_count > 0`.

## Heartbeat Freshness Window

**72 hours** (`HEARTBEAT_FRESHNESS_HOURS = 72`).

Rationale: agents run at most daily (forecast is weekly). 72h covers 3 missed daily runs or
a full week's slack for forecast, with margin for VPS downtime or cron delays.

## Files

| File | Modified by |
|-|-|
| `agents/healthcheck.py` | Healthcheck cron (reads heartbeats, writes health.json) |
| `data/heartbeats.json` | `run-agent.sh` (writes after each successful agent run) |
| `data/health.json` | Healthcheck output (consumed by frontend / Telegram bot) |
