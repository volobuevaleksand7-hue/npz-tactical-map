# Handoff — npz-tactical-map — 2026-06-15

## Status
Прод https://npz-tactical-map.vercel.app живёт, 4 cron-агента крутятся (npz-data / fuel-availability / fuel-voices / grid-status), 5 слоёв на карте, страница `/sources`. Все работы из сессии задеплоены, рабочее дерево чистое.

## Read first (in order)
1. `CLAUDE.md` — identity проекта + правила работы
2. `AGENT_ACTIVITY.md` — лог координации
3. `agents/update-prompt-*.md` — 6 промптов агентов (strikes, npz, market, history, roads, availability, voices, grid)
4. `data/*.json` — текущие данные (живые, обновляются cron'ом)
5. `app.js`, `index.html`, `styles.css` — фронтенд (всё в корне, без сборки)

## Active scheduled-tasks
- `npz-data-sync` (`0 */6 * * *`) — strikes / fuel-state / history / roads
- `fuel-availability-sync` (`15 */4 * * *`) — АЗС, сети, лимиты, цены
- `fuel-voices-sync` (`30 */8 * * *`) — голоса людей, есть ротация STALE-регионов и TTL 21 день
- `grid-status-sync` (`45 */6 * * *`) — подстанции, ТЭС, блэкауты

Управление: `~/.claude/scheduled-tasks/<id>/SKILL.md`.

## In-session decisions
- **Strike-фильтры pre-set:** добавлены `Сегодня / Неделя (default) / Месяц / Все` + slider для одного дня. Состояние через `SK.mode`. (rejected: timeline-only — было видно мало контекста)
- **АЗС цветовой градиент:** чистый зелёный→лайм→жёлтый→оранжевый→красный (calm/strained/limited/severe/critical). (rejected: старая палитра с золотистым strained — выглядела неотличимо от limited)
- **Voices rotation:** агент сам ищет STALE-регионы (>5 дней без цитат) и доливает свежие; записи >21 дня удаляются. (rejected: фиксированный seed без TTL — старые цитаты застаивались)
- **Деплой:** GitHub auto-deploy НЕ работает — после каждого push нужен `npx vercel --prod` вручную. cron-агенты тоже не пушат деплой, только данные (карта читает `data/*.json` напрямую с GitHub raw).

## Next step
Открыть прод, проверить что следующий cron (`09:17 UTC = 12:17 MSK` fuel-availability) отработал без ошибок. Или ждать запрос от Серёги.

## First message
```
Продолжаю npz-tactical-map. Не начинай пока не скажу.

Прочитай:
1. `~/Documents/npz-tactical-map/docs/agents/SESSION_HANDOFF_2026-06-15.md`
2. `~/Documents/npz-tactical-map/CLAUDE.md`

Затем жди мою команду.
```
