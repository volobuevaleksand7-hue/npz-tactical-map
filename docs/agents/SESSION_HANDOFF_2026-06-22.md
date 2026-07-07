# Handoff — npz-tactical-map — 2026-06-22

Проект живёт в `~/Documents/npz-tactical-map` (НЕ в cwd «Alarm NPZ»). Сайт читает `data/*.json` из GitHub raw.

## Status
Watchdog зелёный, агенты работают. За сессию: пересчитан national_balance, доделан heartbeat-механизм, проведён системный аудит, починены DeepSeek/MiMo CLI. Один прогон подвис (см. Next step).

## Read first (in order)
1. `docs/system-audit-2026-06-21.md` — полный аудит: что исправлено vs что осталось (SPOF, forecast-агент, og-image, счётчик «9 агентов»)
2. `CLAUDE.md` — правила проекта (OSINT, режим ОЦЕНКА, гайдрейлы)
3. `docs/cloud-routines-setup.md` — для разбивки cloud-SPOF на пер-датасетные рутины

## In-session decisions
- **national_balance считается из `refineries[]`, не вручную:** `capacity_offline_pct` = Σмощностей `down`/Σвсех; `throughput_shortfall_pct` = взвешено по `est_output_pct`. Прописано в `update-prompt-market.md`.
- **Кинеф** исправлен `down/0%`→`partial/30%` после верификации (3 из 4 CDU, одна цела). Итог headline = **26%**, не 32% (промежуточная 32% переоценивала Кинеф).
- **Локальный `npz-data-sync` оставлен включённым** как fallback — cloud-версия мертва с 19.06. Требует Mac в сети в 00/06/12/18 MSK.
- **DeepSeek-фикс:** в `~/.local/bin/deepseek` добавлен изолированный `CLAUDE_CONFIG_DIR` (иначе claude слал подписочный OAuth-токен → 401). MiMo рабочий, но медленный (агентный харнесс). Детали — в auto-memory.

## Next step
Проверить прогон `npz-data-sync` от 09:00Z (PID был 26089, висел ~27 мин в state S, без коммита — последний `data(routine)` = 03:05Z). Если так и не закоммитил — он подвис: убить и прогнать ручной добор strikes/npz/market/history. Из-за этого «скудные новости» 22.06.

## Не запускать ручной сбор, пока жив тот прогон — будет race за файлы и git push.

## First message
```
Продолжаю npz-tactical-map (~/Documents/npz-tactical-map). Не начинай пока не скажу.

Прочитай:
1. `docs/agents/SESSION_HANDOFF_2026-06-22.md`
2. `docs/system-audit-2026-06-21.md`

Затем проверь, закоммитил ли свежие новости прогон npz-data-sync от 09:00Z
(git log + ps -p 26089 + data/heartbeats.json). Доложи статус и жди мою команду.
```
