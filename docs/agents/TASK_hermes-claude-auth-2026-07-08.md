# ЗАДАЧА ГЕРМЕСУ — восстановить авторизацию `claude` на VPS (все data-агенты падают)

**Дата:** 2026-07-08 · **Приоритет:** высокий · **Автор диагностики:** оператор+Opus (read-only с Мака)

## Симптом
На сайте в панели «Национальный баланс» висит баннер «Мониторинг: N агент(ов) не на связи». `data/health.json` → `meta.overall: degraded`, `dead_count ≥ 1` (первым тригернулся `history-crimea`, дальше подтянутся остальные).

## Корень (это НЕ баг конкретного агента — системный)
На VPS у `claude` CLI **протух логин**. ВСЕ LLM-агенты сети Гермеса падают с `Not logged in · Please run /login`.

Пруфы (снято на VPS):
- `agents/logs/*.log` — последняя строка `Not logged in` во всех: `strikes, npz-status, fuel-market, fuel-voices, grid-status, roads, history-crimea, fuel-availability, economy, newswatch`.
- `run-agent.sh` при RC≠0 откатывает `data/` и **не пишет heartbeat** → watchdog видит `stale_dead` → баннер.
- `/root/.npz-agent.env`: строка `ANTHROPIC_API_KEY` **закомментирована** (заглушка с деплоя). Значит работало на OAuth `/login`, а его сессия истекла (`~/.claude/.credentials.json` нет).
- Данные частично держат python-сборщики (`strike-confirm.py`, `strike-candidates.py`) + коммиты, поэтому падение всплывает не сразу.

**Вывод «каждый раз одно и то же»:** OAuth-сессия `/login` на headless-сервере периодически протухает. Нужен способ авторизации, который НЕ истекает по сессии.

## Фикс (durable). Выбрать 1 из 2:
### Вариант 1 — токен подписки (бесплатно, рекомендуется)
1. ⚠️ Генерится НЕ на VPS (нужен браузер): на машине с активным логином (Мак оператора) → `claude setup-token` → долгоживущий `sk-ant-oat…` (~1 год).
2. На VPS в `/root/.npz-agent.env` (chmod 600): `export CLAUDE_CODE_OAUTH_TOKEN=<token>`. `ANTHROPIC_API_KEY` оставить закомментированной.

### Вариант 2 — API-ключ (платно, по токенам; для Haiku копейки)
1. console.anthropic.com → создать `sk-ant-…` (создаётся из любого браузера, не с VPS).
2. На VPS в `/root/.npz-agent.env`: раскомментировать/вписать `ANTHROPIC_API_KEY=sk-ant-…`.

## После установки ключа/токена — проверка и догон
3. Headless-тест: `. /root/.npz-agent.env && claude -p "ответь ok" --model claude-haiku-4-5-20251001 --permission-mode acceptEdits` → ответ без «Not logged in».
4. Догнать упавшие агенты вручную (не ждать крон): `agents/run-agent.sh <prompt> <label>` для `history-crimea, npz-status, fuel-market, grid-status, fuel-availability, forecast/economy, newswatch`.
5. `python3 agents/healthcheck.py` → `overall: healthy`, `dead_count: 0`. Затем `bash agents/git-sync.sh "health: recover claude auth"`.
6. Баннер на сайте исчезнет сам (фронт читает `data/health.json`).

## Прибрать (вторичное)
В корне репо на VPS лежат левые файлы не на своих местах (mtime 07-08): `exilenova.html`, `moskovskij-npz.html`, `radarrusiia.html`, `seo-topics.jsonl`. Найти, кто пишет их в корень (агент с неверным output-путём), убрать/переместить или в `.gitignore`.

## Критерий «готово»
`health.json overall=healthy` · баннер на сайте исчез · heartbeats всех агентов свежие.
