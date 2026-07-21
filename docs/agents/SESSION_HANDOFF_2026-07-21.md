# Handoff — npz-tactical-map (наличие топлива на АЗС) — 2026-07-21

## Статус
Ц0–Ц2 сделаны и проверены end-to-end (песочница, виджет «Я тут» device-local, общий бэкенд Upstash). Дальше — Ц4: обкатка на живых людях.

## Читать первым
1. `docs/agents/tz-fuel-availability-2026-07.md` — ТЗ, статус по подцелям Ц0–Ц7
2. `azs-lab.js` — вся lab-логика виджета
3. `karta-azs-lab.html` — shim (`L.map("mapAzs")` → `window.__azsMap`) + noindex
4. `api/azs-votes.js` — бэкенд (serverless REST к Upstash Redis)
5. Память: `npz-azs-votes-backend.md`, `gdebenzin-competitor-fake-statuses.md`

## Проект и цель
Тактическая карта РФ (удары/тревоги + слой АЗС). Фича: краудсорс-виджет «Я тут» — реальное наличие топлива на АЗС. Цель: дать пользователю реальную ситуацию, НЕ став паразитом на конкуренте gdebenz.ru и не подорвав доверие.

🔴 Живой репозиторий — ТОЛЬКО `~/Documents/npz-tactical-map` (копия в `~/Documents/Alarm NPZ` устарела). Анон-аккаунт GitHub `volobuevaleksand7-hue`.

## Сделано и живёт (проверено end-to-end)
- **Ц0 Песочница** — скрытая `/karta-azs-lab` (noindex + robots Disallow), копия `/karta-azs`. Вся новая логика в `azs-lab.js` поверх нетронутого `app.js`.
- **Ц1 Виджет v1 (device-local)** — Есть/Нет/Очередь/Лимит в попапе станции, localStorage по station.id, возраст словами, TTL 3ч.
- **Ц2 Общий бэкенд (21.07)** — `api/azs-votes.js`, без зависимостей (стиль `api/radar-state.js`). POST `{station_id,status,cid}` / GET `?ids=`. Env в Vercel (Production+Preview): 🔴 `KV_REST_API_URL` / `KV_REST_API_TOKEN` (НЕ `UPSTASH_*`). База `upstash-kv-coquelicot-pillar` (Free, Frankfurt) через Vercel Marketplace, аккаунт sergeyramas' projects. Модель: hash `av:{station_id}` cid→{s,t}, TTL 24ч, окно агрегата 6ч, анти-спам 1/cid/станцию/30с, IP не логируем. Попап: «👥 За 6 ч: …» + «сообщения водителей, не гарантия»; рубильник — при ошибке API молча device-local (нет SPOF).

## Решения (не переигрывать)
- НЕ bulk-скрейпить gdebenz (ToS запрещает автоскрейп + DDoS-Guard + SPOF + репутация). Свой краудсорс первичен, внешние источники — только отключаемые леса.
- Порядок: сначала device-local v1, затем общий бэкенд (оба сделаны).

## Грабли
- Фронт-правки ТОЛЬКО из чистого git worktree на origin/main (дерево Мака хард-ресетится фоновым git-sync). Пуш: `git push "https://x-access-token:$(gh auth token -u volobuevaleksand7-hue)@github.com/volobuevaleksand7-hue/npz-tactical-map.git" HEAD:main`. `gh auth switch` ЗАПРЕЩЁН. После правки JS/CSS — бампать `?v=` (иначе Vercel отдаёт stale).
- НЕ звать `popup.update()` в виджете — стирает вставленный виджет (перерисовывает попап из исходной HTML-строки). Использовать `reflow()`.
- Карта вкладки АЗС кэширует нулевой размер — тест в браузере: `map.invalidateSize(true)` + markercluster `zoomToShowLayer(marker, cb)`, станции при зуме 3 склеены в кластеры.
- Serverless-функцию локально не проверить (нужен рантайм Vercel + env) — тестировать деплоем на живой сайт. Self-check логики: `node api/azs-votes.js`.
- Тестовые отметки записаны на реальную станцию `osm-253317552` — самоистекают (6ч показ / 24ч TTL).

## Что дальше
1. **Ц4** — обкатка на живых людях + graduation-метрики (доля первый-парти данных, уникальных репортёров/станцию, медианный возраст наблюдения, correction/conflict rate, мин. покрытие) + дедлайн — ДО подмешивания внешних источников.
2. Ц5 — промоушен из песочницы в прод `/karta-azs` (перенос логики в общий пул + `?v` cache-bust).
3. Ц6 — мультиисточник: публичные TG/MAX-чаты через `collect.py`/`sources.json`.
4. Ц7 — приёмы роста (share-текст, watchlist «Мои АЗС», SEO-сетка город×бренд×топливо, антискам-статья, CloudTips-донаты).
5. Отдельная чип-задача: UTM-баг — `/karta-azs?utm_source=…` открывает вкладку «Россия» вместо АЗС; фикс `if(!location.hash)history.replaceState(null,"",location.search+"#azs")` в `karta-azs.html`.

## First message
```
Продолжаю npz-tactical-map — фичу «реальное наличие топлива на АЗС» (краудсорс-виджет «Я тут»). Не начинай пока не скажу.

🔴 Живой репо — ТОЛЬКО ~/Documents/npz-tactical-map (копия в Alarm NPZ устарела). Фронт-правки только из чистого git worktree на origin/main, пуш анон-токеном volobuevaleksand7-hue, gh auth switch запрещён.

Прочитай по порядку:
1. docs/agents/SESSION_HANDOFF_2026-07-21.md — этот хэндоф
2. docs/agents/tz-fuel-availability-2026-07.md — ТЗ, статус Ц0–Ц7
3. Память: npz-azs-votes-backend.md, gdebenzin-competitor-fake-statuses.md

Ц0–Ц2 сделаны (песочница /karta-azs-lab, виджет device-local, общий бэкенд api/azs-votes.js на Upstash). Следующий шаг — Ц4: обкатка на живых людях + graduation-метрики, если Серёга не скажет иное. Жди команды.
```
