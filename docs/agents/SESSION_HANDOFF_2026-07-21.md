# Handoff — npz-tactical-map (наличие топлива на АЗС) — 2026-07-21

Тактическая карта РФ (удары/тревоги + слой АЗС). Фича: «реальное наличие топлива на АЗС» — краудсорс-виджет «Я тут». Главная цель: дать реальную ситуацию наличия топлива на АЗС, НЕ став паразитом на конкуренте gdebenz.ru и не подорвав доверие.

🔴 Живой репозиторий — ТОЛЬКО `~/Documents/npz-tactical-map` (копия в `~/Documents/Alarm NPZ` устарела). Анон-аккаунт GitHub `volobuevaleksand7-hue`.

## Статус
Ц0, Ц1, Ц2, Ц3/Ц5 (слияние) сделаны и проверены end-to-end в скрытой песочнице `/karta-azs-lab` (noindex+robots); прод `/karta-azs` НЕ тронут. Следующий шаг — промоушен в прод по ТЗ §9.

## Читать первым
1. `docs/agents/tz-fuel-availability-2026-07.md` — ТЗ: статус по подцелям Ц0–Ц7, §3 структура источников, §4.5 слияние, §9 план промоушена
2. `azs-lab.js` — вся lab-логика виджета
3. `karta-azs-lab.html` — shim (`L.map("mapAzs")` → `window.__azsMap`) + noindex
4. `api/azs-votes.js` — бэкенд (serverless REST к Upstash Redis)
5. Память: `npz-azs-votes-backend.md`, `gdebenzin-competitor-fake-statuses.md`

## Сделано и живёт
- **Ц0 Песочница** — `/karta-azs-lab` (noindex+robots), вся новая логика в `azs-lab.js` поверх нетронутого `app.js`. Хук: shim в `karta-azs-lab.html` ловит `L.map("mapAzs")` → `window.__azsMap` → popupopen → `marker._azs.id`.
- **Ц1 Виджет «Я тут»** — кнопки Есть/Нет/Очередь/Лимит в попапе, отметка device-local (localStorage) + анонимный cid.
- **Ц2 Общий бэкенд** — `api/azs-votes.js` (serverless REST к Upstash Redis, без зависимостей). POST отметка / GET агрегат. Env Vercel (Production+Preview): 🔴 `KV_REST_API_URL` / `KV_REST_API_TOKEN` (НЕ `UPSTASH_*`). База `upstash-kv-coquelicot-pillar` (Free, Frankfurt) через Vercel Marketplace, аккаунт sergeyramas' projects. Модель: hash `av:{id}` cid→{s,t}, TTL 24ч, окно агрегата 6ч, анти-спам 1/cid/станцию/30с, IP не логируем.
- **Ц3/Ц5 Слияние (ТЗ §4.5) — ПОЛНОСТЬЮ в песочнице**: сервер взвешивает отметки по свежести (свежее «нет» бьёт старое «есть») + confidence/top_share. Виджет: вердикт «⛽ Сейчас: X — по отметкам водителей», когда живое чисто бьёт регион-оценку (пороги MIN_VOTES=1 / CONF_MIN=0.3 / NEAR_TIE=0.6), «⚠️ расходятся» при near-tie. Перекраска маркеров: чистая победа → live-цвет + гало-кольцо (провенанс на карте), near-tie/протухло → откат на регион-иконку; батч-fetch по вьюпорту на move/zoom; рубильник (API упал → регион-цвет).

## Структура источников данных АЗС (ТЗ §3)
1. OSM `data/azs-stations.json` — 9609 точек, расположение.
2. Старые OSINT регион/сеть — `data/fuel-availability.json` (88 регионов, красит маркеры) + `data/fuel-voices.json` (голоса, агент читает публичный TG через t.me/s/ + WebSearch/СМИ).
3. Новое — живые per-station отметки «Я тут».
4. Планируется Ц6 — TG-чаты автоматом через `collect.py`.

gdebenz — НЕ источник (решение зафиксировано).

## Решения (не переигрывать)
- НЕ bulk-скрейпить gdebenz.ru (ToS запрещает автоскрейп + DDoS-Guard + SPOF + репутация).
- Свой краудсорс первичен, внешние источники — только отключаемые леса.
- Порядок реализации: сначала device-local, потом общий бэкенд, потом слияние — всё сделано.

## Грабли
- Фронт-правки ТОЛЬКО из чистого git worktree на origin/main (дерево Мака хард-ресетится фоновым git-sync). Пуш: `git push "https://x-access-token:$(gh auth token -u volobuevaleksand7-hue)@github.com/volobuevaleksand7-hue/npz-tactical-map.git" HEAD:main`. `gh auth switch` ЗАПРЕЩЁН. После правки JS — бампать `?v=`.
- В коде виджета НЕ звать `popup.update()` (стирает виджет) — только `reflow()`.
- Тест карты АЗС: контейнер `mapAzs` кэширует нулевой размер → `map.invalidateSize({animate:false})` (НЕ `invalidateSize(true)`) + `window.dispatchEvent(new Event('resize'))`; станции при мелком зуме в кластерах — брать `grp.getLayers().filter(_azs && _icon)`.
- Serverless-функцию локально не проверить (нужен Vercel + env) — тест деплоем на живой сайт. Self-check логики: `node api/azs-votes.js`.
- 🔴 В репо параллельно работают ДРУГИЕ сессии/чаты (свой dev-сервер в основном дереве) — отсюда изоляция через worktree обязательна; читать файл в worktree перед правкой.
- Тестовые отметки на реальных станциях Москвы (`osm-527768764`, `osm-253317552`) самоистекают (6ч показ / 24ч TTL).

## Что дальше (промоушен первым)
1. **Промоушен в прод `/karta-azs`** (детальный план — ТЗ §9). Кратко: overlay в песочнице самодостаточен → вынести shim + скрипт (убрать LAB-бейдж, `azs-lab.js` → `azs-live.js`) на прод-страницу минимальным диффом.
2. 🔴 ДО прода обязательно: клиентский кэш агрегатов — сейчас `recolorVisible` жжёт Upstash на каждый `moveend` (1 вьюпорт ≈ 50 команд, free-лимит ~10k/день).
3. После прода пойдут реальные люди → **Ц4**: graduation-метрики.
4. **Ц6** — мультиисточник: TG-чаты автоматом через `collect.py`.
5. **Ц7** — рост: share-текст, watchlist, SEO-сетка, антискам-статья, CloudTips.
6. Отдельная чип-задача: UTM-баг — `/karta-azs?utm=…` открывает вкладку «Россия» вместо АЗС; фикс `if(!location.hash)history.replaceState(null,"",location.search+"#azs")` в `karta-azs.html`.

## First message
```
Продолжаю npz-tactical-map — фичу «реальное наличие топлива на АЗС» (краудсорс-виджет «Я тут»). Не начинай пока не скажу.

🔴 Живой репо — ТОЛЬКО ~/Documents/npz-tactical-map (копия в Alarm NPZ устарела). Фронт-правки только из чистого git worktree на origin/main, пуш анон-токеном volobuevaleksand7-hue, gh auth switch запрещён.

Прочитай по порядку:
1. docs/agents/SESSION_HANDOFF_2026-07-21.md — этот хэндоф
2. docs/agents/tz-fuel-availability-2026-07.md — ТЗ (статус Ц0–Ц7, §3 источники, §4.5 слияние, §9 план промоушена)
3. Память: npz-azs-votes-backend.md, gdebenzin-competitor-fake-statuses.md

Ц0–Ц3/Ц5 сделаны и живут в песочнице /karta-azs-lab, прод /karta-azs не тронут. Первый шаг — промоушен в прод по §9: НАЧАТЬ с клиентского кэша агрегатов (сейчас recolorVisible жжёт Upstash на каждый moveend), затем перенести shim+скрипт на прод минимальным диффом.

Жди мою команду.
```
