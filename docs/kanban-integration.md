# Kanban + Cron Jobs Integration

## Проблема

Воркеры Kanban не имеют нужных инструментов:
- Нет `web_search` (для поиска новостей)
- Нет `terminal` (для выполнения команд)
- Есть только `kanban_*` инструменты

## Решение

Использовать **cron jobs** для выполнения задач, а **Kanban** только для отслеживания статуса.

## Архитектура

```
Cron Job (Hermes session)
  ├─ web_search (поиск новостей)
  ├─ terminal (git pull/push)
  ├─ file (обновление JSON)
  └─ update-kanban.sh (обновление статуса)
       ↓
Kanban Board (визуальный трекинг)
```

## Как это работает

1. **Cron job запускается** по расписанию
2. **Агент выполняет задачу** (поиск новостей, обновление JSON)
3. **Агент обновляет Kanban** через `update-kanban.sh`
4. **Dashboard показывает статус** (running → completed)

## Интеграция

### В каждом cron job добавить:

```bash
# В начале (запуск)
hermes kanban comment <task_id> "Агент запущен, ищу новости..."

# После завершения
hermes kanban complete <task_id>

# При ошибке
hermes kanban block <task_id> "Ошибка: ..."
```

### Или использовать скрипт:

```bash
# Запуск
bash agents/update-kanban.sh t_ede6b9ba comment "STRIKES: запущен"

# Завершение
bash agents/update-kanban.sh t_ede6b9ba complete

# Блокировка
bash agents/update-kanban.sh t_ede6b9ba block "Ошибка: нет доступа к Telegram"
```

## Текущий статус

### Задачи в Kanban:

| Задача | Статус | Причина |
|---|---|---|
| STRIKES | ready | Воркер не имеет инструментов |
| NPZ-STATUS | ready | Воркер не имеет инструментов |
| FUEL-MARKET | ready | Воркер не имеет инструментов |
| NEWSWATCH | done | ✅ |
| FUEL-VOICES | done | ✅ |
| WATCHDOG | done | ✅ |
| HISTORY-CRIMEA | ready | Воркер не имеет инструментов |
| ROADS | done | ✅ |
| GRID-STATUS | ready | Воркер не имеет инструментов |
| FUEL-AVAILABILITY | done | ✅ |
| FORECAST | done | ✅ |
| ECONOMY | ready | Воркер не имеет инструментов |
| COVERS | done | ✅ |
| PUBLISH | done | ✅ |

### Cron jobs:

| Job | Статус | Следующий запуск |
|---|---|---|
| NPZ Morning Update | ✅ | 08:00 UTC |
| NPZ Afternoon Update | ✅ | 14:00 UTC |
| NPZ Evening Update | ✅ | 20:00 UTC |
| NPZ FUEL-VOICES | ✅ | каждые 8ч |
| NPZ WATCHDOG | ✅ | каждый час |
| NPZ NEWSWATCH | ✅ | каждый час (день) |
| NPZ COVER GENERATION | ✅ | 07:00, 19:00 UTC |

## Вывод

**Cron jobs работают и обновляют данные.** Kanban используется только для визуального отслеживания. Воркеры Kanban не нужны — их функцию выполняют cron jobs.
