# TODO

## 🎯 Goal
Повторить радар-карту как на **radar-map.ru** (движение БПЛА/ракет по регионам), но видоизменить под себя — и сделать это **малой кровью** (без бэкенда/БД/кронов).

Живой репозиторий: `~/Documents/npz-tactical-map` (НЕ `Alarm NPZ/`). Правим и деплоим только его.

**Ключевой факт:** апстрим `radar-map.ru/api/state` уже считает всю логику появления/затухания
(`bpla`=активен, `bplaDim`=затухает, нет в выдаче=исчез, `last_event_ts`, `bpla_icon_fade_sec`).
Своё ничего писать не надо — только прокинуть и красиво отрисовать.

## Active
(никто не работает)

## Pending

## Completed
- [x] Task 1: Прокинуты в `api/radar-state.js` поля апстрима — `recent_messages`, `sources`, `direction_arrows`, `bpla_icon_fade_sec` + `last_event_ts`/`source_text` городов (SHA: 2466829, 2026-07-08)
- [x] Task 2: SVG-модельки вместо треугольников + `safe`-точка; затухание `bplaDim`→opacity .45 (SHA: 2466829, 2026-07-08)
- [x] Task 3: Тема ☀/🌙 — voyager↔dark_all, localStorage, дефолт светлая, анти-FOUC (SHA: 2466829, 2026-07-08)
- [x] Task 4: Лента Telegram справа из `recent_messages`, 60 записей, на мобиле скрыта (SHA: 2466829, 2026-07-08)
- [x] Бонус-фикс: `toggleStrikesLayer` → `window` (чекбокс «Удары» кидал ReferenceError) (SHA: 2466829, 2026-07-08)
- [x] Task 5 (v1.5.1): ПВО полностью убрано с радара — юридический запрет. Вырезано во фронте + прокси (`delete r.pvo`) + фильтр ленты. ПРАВИЛО: не возвращать ПВО никогда (SHA: 07f42bb, 2026-07-08)

## Completed
<!-- format: - [x] Task N: description (SHA: abc1234, YYYY-MM-DD) -->
