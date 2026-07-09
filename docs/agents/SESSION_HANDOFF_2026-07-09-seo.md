# Handoff — npz-tactical-map — 2026-07-09 (SEO-линии + сводка + git-safety)

## Status
Выпущено/запланировано: реопт /radar (freshness), линия «ракетная опасность» (8 городов,
разовые scheduled-tasks), топливные /benzin-na-trasse+/gde-dizel (08:00 МСК), 3 НПЗ-черновика
(scheduled 12/13/14.07), обложки хаба /analytics (5 вписаны). Сводка /news/2026-07-09 выпущена
+ 2 root-cause фикса gen-news.py (schema drift ударов, выбор ЛИДА дня). Autostash-клоббер
устранён во всех 3 публикаторах + 12 задачах.

## 🔴 Read first (в этом порядке)
1. `HERMES.md` §0 — ПРОТОКОЛ КООРДИНАЦИИ (несколько агентов в одном репо)
2. `AGENT_ACTIVITY.md` — верх ## Log + зоны ответственности (застолбить намерение перед работой)
3. `CLAUDE.md` — правила проекта
4. `docs/agents/rocket-danger-pages.md` + `docs/agents/fuel-pages.md` — линии страниц
5. `data/seo-topics.jsonl` — реестр ключей (анти-каннибализация)

## 🔴 Критично — git-safety (иначе снесёшь чужую работу)
- Дерево Мака `~/Documents/npz-tactical-map` **загрязнено uncommitted правками параллельной
  сессии** — НЕ коммить из него. Публикуй из ЧИСТОГО КЛОНА origin (рецепт — в памяти
  `npz-git-sync-hard-reset-hazard` и я весь день так делал: `git clone --shared … ; reset --hard origin/main`).
- НИКОГДА `--autostash` / `git stash` / `reset --hard` (в общем дереве) / `git checkout .`.
- Публикаторы уже безопасны (commit-first + `git pull --rebase` без autostash).

## In-session decisions
- **Апдейты сводки в течение дня → зона Гермеса** (его рутина 10:00 МСК). Лезу только по слову владельца.
- **Даты сводок:** массовый налёт (Саратов/Уфа/Нижнекамск, 415 дронов) = ночь на **8.07** → /news/2026-07-08
  (15 ударов). Ночь на 9.07 тихая (73 дрона) → /news/2026-07-09 (2 удара, Тверь). НЕ путать/переносить.
- **Лид сводки** = самый значимый удар (НПЗ>энергетика>прочее, confirmed>reported), не первый в списке.
- **Сбор данных Гермеса** (LLM-коллекторы «Not logged in») выключен **намеренно** — переезд на Гермеса-only, НЕ баг.

## Next step
Косметика по желанию владельца: (1) склонение в авто-заголовках сводок («в Саратов»→«в Саратове»,
`gen-news.py::brief_headline`); (2) навигация ←пред/след день→ на сводках. Крупное: реопт
`/attacks`+`/refineries` (freshness + CTA на радар/новые НПЗ).

## Scheduled tasks (все безопасны)
Ракетные города: omsk/cheboksary(9.07), kazan/moskovskaya-oblast/penza/samara(10.07), ulyanovsk(16:00 9.07).
Топливные: npz-fuel-pages-morning-release (08:00 daily). НПЗ: npz-obj-{slavneft-yanos 12.07, kujbyshevskij 13.07, ryazanskij 14.07}.
Backup: npz-rocket-danger-morning-release (04:00 daily).

## First message
```
Продолжаю npz-tactical-map. Не начинай пока не скажу.

Прочитай по порядку:
1. `docs/agents/SESSION_HANDOFF_2026-07-09-seo.md`
2. `HERMES.md` §0 (протокол координации) + `AGENT_ACTIVITY.md` (верх ## Log)
3. `CLAUDE.md`

🔴 Git-safety: дерево Мака загрязнено чужими uncommitted правками — публикуй ТОЛЬКО из чистого
клона origin, НИКОГДА не гоняй `git pull --rebase --autostash` / `stash` / `reset --hard` в общем дереве.

Затем жди мою команду.
```
