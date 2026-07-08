# TODO

## 🎯 Goal
Повторить радар-карту как на **radar-map.ru** (движение БПЛА/ракет по регионам), но видоизменить под себя — и сделать это **малой кровью** (без бэкенда/БД/кронов).

Живой репозиторий: `~/Documents/npz-tactical-map` (НЕ `Alarm NPZ/`). Правим и деплоим только его.

**Ключевой факт:** апстрим `radar-map.ru/api/state` уже считает всю логику появления/затухания
(`bpla`=активен, `bplaDim`=затухает, нет в выдаче=исчез, `last_event_ts`, `bpla_icon_fade_sec`).
Своё ничего писать не надо — только прокинуть и красиво отрисовать.

## Active
- **fable5-main** | task-1..4 (radar revamp v1.5.0) | api/radar-state.js + radar.html | субагенты: proxy (Task 1), icon design (Task 2); main: Tasks 3-4 + интеграция

## Pending

## Completed (in progress → SHA после релиза)
- [ ] Task 1: Прокинуть в `api/radar-state.js` отброшенные поля апстрима — `recent_messages`, `sources`, `direction_arrows`, `bpla_icon_fade_sec`
- [ ] Task 2: Заменить треугольники в `ICON_SVGS` (radar.html) на силуэты-модельки. Яркость: `bpla`→opacity 1, `bplaDim`→0.45 с CSS-transition
- [ ] Task 3: Светлая/тёмная тема — кнопка ☀/🌙, `[data-theme=light]` + тайлы `dark_all`↔`voyager`, localStorage, дефолт светлая
- [ ] Task 4: Лента справа из `recent_messages` (канал · время МСК · текст)

## Completed
<!-- format: - [x] Task N: description (SHA: abc1234, YYYY-MM-DD) -->
