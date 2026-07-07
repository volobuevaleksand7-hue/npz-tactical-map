# npz-tactical-map — project memory

## Identity
Тактическая дашборд-карта состояния НПЗ РФ (удары/мощности/баланс/логистика/дефицит). Статический сайт на Vercel, данные в `data/fuel-state.json`, обновляются cron-агентами на VPS.

## Stack
- Frontend: vanilla HTML/CSS/JS + Leaflet 1.9 (CARTO dark tiles, без ключей). Без сборки.
- Data: единый `data/fuel-state.json` (схема: meta / national_balance / fuel_balance / refineries[] / export_terminals[] / pipelines[] / deficit_regions[] / events[]).
- Deploy: Vercel (framework = Other / static). Репо: github.com/volobuevaleksand7-hue/npz-tactical-map.
- Agents: VPS 193.28.186.23 cron, модель `claude-haiku-4-5-20251001`. См. `agents/`.

## Commands
- Локально: `python3 -m http.server 8080`
- Деплой: push в main → Vercel авто-редеплой
- Ручной прогон агента: `./agents/run-agent.sh agents/update-prompt-npz.md npz-status`

## Verification
- JSON валиден: `python3 -c "import json;json.load(open('data/fuel-state.json'))"`
- Карта грузится, маркеры зел/жёлт/красн, попапы открываются, тикер идёт, NEXT SYNC тикает.

## Guardrails
- Режим ОЦЕНКА — всегда показывать дисклеймер. Это OSINT, не официальные данные.
- Агенты меняют только status/даты/дефицит/события/meta. Координаты, названия, мощности — не трогать.
- Раннер валидирует JSON и откатывает при поломке до пуша.

## Data sources (seed)
Reuters (via liga.net), Meduza, Moscow Times, The Bell, Новая газета Европа, Euronews — см. source_url в JSON и ресёрч-отчёт от 2026-06-11.
