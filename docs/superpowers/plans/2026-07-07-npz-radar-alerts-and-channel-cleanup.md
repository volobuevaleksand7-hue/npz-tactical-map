# NPZ Radar Alerts And Channel Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add subscriber-controlled BPLA/radar alerts and a safe dry-run workflow for cleaning old Telegram channel posts.

**Architecture:** Keep destructive channel cleanup behind an audit-only script. Add a separate `radar_alerts.py` engine for alert decisions, while `poll.py` only handles user commands and `radar_alerts.py --send` handles scheduled delivery.

**Tech Stack:** Python stdlib, Telegram Bot API, existing `~/.npz-bot/subscribers.json`, existing `data/radar-state.json`.

---

### Task 1: Channel Cleanup Audit

**Files:**
- Create: `hermes/bot/channel_cleanup_audit.py`
- Test: `hermes/bot/test_channel_cleanup_audit.py`

- [ ] Write tests that parse sample `t.me/s/NPZmap` HTML and classify candidates: English/mixed, duplicate, service/test, weak no-main posts.
- [ ] Implement read-only audit script. Default mode prints a Markdown table and never calls Telegram delete APIs.
- [ ] Add CLI args: `--html`, `--url`, `--json`, `--limit`.

### Task 2: Radar Alert Engine

**Files:**
- Create: `hermes/bot/radar_alerts.py`
- Test: `hermes/bot/test_radar_alerts.py`

- [ ] Write failing tests for region matching, "all regions", immediate new danger, interval reminder, and one-time all-clear.
- [ ] Implement subscriber alert settings: `alerts.enabled`, `alerts.regions`, `alerts.interval_min`.
- [ ] Implement alert state in `~/.npz-bot/radar-alert-state.json`.
- [ ] Add CLI: `--dry-run` and `--send`; dry-run is default.

### Task 3: Bot Commands

**Files:**
- Modify: `hermes/bot/poll.py`

- [ ] Add `/alerts`, `/alerts_off`, `/regions`, `/region <name|all>`, `/interval <30|60|changes>`.
- [ ] Keep `/radar` unchanged for manual status.
- [ ] Send concise help text after each setting change.

### Task 4: Publish/Scheduler Hook

**Files:**
- Modify: `hermes/publish-vps.sh`
- Modify: `hermes/crontab.hermes`

- [ ] Run `radar_alerts.py --send` from publish pipeline or document a Hermes routine every 10 minutes.
- [ ] Do not post channel cleanup deletes automatically.

### Verification

- `python3 -m unittest hermes.bot.test_channel_cleanup_audit hermes.bot.test_radar_alerts -v`
- `python3 -m py_compile hermes/bot/channel_cleanup_audit.py hermes/bot/radar_alerts.py hermes/bot/poll.py`
- `python3 hermes/bot/channel_cleanup_audit.py --html /tmp/sample.html`
- `NPZ_REPO=/root/npz-tactical-map NPZ_BOT_DIR=/tmp/npz-bot-test python3 hermes/bot/radar_alerts.py --dry-run`
