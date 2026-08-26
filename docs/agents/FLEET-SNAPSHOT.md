# Снимок планировщиков флота НПЗ

> Снят автоматически: `agents/fleet-snapshot.sh`. **Руками не править** —
> правки затрёт следующий прогон. Источник правды — сами планировщики.
>
> Снято: 2026-08-26T16:45Z на `server-rwe3ae`

## 1. crontab

```cron
PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/bin
NPZ_MIMO_TIMEOUT=420
NPZ_REPO=/root/npz-tactical-map
R=/root/npz-tactical-map/agents/run-agent.sh
LOG=/root/npz-tactical-map/agents/logs/cron.log
HAIKU=claude-haiku-4-5-20251001
OPUS=claude-opus-4-8
5  4,16 * * *  NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-npz.md      npz-status       >> $LOG 2>&1
15 4,16 * * *  NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-market.md   fuel-market      >> $LOG 2>&1
25 4,16 * * *  NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-history.md  history-crimea   >> $LOG 2>&1
35 4,16 * * *  NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-strikes.md  strikes          >> $LOG 2>&1
45 4,16 * * *  NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-roads.md    roads            >> $LOG 2>&1
51 4,16 * * *  NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-grid.md     grid-status      >> $LOG 2>&1
23 */4 * * *        NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-availability.md fuel-availability >> $LOG 2>&1; python3 $NPZ_REPO/agents/guard-availability-coverage.py --fix-worktree >> $LOG 2>&1
33 */6 * * *        cd $NPZ_REPO && python3 agents/strike-confirm.py >> $LOG 2>&1; bash agents/git-sync.sh "data(strike-confirm): $(date -u +\%Y-\%m-\%dT\%H:\%MZ)" >> $LOG 2>&1
55 4,16 * * *  bash $NPZ_REPO/hermes/publish-vps.sh >> $LOG 2>&1
0 * * * *           cd $NPZ_REPO && git pull --rebase --quiet 2>/dev/null; python3 agents/healthcheck.py >> $LOG 2>&1; bash agents/git-sync.sh "health: watchdog $(date -u +\%Y-\%m-\%dT\%H:\%MZ)" >> $LOG 2>&1
*/10 * * * * bash /root/npz-tactical-map/hermes/cron-radar-refresh.sh >> /root/npz-tactical-map/agents/logs/radar-state.log 2>&1
20 * * * *  cd $NPZ_REPO && python3 agents/strike-candidates.py >> $LOG 2>&1; bash agents/git-sync.sh "data(strike-candidates): $(date -u +\%Y-\%m-\%dT\%H:\%MZ)" >> $LOG 2>&1
0 */4 * * * bash /root/npz-tactical-map/hermes/bot/sub-report.sh >> /root/npz-tactical-map/agents/logs/bpla-bot.log 2>&1
0 17 * * *   /usr/bin/python3 /root/.hermes/scripts/metrika_summary.py >> /root/npz-tactical-map/agents/logs/metrika-summary.log 2>&1
15 5,17 * * * cd /root/npz-tactical-map && /usr/bin/python3 agents/summary-watchdog.py >> /root/npz-tactical-map/agents/logs/cron.log 2>&1
5 * * * *        cd $NPZ_REPO && python3 agents/collect.py >> $LOG 2>&1; bash agents/git-sync.sh "data(collect): $(date -u +\%Y-\%m-\%dT\%H:\%MZ)" >> $LOG 2>&1
30 3 * * *   NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-forecast.md forecast >> $LOG 2>&1
30 4 * * *   NPZ_MODEL=$HAIKU $R $NPZ_REPO/agents/update-prompt-economy.md economy >> $LOG 2>&1
38 2 * * *   cd $NPZ_REPO && python3 agents/position-tracker.py >> $LOG 2>&1; bash agents/git-sync.sh "data(position-tracker): $(date -u +\%Y-\%m-\%dT\%H:\%MZ)" >> $LOG 2>&1
7,27,47 * * * *     cd $NPZ_REPO && /usr/bin/python3 hermes/bot/strike_pipeline.py >> $LOG 2>&1
0 * * * * /usr/bin/python3 /root/itp-monitor/monitor.py >> /root/itp-monitor/run.log 2>&1
17 * * * * /usr/local/bin/reap-orphan-browsers
*/15 * * * * bash /root/npz-tactical-map/hermes/deadman-alert.sh >> /root/npz-tactical-map/agents/logs/deadman.log 2>&1
0 18 * * * cd /root/tg-recon && ./.venv/bin/python channel_report.py >> /root/npz-tactical-map/agents/logs/channel-report.log 2>&1
40 */6 * * *   bash $NPZ_REPO/agents/refresh-warehouses.sh >> $LOG 2>&1
25 3 * * *   python3 $NPZ_REPO/agents/build-search-index.py >> $LOG 2>&1
5,20,35,50 * * * * cd /root/tg-recon && export TG_DATA_DIR=/root/tg-recon/instances/personal && set -a && . $TG_DATA_DIR/.env && set +a && ./.venv/bin/python watch_site_reply.py >> /root/tg-recon/watch_site_reply.log 2>&1
*/20 * * * * cd /root/tg-recon && export TG_DATA_DIR=/root/tg-recon/instances/personal && set -a && . $TG_DATA_DIR/.env && set +a && ./.venv/bin/python nudge_oleg.py >> /root/tg-recon/nudge_oleg.log 2>&1
```

## 2. hermes cron (`/root/.hermes/cron/jobs.json`)

🔴 Эти задания НЕ видны ни в `crontab -l`, ни в syslog, ни в `cron.log`.

Живых: **11** из 29.

| вкл | расписание | имя | тип | модель | последний прогон |
|---|---|---|---|---|---|
| ✅ | `*/5 * * * *` | BPL Strike Alerts | script | — | 2026-08-26T16:45 ok |
| ✅ | `*/30 5-20 * * 1-5` | ITP Yandex Positions (logika-itp, НЕ npz) | script | deepseek-v4-flash | 2026-08-26T16:30 error |
| ✅ | `0 */4 * * *` | NPZ Agent Monitor | llm | deepseek-v4-flash | 2026-08-26T16:02 ok |
| ✅ | `0 7,19 * * *` | NPZ COVER GENERATION | llm | — | 2026-08-26T07:03 ok |
| ✅ | `0 17 * * *` | NPZ EVENING BRIEFING | script | — | 2026-08-25T17:00 ok |
| ✅ | `41 */8 * * *` | NPZ FUEL-VOICES | llm | deepseek-v4-flash | 2026-08-26T16:44 ok |
| ✅ | `0 5 * * *` | NPZ MORNING BRIEFING | script | — | 2026-08-26T05:01 ok |
| ✅ | `0 1,3,5,7,9,11,13,15,17,19,21,23 * * *` | NPZ NEWSWATCH | llm | deepseek-v4-flash | 2026-08-26T15:07 ok |
| ✅ | `30 8,14,20 * * *` | NPZ PUBLISH | script | — | 2026-08-26T14:31 ok |
| ✅ | `*/5 * * * *` | NPZ Strike Alerts | script | — | 2026-08-26T16:45 ok |
| ✅ | `0 */4 * * *` | NPZ WATCHDOG | script | deepseek-v4-flash | 2026-08-26T16:31 ok |
| — | `0 */2 * * *` | BPL Radar Digest | script | — | —  |
| — | `35 */2 * * *` | BPL Radar Digest | script | — | 2026-07-18T08:35 error |
| — | `*/5 * * * *` | BPL Strike Alerts | script | — | 2026-07-14T06:10 ok |
| — | `0 14 * * *` | NPZ Afternoon Update | llm | — | 2026-07-06T14:06 ok |
| — | `45 3 * * 3` | NPZ ECONOMY | llm | — | 2026-08-26T03:49 ok |
| — | `0 20 * * *` | NPZ Evening Update | llm | — | 2026-07-06T20:09 ok |
| — | `45 3 * * 0` | NPZ FORECAST | llm | — | 2026-08-23T05:41 ok |
| — | `30 */4 * * *` | NPZ FUEL-AVAILABILITY | llm | deepseek-v4-flash | 2026-08-26T12:33 ok |
| — | `25 1,7,13,19 * * *` | NPZ HISTORY-CRIMEA | llm | deepseek-v4-flash | 2026-08-26T13:27 ok |
| — | `0 */2 * * *` | NPZ Manual Digest | script | — | 2026-07-13T12:01 ok |
| — | `0 8 * * *` | NPZ Morning Update | llm | — | 2026-07-07T08:14 ok |
| — | `*/10 * * * *` | NPZ RADAR ALERTS | llm | — | 2026-07-14T05:32 ok |
| — | `*/5 * * * *` | NPZ RADAR FETCH | llm | — | 2026-07-18T08:10 ok |
| — | `30 */2 * * *` | NPZ Radar Digest | script | — | —  |
| — | `5 */2 * * *` | NPZ Radar Digest | script | — | 2026-07-18T08:05 error |
| — | `*/5 * * * *` | NPZ Strike Alerts | script | — | 2026-07-14T06:10 ok |
| — | `0 */4 * * *` | NPZ Subscriber Monitor | llm | — | 2026-07-13T08:05 ok |
| — | `*/30 * * * *` | NPZ Threat Digest | script | — | 2026-07-13T09:00 ok |

_Спящих (пауза/выключены): 18 — держат промпты, работы не делают._

## 3. systemd timers (не-ОС)

```
hermes-browser-reaper.timer
tg-recon@personal.timer
wiki-pull.timer
```
