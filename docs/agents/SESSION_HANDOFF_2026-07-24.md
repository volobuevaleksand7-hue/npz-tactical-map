# Handoff — npz-tactical-map — 2026-07-24

## Status
WB-кластер (3 страницы + удары 22.07) из чата 22.07 полностью **на проде**: файлы на `origin/main`, в `data/seo-topics.jsonl`, удары Краснодар/Невинномысск в `strikes.json`. Мой коммит вмёржен параллельной сессией (`715586d3`), поверх добавлен слой карты «Склады ВБ/Озон» (`79f73642`). Открытых правок от меня нет — дерево чистое.

## Что живёт (проверять, не переписывать)
- `/ataki-na-sklady-wildberries-hronika` (reference) — растущий реестр эпизодов. 🔴 новые удары по складам маркетплейсов — СЮДА, не новой страницей.
- `/kompensacii-wildberries-posle-udara` (reference) — денежный интент; суммы по СМИ + дисклеймер «не юрконсультация». При уточнении выплат правь цифры И дисклеймер.
- `/raketnaya-opasnost-tambovskaya-oblast` — генерится `agents/gen-rocket-danger.py` (запись в `CITIES`), не руками.

## Read first (in order)
1. `AGENT_ACTIVITY.md` — запись 2026-07-22 (детали кластера) + разведение зон
2. `docs/seo-playbook.md` — регламент страниц (реестр → страница → build-nav → check-ia)
3. `CLAUDE.md` + auto-memory — git-гигиена (анон-аккаунт, `gh auth switch` запрещён)

## In-session decisions
- **Тип `/kompensacii-*` = reference, не explainer:** `explainer` в `build-nav.py` уводит в группу «Топливо», а тема не топливная → место кластера WB в «Справочниках».

## Next step
Замер: страницы созданы 22.07, Вебмастер отдаёт с задержкой ~2 сут → к 24–25.07 могут появиться позиции. Снять срез по кластеру «wildberries удар/склад/компенсации» через API Вебмастера, решить нужны ли реопты. НЕ трогать до замера.

## First message
```
Продолжаю npz-tactical-map (кластер по ударам о складам Wildberries). Не начинай пока не скажу.

Прочитай:
1. `docs/agents/SESSION_HANDOFF_2026-07-24.md`
2. `AGENT_ACTIVITY.md` (запись 2026-07-22)
3. `docs/seo-playbook.md`

🔴 Перед любой правкой: `git log --oneline -8` (сверить с параллельными сессиями), правки фронта — только с `ALLOW_FRONTEND_RELEASE=1`, push — точечным `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue)`.

Затем жди мою команду.
```
