# Handoff — npz-tactical-map — 2026-06-20

## Status
Карта дополнена (вкладка АЗС+поездки, 32 НПЗ, охват до Татарстана), мигрирована в облако (7 cloud-рутин 24/7), аудит данных + 4 фазы улучшений — ВСЁ внедрено и в проде. FIRMS+Gemini рабочие. Осталась 1 фронт-фича (визуализация strike-confirm) + наблюдение за первыми cron-файрами.

## Read first (in order)
1. `docs/agents/REVIEW_2026-06-22.md` — live-site review: trust, onboarding, OG image, mobile discoverability
2. `docs/data-audit-2026-06-20.md` — аудит + дорожная карта 4 фаз (что сделано/осталось)
3. auto-memory `project_npz_tactical_map.md` (инжектится сама) — вся инфра: 7 рутин + ID триггеров, токен, фикс fetch, FIRMS, gemini
4. `CLAUDE.md` — правила проекта

## In-session decisions (уже в auto-memory, не дублирую файлами)
- **Облако = claude.ai RemoteTrigger API** (НЕ локальные MCP scheduled-tasks). PAT `github_pat_11B6…` (fine-grained, write). Локальные Mac-рутины ОТКЛЮЧЕНЫ.
- **Фронт читает raw-CDN первым** (`fetchJsonPath(path, live)`), статика — бандлом. Код-изменения → нужен `vercel --prod`; данные — авто из raw.
- **Делегирование моделям:** Gemini + DeepSeek-Flash дёргать свободно; **Codex — только спросив** (лимит). См. `feedback_model_delegation.md`.

## Next step
Фронт-слой для `data/strike-confirm.json`: значок 🛰 «подтверждено спутником» на НПЗ/ударах (FIRMS высокий FRP + GDELT-новость). + проверить первые cron-файры watchdog (`13 */3`) и strike-confirm (`33 */6`).

## Open (опционально)
- ТАИФ-НК отдельным брендом в azs-stations (сейчас в «Прочие»); трип-коридор Москва→Казань.

## First message
```
Продолжаю проект npz-tactical-map (Топливный фронт РФ). Не начинай работу, пока не скажу.

Прочитай:
1. `~/Documents/npz-tactical-map/docs/agents/SESSION_HANDOFF_2026-06-20.md`
2. `~/Documents/npz-tactical-map/docs/agents/REVIEW_2026-06-22.md`
3. `~/Documents/npz-tactical-map/docs/data-audit-2026-06-20.md`

Контекст по инфраструктуре (7 cloud-рутин, токены, FIRMS, fetch-фикс, политика моделей) — в auto-memory, инжектится сам. Сверь актуальное состояние с `git log` и живыми данными перед утверждениями.

Жди мою команду.
```
