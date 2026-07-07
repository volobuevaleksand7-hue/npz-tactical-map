# NPZ Tactical Map — Архитектура оркестратора (Hermes)

## 🎯 Принцип работы

### Модель: Независимые агенты + Watchdog

Вместо цепочки «агент A → агент B → агент C» используем модель **независимых агентов с централизованным мониторингом**:

```
┌─────────────────────────────────────────────────────────────┐
│  Cron Scheduler (Hermes)                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │STRIKES  │ │NPZ-STAT │ │MARKET   │ │VOICES   │  ...      │
│  │08:00    │ │08:05    │ │08:15    │ │08:41    │          │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘          │
│       │           │           │           │                │
│       ▼           ▼           ▼           ▼                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ data/*.json + heartbeats.json                       │    │
│  │ (каждый агент пишет свой файл + heartbeat)          │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ WATCHDOG (каждый час)                               │    │
│  │ - Проверяет heartbeats.json                         │    │
│  │ - Если агент мёртв → алерт в Telegram              │    │
│  │ - Если всё ОК → молчит                              │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 📊 Таблица агентов

| # | Агент | Файл | Частота | Модель | Статус |
|---|---|---|---|---|---|
| 1 | STRIKES | strikes.json | 3×/день | mimo-auto:free | ✅ Активен |
| 2 | NPZ-STATUS | fuel-state.json | 3×/день | mimo-auto:free | ✅ Активен |
| 3 | FUEL-MARKET | fuel-state.json | 3×/день | mimo-auto:free | ✅ Активен |
| 4 | NEWSWATCH | strikes.json | каждый час | mimo-auto:free | ✅ Активен |
| 5 | FUEL-VOICES | fuel-voices.json | 8ч | mimo-auto:free | ✅ Активен |
| 6 | WATCHDOG | health.json | каждый час | Python | ✅ Активен |
| 7 | HISTORY-CRIMEA | history-crimea.json | 6ч | mimo-auto:free | ⏳ Этап2 |
| 8 | ROADS | roads.json | 6ч | mimo-auto:free | ⏳ Этап2 |
| 9 | GRID-STATUS | grid-state.json | 6ч | mimo-auto:free | ⏳ Этап2 |
| 10 | FUEL-AVAILABILITY | fuel-availability.json | 4ч | mimo-auto:free | ⏳ Этап2 |
| 11 | FORECAST | forecast.json | вс 03:45 | mimo-v2.5-pro | ⏳ Этап3 |
| 12 | ECONOMY | economy.json | ср 03:45 | mimo-v2.5-pro | ⏳ Этап3 |
| 13 | STRIKE-CONFIRM | strike-confirm.json | 6ч | Python | ⏳ Этап3 |
| 14 | COVERS | assets/cover-*.png | по событию | codex | ⏳ Этап3 |

## 🔄 Ротация моделей (Fallback)

Если основная модель недоступна, Hermes автоматически переключается на следующую:

```
Приоритет1: mimo-auto:free (Xiaomi)
Приоритет2: openai/gpt-oss-20b:free (OpenRouter)
Приоритет3: cohere/north-mini-code:free (OpenRouter)
Приоритет4: google/gemma-4-26b-a4b-it:free (OpenRouter)
Приоритет5: nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
Приоритет6: poolside/laguna-xs-2.1:free
```

**Для сложных задач (forecast/economy):**
```
Приоритет1: mimo-v2.5-pro (Xiaomi)
Приоритет2: deepseek-v4-pro (DeepSeek)
```

**Для ревью и генерации картинок:**
```
codex (OpenAI)
```

## 🚨 Срочные оповещения (NEWSWATCH)

NEWSWATCH запускается каждый час и проверяет новые удары. Если находит:

1. Обновляет strikes.json
2. Отправляет алерт в Telegram с кнопками:
   - ✅ Опубликовать
   - ✏️ Править
   - ❌ Отклонить

**Взаимодействие:**
- Алерт приходит в бот Hermes
- Вы нажимаете кнопку → я создаю пост
- Пост публикуется в Telegram + на сайт

## 🏥 WATCHDOG (мониторинг)

WATCHDOG запускается каждый час и проверяет:

1. **heartbeats.json** — когда каждый агент последний раз работал
2. **health.json** — общее состояние системы

**Если агент мёртв:**
```
🚨 WATCHDOG ALERT: Агент STRIKES мёртв!
Последнее обновление: 2026-07-05T17:48Z
Возраст: 12 часов
Действие: Проверить логи agents/logs/strikes.log
```

**Если всё ОК:**
- Молчит (не спамит)

## 📝 Логика heartbeat

Каждый агент после успешного выполнения пишет в `data/heartbeats.json`:

```json
{
  "strikes": "2026-07-06T04:35Z",
  "npz-status": "2026-07-06T04:41Z",
  "fuel-market": "2026-07-06T04:45Z",
  "fuel-voices": "2026-07-06T04:41Z"
}
```

WATCHDOG читает эти метки и сравнивает с текущим временем. Если разница больше порога (например, 12 часов для агентов, работающих 3×/день) → алерт.

## 🎨 Генерация обложек (Этап3)

Для генерации обложек новостных сводок:

1. **Источник:** news-archive.json ( лидер-удар дня)
2. **Генерация:** codex image_gen (gpt-image-2-medium)
3. **Подпись:** agents/caption_cover.py (Pillow)
4. **Результат:** assets/cover-<date>.png

**Расписание:** 2×/день (утро + вечер) или по событию.

## 📋 Текущий статус

### Активные cron jobs (6 шт):

1. **NPZ Morning Update** — 08:00 UTC (11:00 МСК)
2. **NPZ Afternoon Update** — 14:00 UTC (17:00 МСК)
3. **NPZ Evening Update** — 20:00 UTC (23:00 МСК)
4. **NPZ FUEL-VOICES** — каждые 8 часов
5. **NPZ WATCHDOG** — каждый час
6. **NPZ NEWSWATCH** — каждый час (дневное время)

### Модели:

- **Основная:** mimo-auto:free (Xiaomi)
- **Фолбэк:**10 бесплатных моделей (OpenRouter)
- **Сложные задачи:** mimo-v2.5-pro (Xiaomi)
- **Ревью/картинки:** codex (OpenAI)

### Доставка:

- **Все алерты** → Telegram bot Hermes (chat_id: 609952529)
- **Срочные удары** → с кнопками ✅/✏️/❌
- **Watchdog** → только при проблемах

## ❓ Открытые вопросы

1. **PUBLISH** — нужно адаптировать hermes/publish-vps.sh для Hermes (генерация /news + Telegram broadcast)
2. **COVERS** — настроить генерацию обложек через codex
3. **Этап2** — добавить агентов для HISTORY-CRIMEA, ROADS, GRID-STATUS, FUEL-AVAILABILITY
4. **Этап3** — добавить FORECAST, ECONOMY, STRIKE-CONFIRM

## 🚀 Следующие шаги

1. Протестировать WATCHDOG (проверить что алерты работают)
2. Протестировать NEWSWATCH (проверить что кнопки работают)
3. Настроить PUBLISH (генерация /news)
4. Добавить Этап2 агентов
5. Добавить Этап3 агентов
