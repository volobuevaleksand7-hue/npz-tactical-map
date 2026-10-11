# agents/world — конвейер /lab/world

Только stdlib Python 3. Корень репозитория — рабочий каталог.

## Последовательность

События (3 раза в сутки):
1. `agents/run-agent.sh agents/update-prompt-world-events.md world-events` — Haiku-разведчик дописывает кандидатов в `data/world/events-queue.json`.
2. `python3 agents/world/validate-events.py` — схема, URL, лексика, дедуп, правило двух издателей; пишет `checks`, `verdict` (`ready|needs_source|rejected`), `reject_reason`.
3. `python3 agents/world/notify.py` — одно сообщение владельцу со всеми `ready`, ещё не отправленными (макс. 8), ставит `notified_at`.
4. Решение владельца: `python3 agents/world/approve.py <id> [<id>...] [--reject <id>...] [--force]`.

Ряды и индекс (каждые 6 ч):
`collect.py` → `index.py` → `watch.py --notify`.

## Опции
- `validate-events.py [--dry] [--queue P] [--events P] [--no-net] [--workers 4] [--timeout 10]`. Сеть недоступна: `urls_alive: "unknown"`, не reject. Мёртвый URL (HTTP 4xx/5xx) → reject. `confirmed` без двух независимых издателей у strike/seizure/attack_shipping → понижается до `reported`, verdict `needs_source`.
- `notify.py [--dry-run] [--queue P] [--max 8]`.
- `approve.py`: не-`ready` без `--force` не переносится; событие получает `review:"approved"`, `approved_at`; `events.json` сортируется по `occurred_at` убыв.
- `watch.py [--dry-run] [--notify] [--data DIR] [--state P]`: JSON в stdout, код 2 при проблемах. `--notify`: не чаще раза в 6 ч на тот же набор; состояние `data/world/.watch-state.json`; напоминание о `ready` без решения >48 ч — раз в сутки. В `incidents.md` не пишет.

## Окружение
- `NPZ_BOT_TOKEN` (иначе `~/.npz-bot/token`), `NPZ_OWNER_CHAT` (по умолчанию 609952529). Без токена notify/watch печатают предупреждение и ничего не шлют.

## Форматы
Схема кандидата и events.json — `docs/world-lab-spec.md`. Типы: strike, attack_shipping, seizure, outage, stocks_release, opec, sanctions, shortage, naval, other. Служебные поля очереди: `found_at`, `agent`, `checks`, `verdict`, `reject_reason`, `notified_at`, `decided_at`. Все записи JSON — атомарно (tmp + `os.replace`), общий код в `_common.py`.

## Тесты
`python3 -m unittest tests.world.test_pipeline` (без сети).
