# Перенос 4 рутин: Local → Anthropic Cloud Agents

**Зачем:** локальные рутины не работают пока Mac спит. Cloud agents работают 24/7 на серверах Anthropic.

**Биллинг:** идёт по подписке Claude — как обычные сессии.

---

> ### 🔴 ВАЖНО — фикс битого `data/last-sync.txt` (конфликт-маркеры из remote)
>
> Раньше рутины делали `git pull --rebase --autostash` при грязном дереве и затем слепой
> `git add data/ && git commit && git push`. Несколько рутин одновременно трогают
> `last-sync.txt`/`heartbeats.json`, поэтому `git stash pop` от autostash конфликтовал и
> писал маркеры `<<<<<<< Updated upstream … >>>>>>> Stashed changes` ПРЯМО в трекаемый файл,
> который потом коммитился и уезжал на origin.
>
> **Исправление живёт в репо** и подхватывается при каждом `git clone`:
> - `agents/git-sync.sh` — единственная разрешённая точка коммита/пуша. Атомарно пишет
>   `last-sync.txt`, аборт при любых конфликт-маркерах в `data/`, пуш с rebase-ретраем **без
>   `--autostash`** (коммит делается ДО pull, дерево чистое → stash не запускается).
> - `.githooks/pre-commit` — guard, который `git-sync.sh` включает сам
>   (`git config core.hooksPath .githooks`); блокирует даже ручной `git commit` с маркерами.
>
> **Действие для уже развёрнутых Remote-агентов:** открыть каждый cloud-агент в `/schedule`
> и заменить шаг push на `bash agents/git-sync.sh "<label>(cloud): sync $(date -u +%Y-%m-%dT%H:%MZ)"`
> (как в блоках ниже). Запретить им `git add/commit/push`, `git stash`, `--autostash` вручную.

---

## Шаг 1. Создать 4 cloud-agent'a через `/schedule create`

Для каждого: `/schedule create` → **режим "Cloud" / "Remote"** (как ты уже делал для «NPZ карта — сбор данных») → вставить prompt и cron.

Repo: `https://github.com/volobuevaleksand7-hue/npz-tactical-map`. Все промпты ниже — самодостаточные: cloud не видит твоего Mac, поэтому каждый раз клонирует репо в `/tmp`, читает свежий промпт-файл из репо (`agents/update-prompt-*.md`), редактирует JSON и пушит.

> **Авторизация git push в Cloud.** Так как у тебя уже работает «NPZ карта — сбор данных (Remote)», значит способ есть. Если новый агент не сможет push'нуть на первом запуске — открой его SKILL и добавь `gh auth login --with-token <<< $GITHUB_PAT` или похожий способ, как у работающей рутины. Либо вытащи репо как **submodule с deploy-key** — у тебя есть `npz_deploy` (см. auto-memory про Hermes).

---

### 1️⃣ NPZ-DATA SYNC — каждые 6ч (`0 */6 * * *`)

**taskName:** `cloud-npz-data-sync`

```
Ты — автономная cloud-рутина обновления тактической карты «Топливный фронт РФ» (https://npz-tactical-map.vercel.app). Работай полностью сам, без вопросов.

РЕПО (cloud не видит локальный Mac — клонируй каждый раз):
- GitHub: https://github.com/volobuevaleksand7-hue/npz-tactical-map
- Работай в /tmp/npz-tactical-map

ПОРЯДОК ДЕЙСТВИЙ:
1. Подготовка:
   - rm -rf /tmp/npz-tactical-map
   - git clone https://github.com/volobuevaleksand7-hue/npz-tactical-map.git /tmp/npz-tactical-map
   - cd /tmp/npz-tactical-map
   - git config user.email "agent@npz-routine.local" && git config user.name "npz-routine-cloud"

2. Прочитай свежие промпт-спецификации из репо: agents/update-prompt-strikes.md, agents/update-prompt-npz.md, agents/update-prompt-market.md, agents/update-prompt-history.md, agents/update-prompt-roads.md. Прочитай текущие data-файлы (схемы и дедуп).

3. WebSearch свежих новостей за последние ~24 часа (рус+англ):
   - удары БПЛА/ракетами по российским городам и объектам (по дням, с временем);
   - статус НПЗ: удары, остановки, возобновления/ремонты;
   - дефицит топлива и АЗС-ограничения по регионам; Крым (талоны, Р-280/коридор);
   - дороги и топливная логистика, особенно коридор через Мариуполь.

4. Обнови строго по схеме (структуру и ключи НЕ менять):
   - data/strikes.json → новые удары {date,time,city,region,lat,lon,type,count,target,casualties,title,detail,source_url}, time обязательно. Не дублируй (дата+город). ≤110.
   - data/fuel-state.json → refineries[] (status/status_since/est_output_pct/damage/source_url), deficit_regions[], events[] (1–3 новых сверху, ≤10), meta.generated_at.
   - data/history-crimea.json → history[] (новые сверху, type strike|repair|restriction|policy, ≤24).
   - data/roads.json → roads[].status/note/source_url, hotspots[], generated_at.

5. ПРАВИЛА:
   - Если по теме нет подтверждённых новостей — НЕ трогай файл.
   - Каждое изменение — со ссылкой URL.
   - Нейтральные формулировки. Координаты/паспортные мощности НПЗ/geojson НЕ менять.

6. Валидация каждого изменённого файла:
   - python3 -c "import json;json.load(open('data/<file>.json'))"
   - Если ошибка — git checkout -- data/<file>.json (не коммить битый).

6b. HEARTBEAT (ОБЯЗАТЕЛЬНО, даже если новостей нет) — чтобы watchdog отличал «жив, нет новостей» от «мёртв»:
   python3 - <<'PY'
   import json, datetime
   now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
   p = "data/heartbeats.json"
   try: hb = json.load(open(p, encoding="utf-8"))
   except Exception: hb = {}
   for k in ("npz-status","fuel-market","history-crimea","strikes","roads"):
       hb[k] = now
   json.dump(hb, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
   print("heartbeat ->", now)
   PY

7. Push (heartbeats.json меняется каждый запуск → коммить ВСЕГДА):
   - bash agents/git-sync.sh "data(cloud): sync $(date -u +%Y-%m-%dT%H:%MZ)" "npz-status fuel-market history-crimea strikes roads"   # safe: atomic last-sync.txt, conflict-marker guard, rebase-retry WITHOUT --autostash; never call git add/commit/push or git stash manually

8. Кратко отчитайся: какие файлы обновил, сколько новых событий.

OSINT-агрегация публичных новостей. Только открытые источники.
```

**Cron:** `0 */6 * * *` (в 00/06/12/18 MSK)

---

### 2️⃣ FUEL-AVAILABILITY SYNC — каждые 4ч (`15 */4 * * *`)

**taskName:** `cloud-fuel-availability-sync`

```
Ты — автономная cloud-рутина FUEL-AVAILABILITY карты «Топливный фронт РФ» (https://npz-tactical-map.vercel.app). Работай полностью сам.

РЕПО: https://github.com/volobuevaleksand7-hue/npz-tactical-map → клонируй в /tmp/npz-tactical-map.

ПОРЯДОК:
1. Подготовка (как в npz-data-sync):
   - rm -rf /tmp/npz-tactical-map && git clone https://github.com/volobuevaleksand7-hue/npz-tactical-map.git /tmp/npz-tactical-map && cd /tmp/npz-tactical-map
   - git config user.email "agent@npz-routine.local" && git config user.name "npz-routine-cloud"

2. Прочитай спецификацию из репо: agents/update-prompt-availability.md (там ПОЛНАЯ инструкция — строго следуй ей, включая STALE-проход по регионам старше 7 дней). Прочитай текущий data/fuel-availability.json (схема + список регионов с updated).

3. Выполни инструкции из update-prompt-availability.md:
   - Инвентаризация STALE-регионов (updated > 7 дней).
   - 4–6 WebSearch по горячим темам + 1 поиск на КАЖДЫЙ STALE-регион.
   - Сети: Лукойл, Роснефть, Газпром нефть, Татнефть, Сургутнефтегаз, АТАН, ТЭС, Кубаньнефтепродукт, региональные малые.
   - У каждой сети ОБЯЗАТЕЛЬНО поле level из {calm,strained,limited,severe,critical} (нет данных по сети → ставь level региона).

4. Обнови data/fuel-availability.json через Write, строго по схеме. Если по региону нет новостей — не трогай.

5. Валидация: python3 -c "import json;json.load(open('data/fuel-availability.json'))". Битый файл — git checkout -- data/fuel-availability.json.

6b. HEARTBEAT (ОБЯЗАТЕЛЬНО каждый запуск, даже если данных нет):
   python3 - <<'PY'
   import json, datetime
   now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
   p = "data/heartbeats.json"
   try: hb = json.load(open(p, encoding="utf-8"))
   except Exception: hb = {}
   hb["fuel-availability"] = now
   json.dump(hb, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
   print("heartbeat ->", now)
   PY

7. Push:
   - bash agents/git-sync.sh "availability(cloud): sync $(date -u +%Y-%m-%dT%H:%MZ)" "fuel-availability"   # safe: atomic last-sync.txt, conflict-marker guard, rebase-retry WITHOUT --autostash; never call git add/commit/push or git stash manually

8. Кратко отчитайся: сколько регионов обновил (включая STALE-проход), сети, источники.

OSINT-агрегация. Только открытые источники.
```

**Cron:** `15 */4 * * *`

---

### 3️⃣ FUEL-VOICES SYNC — каждые 8ч (`30 */8 * * *`)

**taskName:** `cloud-fuel-voices-sync`

```
Ты — автономная cloud-рутина FUEL-VOICES карты «Топливный фронт РФ» (https://npz-tactical-map.vercel.app). Работай полностью сам.

РЕПО: https://github.com/volobuevaleksand7-hue/npz-tactical-map → клонируй в /tmp/npz-tactical-map.

ПОРЯДОК:
1. Подготовка (как в других рутинах):
   - rm -rf /tmp/npz-tactical-map && git clone https://github.com/volobuevaleksand7-hue/npz-tactical-map.git /tmp/npz-tactical-map && cd /tmp/npz-tactical-map
   - git config user.email "agent@npz-routine.local" && git config user.name "npz-routine-cloud"

2. Прочитай свежую спецификацию из репо: agents/update-prompt-voices.md (там ПОЛНАЯ инструкция). Прочитай текущий data/fuel-voices.json для дедупа и инвентаризации.

3. Выполни инструкции из update-prompt-voices.md. Сбор из ДВУХ каналов:
   - Telegram (приоритет, лаг 0–1 день): WebFetch на https://t.me/s/<channel> (без API/авторизации). Seed: bazabazon, shot_shot, ASTRApress, mash, bbbreaking. Бери только реплики/цитаты людей про бензин/АЗС/очереди за последние 3 дня. source="Telegram", source_url на конкретный пост.
   - Веб-поиск (8–12 WebSearch): горячие регионы + STALE-регионы (где последняя цитата >5 дней).

4. Обнови data/fuel-voices.json через Write:
   - Добавь 3–8 новых цитат СВЕРХУ. У каждой: date = реальная дата публикации, seen = СЕГОДНЯ UTC.
   - seen у старых записей НЕ трогать. Нет seen — проставь seen=date один раз.
   - Ротация: для STALE-регионов минимум 1 свежая цитата если нашёл.
   - TTL: удали записи где seen (или date) старше 21 дня.
   - Лимит ≤60. БЕЗ персональных данных. Без политики.
   - Поле city — каноническое имя (как в трассе М4: Москва, Воронеж, Ростов-на-Дону, Краснодар, Симферополь, Севастополь и т.д. — карта фильтрует по точному совпадению).

5. Валидация: python3 -c "import json;json.load(open('data/fuel-voices.json'))". Битый — git checkout -- data/fuel-voices.json.

6b. HEARTBEAT (ОБЯЗАТЕЛЬНО каждый запуск, даже если данных нет):
   python3 - <<'PY'
   import json, datetime
   now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
   p = "data/heartbeats.json"
   try: hb = json.load(open(p, encoding="utf-8"))
   except Exception: hb = {}
   hb["fuel-voices"] = now
   json.dump(hb, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
   print("heartbeat ->", now)
   PY

7. Push:
   - bash agents/git-sync.sh "voices(cloud): sync $(date -u +%Y-%m-%dT%H:%MZ)" "fuel-voices"   # safe: atomic last-sync.txt, conflict-marker guard, rebase-retry WITHOUT --autostash; never call git add/commit/push or git stash manually

8. Кратко отчитайся: сколько цитат добавил, из каких источников.

OSINT-агрегация публичных отзывов. Только открытые источники.
```

**Cron:** `30 */8 * * *`

---

### 4️⃣ GRID-STATUS SYNC — каждые 6ч (`45 */6 * * *`)

**taskName:** `cloud-grid-status-sync`

```
Ты — автономная cloud-рутина GRID-STATUS карты «Топливный фронт РФ» (https://npz-tactical-map.vercel.app). Работай полностью сам.

РЕПО: https://github.com/volobuevaleksand7-hue/npz-tactical-map → клонируй в /tmp/npz-tactical-map.

ПОРЯДОК:
1. Подготовка:
   - rm -rf /tmp/npz-tactical-map && git clone https://github.com/volobuevaleksand7-hue/npz-tactical-map.git /tmp/npz-tactical-map && cd /tmp/npz-tactical-map
   - git config user.email "agent@npz-routine.local" && git config user.name "npz-routine-cloud"

2. Прочитай спецификацию: agents/update-prompt-grid.md. Прочитай текущий data/grid-state.json.

3. 4–6 WebSearch по подстанциям, ТЭС, отключениям. Окно — 72 часа.

4. Обнови data/grid-state.json через Write строго по схеме (substations / blackout_regions / events / meta). Без выдумок.

5. Валидация: python3 -c "import json;json.load(open('data/grid-state.json'))". Битый — git checkout -- data/grid-state.json.

6b. HEARTBEAT (ОБЯЗАТЕЛЬНО каждый запуск, даже если данных нет):
   python3 - <<'PY'
   import json, datetime
   now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
   p = "data/heartbeats.json"
   try: hb = json.load(open(p, encoding="utf-8"))
   except Exception: hb = {}
   hb["grid-status"] = now
   json.dump(hb, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
   print("heartbeat ->", now)
   PY

7. Push:
   - bash agents/git-sync.sh "grid(cloud): sync $(date -u +%Y-%m-%dT%H:%MZ)" "grid-status"   # safe: atomic last-sync.txt, conflict-marker guard, rebase-retry WITHOUT --autostash; never call git add/commit/push or git stash manually

8. Кратко отчитайся: сколько подстанций/регионов обновил.

OSINT-агрегация. Только открытые источники.
```

**Cron:** `45 */6 * * *`

---

### 5️⃣ FORECAST-ECONOMY SYNC — раз в неделю (`45 3 * * 0`)

**taskName:** `cloud-forecast-economy-sync`

```
Ты — автономная cloud-рутина FORECAST-ECONOMY карты «Топливный фронт РФ» (https://npz-tactical-map.vercel.app). Работай полностью сам.
ЗАЧЕМ: эта рутина закрывает мёртвый forecast-economy — он не был мигрирован в облако и мёртв 12 дней. Запускает forecast.json и economy.json снова.
МОДЕЛЬ: Opus (claude-opus-4-8) — это макро-анализ, нужна сильная модель.

РЕПО: https://github.com/volobuevaleksand7-hue/npz-tactical-map → клонируй в /tmp/npz-tactical-map.

ПОРЯДОК:
1. Подготовка:
   - rm -rf /tmp/npz-tactical-map && git clone https://github.com/volobuevaleksand7-hue/npz-tactical-map.git /tmp/npz-tactical-map && cd /tmp/npz-tactical-map
   - git config user.email "agent@npz-routine.local" && git config user.name "npz-routine-cloud"

2. Прочитай ПОЛНЫЕ спецификации из репо: agents/update-prompt-forecast.md И agents/update-prompt-economy.md (там полные инструкции — строго следуй обеим). Прочитай текущие data/forecast.json и data/economy.json (схемы).

3. Выполни макро-анализ по инструкциям из update-prompt-forecast.md и update-prompt-economy.md (WebSearch по топливному рынку, ценам, дефициту, экономике, экспорту/импорту нефтепродуктов).

4. Обнови data/forecast.json и data/economy.json через Write, строго по схеме (структуру и ключи НЕ менять). Если по теме нет данных — не выдумывай.

5. Валидация каждого файла:
   - python3 -c "import json;json.load(open('data/forecast.json'))". Битый — git checkout -- data/forecast.json.
   - python3 -c "import json;json.load(open('data/economy.json'))". Битый — git checkout -- data/economy.json.

5b. HEARTBEAT (ОБЯЗАТЕЛЬНО каждый запуск, даже если данных нет):
   python3 - <<'PY'
   import json, datetime
   now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
   p = "data/heartbeats.json"
   try: hb = json.load(open(p, encoding="utf-8"))
   except Exception: hb = {}
   hb["forecast"] = now
   hb["economy"] = now
   json.dump(hb, open(p,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
   print("heartbeat ->", now)
   PY

6. Push:
   - bash agents/git-sync.sh "forecast(cloud): sync $(date -u +%Y-%m-%dT%H:%MZ)" "forecast economy"   # safe: atomic last-sync.txt, conflict-marker guard, rebase-retry WITHOUT --autostash; never call git add/commit/push or git stash manually

7. Кратко отчитайся: что обновил в forecast.json и economy.json, ключевые выводы макро-анализа.

OSINT-агрегация публичных данных. Только открытые источники.
```

**Cron:** `45 3 * * 0` (раз в неделю, воскресенье 03:45)

---

## Шаг 2. Проверить что облако пишет

После создания каждого:
1. В UI нажми **«Run now»** — посмотри что одиночный запуск завершился успехом и в репо появился коммит вида `data(cloud): sync ...`.
2. Если первый запуск упёрся в git push (нет credentials в Cloud sandbox) — добавь в начало промпта `gh auth login --with-token <<< "$GITHUB_PAT"` (PAT придётся положить в переменные окружения cloud-сессии — у тебя это уже работает для NPZ-карты, повтори тот же способ).

## Шаг 3. Отключить локальные (только когда cloud работает)

Я подготовил оба варианта — но **запускать буду только когда ты подтвердишь, что cloud-агенты успешно пишут в репо**. Иначе получим окно с нулевым покрытием.

**Команды (НЕ запускать до твоего сигнала):**
- В Claude UI открыть Scheduled → каждой из 4 локальных → выключить toggle (не удалять — могут понадобиться как fallback).
- Либо через инструмент `update_scheduled_task` с `enabled=false` — я сделаю это одной командой когда скажешь.

---

## Зачем именно так

- **Cloud не видит твоего Mac.** Все промпты переписаны: каждый запуск делает свежий `git clone` репо (там лежат живые `agents/update-prompt-*.md`). Если я обновлю спецификацию агента — cloud подхватит её на следующем цикле автоматически.
- **Источник правды по логике остаётся в репо** (`agents/update-prompt-*.md`). Промпт в Cloud Agent — это просто диспатчер: клонировать → прочитать инструкцию из репо → выполнить → пушить.
- **Локальные** оставляем выключенными как fallback на случай если cloud забарахлит.
