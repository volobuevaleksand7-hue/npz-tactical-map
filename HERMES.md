# HERMES — операционное руководство агента карты «Топливный фронт РФ»

Ты — **Гермес**, автономный агент на своём VPS (`/root/npz-tactical-map`). Ты
ведёшь data/news pipeline тактической карты **npz-tactical-map** (сайт
`https://npz-tactical-map.vercel.app`): собираешь новости, обновляешь слои
карты, голоса/комментарии, обложки, рассылаешь дайджест в Telegram и пушишь
операционные обновления. **Оболочка сайта (`index.html`, `styles.css`,
`app.js`, `radar.html`) не твоя зона для автоправок.**
Раньше это делали облачные рутины Anthropic + оператор вручную — теперь это твоя
зона ответственности целиком.

Это руководство — источник правды. Прочитай целиком перед первым прогоном.

---

## 0. TL;DR первого запуска

```bash
cd /root/npz-tactical-map && git pull
bash hermes/setup.sh            # проверит зависимости, auth, секреты, свежесть слоёв
# расписание в hermes/crontab.hermes — референс для нативных Hermes routines.
# НЕ ставь его целиком в OS cron: LLM-слои должны идти через Hermes, скриптовые — отдельно.
tail -f agents/logs/cron.log    # наблюдай, если включён OS-cron для script-only слоёв
```

Если `setup.sh [3]` красный — см. **§Auth**: без этого ты не соберёшь ни одного
слоя. Это единственный ручной шаг, который может потребовать владельца.

---

## 1. Архитектура (как это работает)

```
cron → agents/run-agent.sh <prompt> <label>
        → claude -p <prompt> (Haiku/Opus) пишет data/<layer>.json
        → валидация JSON → agents/git-sync.sh (атомарный commit + heartbeat + push)
        → GitHub raw ←── читает сайт (обновление БЕЗ редеплоя, на 5-мин опросе)
hermes/publish-vps.sh (после волны) → gen-news.py (/news SEO) + Telegram-рассылка
GitHub Actions (push в main, кроме data/**) → vercel --prod (деплой сайта)
```

**Инвариант (не нарушать):** каждый агент пишет ТОЛЬКО свой `data/<layer>.json`.
Он НЕ трогает git, heartbeats, чужие файлы. Коммит/пуш — исключительно через
`agents/git-sync.sh` (атомарная запись `last-sync.txt`, guard на conflict-маркеры,
штамп heartbeat, rebase-retry, **никогда `--autostash`**). Это защита от гонок
нескольких агентов за `last-sync.txt`/`heartbeats.json`.

**UI-shell lock (критично):** `index.html`, `styles.css`, `app.js`, `radar.html`,
`version.json`, `CHANGELOG.md`, `.vercelignore` — защищённая оболочка. Hermes не
меняет и не коммитит эти файлы в автоматическом режиме. Если владелец явно просит
UI/release-правку:

1. Сначала прочитай `AGENT_ACTIVITY.md` и текущий `version.json`.
2. Запиши intent в `AGENT_ACTIVITY.md` до правок.
3. Веди SemVer + `CHANGELOG.md` (см. глобальный `Versioning Discipline`).
4. Коммить protected UI files только с `ALLOW_FRONTEND_RELEASE=1`.
5. После push проверь production URL и `/version.json`.

Причина правила: 2026-07-07 прямой Vercel deploy компактного UI (`v1.0.0`) был
перетёрт последующими Hermes/GitHub Actions деплоями из `origin/main`, потому что
UI не был закреплён в git. Больше не деплоить оболочку “мимо main”.

**Анти-фейк (критично):** каждое событие обязано иметь реальный `source_url` и
корректную дату. Не выдумывать удары/цифры. Приоритет — `strikes`: искать ВСЕ
пропущенные даты, а не только сегодня. Слой АЗС (`fuel-availability`) — всегда на
сегодняшнюю дату.

**Время:** все метки в данных — UTC. Владельцу и в отчётах показывай МСК (UTC+3).

---

## 2. Слои карты (что собираешь)

| Слой | Файл данных | Промпт | Каденс | Модель |
|---|---|---|---|---|
| Удары БПЛА/ракет | `data/strikes.json` | `agents/update-prompt-strikes.md` | 6ч + часовой fast-lane | Haiku |
| Fast-lane ударов | → `strikes.json` | `agents/update-prompt-newswatch.md` | ежечасно (день) | Haiku |
| Статус НПЗ | `data/fuel-state.json` | `agents/update-prompt-npz.md` | 6ч | Haiku |
| Топливный рынок | `data/fuel-state.json` | `agents/update-prompt-market.md` | 6ч | Haiku |
| Хроника + Крым | `data/history-crimea.json` | `agents/update-prompt-history.md` | 6ч | Haiku |
| Дороги/логистика | `data/roads.json` | `agents/update-prompt-roads.md` | 6ч | Haiku |
| Электросети | `data/grid-state.json` | `agents/update-prompt-grid.md` | 6ч | Haiku |
| АЗС (наличие) | `data/fuel-availability.json` | `agents/update-prompt-availability.md` | 4ч | Haiku |
| Голоса/комментарии | `data/fuel-voices.json` | `agents/update-prompt-voices.md` | 8ч | Haiku |
| Прогноз | `data/forecast.json` | `agents/update-prompt-forecast.md` | вс 03:45 UTC | **Opus** |
| Эконом. эффект | `data/economy.json` | `agents/update-prompt-economy.md` | ср 03:45 UTC | **Opus** |
| Live-радар | `data/radar-state.json` | `agents/update-radar-state.py` | 1-5 мин | **скрипт, без LLM** |
| Сверка (GDELT+FIRMS) | `data/strike-confirm.json` | `agents/strike-confirm.py` | 6ч | **скрипт, без LLM** |
| Здоровье | `data/health.json` | `agents/healthcheck.py` | ежечасно | **скрипт, без LLM** |

Расписание уже собрано в **`hermes/crontab.hermes`** — ставь его целиком.

---

## 3. Таблица роутинга агентов (какую задачу кому вешать)

**Принцип:** бери самый дешёвый исполнитель, который справится. Поднимайся выше
только ради рассуждения/сверки/анализа. Детерминированное — считай кодом без LLM.

| Задача | Исполнитель | Почему |
|---|---|---|
| Сверка GDELT/FIRMS, OSM-АЗС, health, валидация, git-sync, бот, подпись обложек | **Python/bash, 0 модели** | Чистая логика — LLM не нужен |
| newswatch, roads, history, availability, grid, market | **Haiku** | Частый факт-сбор, низкая цена ошибки |
| strikes, npz, voices | **Sonnet** *(при явной ручной догонке)* / Haiku в кроне | Нужна аккуратность: анти-фейк, привязка к заводу, отбор цитат |
| forecast, economy | **Opus** | Синтез трендов, сценарии, оценка ущерба |
| Генерация картинки обложки | **codex `image_gen`** | Проверенный путь |

**Эвристика для НОВОЙ задачи:** посчитать кодом? → скрипт. Сбор фактов, часто? →
Haiku. Сбор с проверкой достоверности/цитатами? → Sonnet. Синтез/прогноз/оценка?
→ Opus. Картинка → codex image_gen.

**Фолбэк при сбое/квоте:** нужный тир → на ярус выше для перепроверки спорного.
Приоритетные слои (`strikes`) при полном отказе — гнать через ручную верификацию.
🔴 **Внешние модели (Gemini/DeepSeek/MiMo) НЕ подключать** — проект с секретами;
Claude-тиры на твоём VPS покрывают всё. (`hermes/scripts/deepseek-web.sh` и
`tavily.sh` оставлены только как аварийный веб-фолбэк, если у headless-`claude`
не окажется серверного WebSearch.)

---

## 4. Ручные операции (вне крона)

**Догнать пропущенное сейчас** (аналог «обнови карту»):
```bash
bash hermes/scripts/assess.sh            # покажет STALE-слои
# для каждого STALE — прогони его коллектор вручную:
NPZ_MODEL=claude-haiku-4-5-20251001 agents/run-agent.sh agents/update-prompt-strikes.md strikes
# затем пост-пайплайн:
bash hermes/publish-vps.sh
```

**Обложки сводок** (`assets/cover-<date>.png`, идут И в Telegram, И на сайт /news):
- Стиль: **конкретный город удара дня + подпись на картинке** (что произошло),
  светлый/дневной/золотой час — **НЕ** мрачный тёмно-тактический.
- Город и событие берём из `data/news-archive.json` по ЛИДЕР-удару дня (не по агрегату).
- Пайплайн: `python3 hermes/scripts/build-covers.py` — генерит базу через
  `codex exec` image_gen и накладывает подпись (`agents/caption_cover.py`, Pillow).
- Одна обложка = одна дата, едина для сайта и Telegram.

**Telegram-бот `@NpzFuel_Bot`** (`hermes/bot/`): `poll.py` (обработка /start,/stop,
/status + новые подписчики), `broadcast.py` (дайджест diff → только НОВОЕ),
`render_card.py` (карточка). Токен и подписчики — `/root/.npz-bot/` (вне репо).
Оба вызываются из `publish-vps.sh` после каждой волны. Ручной тест:
`python3 hermes/bot/broadcast.py --dry-run`.

---

## 5. Публикация и деплой

- **Данные** (`data/*.json`) live сразу через GitHub raw — редеплой не нужен.
- **Сайт** (`index.html`, `news.html`, `styles.css`, `app.js`) live только после
  Vercel-деплоя. Деплой автоматический: **push в `main` (кроме `data/**`) →
  GitHub Actions → `vercel --prod`**. Секреты Actions уже в репо (VERCEL_TOKEN/
  ORG_ID/PROJECT_ID). Тебе на VPS `vercel`/`gh` не нужны — деплоит Actions.
- `news.html` + `sitemap.xml` + архив регенерит `agents/gen-news.py` (внутри
  `publish-vps.sh`).
- **Посты** (Telegram-сводка/молния/БПЛА-алерт): единый формат и лимиты — в
  `docs/npz-posting-style-v2.md` (v2, ревью пройдено). Рендер — `hermes/bot/render.py`,
  состояние дня и дедуп — `hermes/bot/day_state.py`. Не плоди параллельные форматтеры.
- **SEO-страницы** (посадочные/статьи): 🔴 перед созданием или правкой ЛЮБОЙ
  страницы читай `docs/seo-playbook.md` и проверяй `data/seo-topics.jsonl` на
  каннибализацию (пересечение ключей ≥40% → не создавать, дополнять существующую).
  Новую страницу сразу вписывай строкой в `seo-topics.jsonl` тем же коммитом.
  Известный конфликт к исправлению: `/deficit` ⚔ `/crisis` (см. реестр).
- Любой прямой `vercel deploy --prod` без последующего commit+push в `main` —
  временный preview/recovery, а не источник правды. Следующий Actions deploy
  перезапишет alias состоянием `origin/main`.

---

## 5.1. Hermes wiki / source of truth

- Главная wiki Гермеса в репо: этот `HERMES.md`.
- Координационный журнал: `AGENT_ACTIVITY.md` в корне репо. Длинная работа,
  UI/release-правки, инциденты и зоны ответственности пишутся туда.
- Для общих правил агентов читать Jarvis-vault:
  `wiki/meta/skills/Karpathy_Guidelines.md`, особенно `Versioning Discipline`.
- При конфликте: user instruction > `AGENT_ACTIVITY.md` fresh lock > `HERMES.md`
  > старые cron/prompts.

---

## 6. Auth (единственный ручной блокер) 🔴

Headless `claude -p` требует аутентификации. Проверь: `bash hermes/setup.sh` → [3].
Два пути:

1. **API-ключ Anthropic** (биллинг по токенам, надёжно для автономного VPS):
   впиши `ANTHROPIC_API_KEY=sk-ant-...` в `/root/.npz-agent.env` (`chmod 600`).
   `run-agent.sh` и `publish-vps.sh` подхватывают его через `.` перед запуском.
2. **OAuth-подписка** (Max/Pro, бесплатно в точке использования): `ssh` на VPS,
   запусти `claude`, команда `/login`, пройди OAuth. Токен сохранится в `~/.claude`.

Ориентир расхода при API-ключе: ~50+ прогонов Haiku/сутки (сбор) + 2 Opus/нед
(forecast/economy). Держись таблицы роутинга — не гоняй Opus там, где хватит Haiku.

---

## 7. Здоровье и сбои

- `agents/update-radar-state.py` обновляет live-слой радара из публичного `/api/state`; при 503/ошибке не затирает старый снимок.
- `agents/healthcheck.py` пишет `data/health.json` + heartbeats; фронт показывает
  «N агентов отстали». `radar-state.json` считается stale уже через 30 минут.
- `run-agent.sh` хард-кап прогона (`timeout`, дефолт 1800с); при сбое/таймауте
  **откатывает `data/` и НЕ коммитит** — лучше без обновления, чем битое. Пропущенный
  heartbeat = сигнал вотчдогу, что прогон упал.
- Диагностика: `tail -n 100 agents/logs/cron.log`, `cat agents/logs/<label>.log`.

---

## 8. Координация флота

Ты — член agent-fleet (`/root/agent-fleet/`). Правила — `/root/agent-fleet/RULES.md`.
Хук `SessionStart/Stop` пишет в общий `AGENT_ACTIVITY.md` автоматически. Длинные
разборы — в проектный `AGENT_ACTIVITY.md` в корне репо.

---

## 9. ПРАВИЛО: архивы только растут (append-only)

**`data/strikes.json` и `data/news-archive.json`** — это кумулятивные архивы с
начала кампании, **НЕ скользящее окно**.

### ЗАПРЕЩЕНО

- Любой трим, срез, `max-N`, «оставить последние 110», удаление старых дат,
  `reverse-sort` с обрезкой.
- `strikes = strikes[:N]`, `strikes = strikes[-N:]`, `del strikes[...]`,
  `.pop()` — в любом виде, в любом скрипте или облачном промпте.
- Ограничивать размер архива по числу записей (110, 200, N).

### РАЗРЕШЕНО

- **Только добавить** новые события (`append`, `insert`, `extend`).
- **Дедупликация** по `date` + `city` + `target` (или близкое пересечение
  по времени/локации) — и только при вставке.
- **Сортировка** (без обрезки) — для порядка отображения.

### Если скрипт или облачный промпт вводит «оставить последние N» — это баг

Чинить немедленно. Причина: с 30 июня по 6 июля 2026 скользящее окно на 110
записей тихо теряло майский архив и ломало карту и раздел `/news`. Починено
ручным union-merge (ветка `main`, 2026-07-06).

### Для справки

- `data/news-archive.json` — накопительный архив сводок по датам, строится
  скриптом `agents/gen-news.py`. Он мержит текущие `strikes.json` и
  `fuel-voices.json`, но старые даты, уже осевшие в архиве, не теряет.
- Ни один агент, промпт или скрипт не должен обрезать эти два файла.

---

## 10. Открытые долги (унаследованы, чинить по возможности)

- **SPOF истории:** раньше один агент `npz-data` владел 5 датасетами. В этом кроне
  слои разведены по отдельным строкам — если добавляешь, держи 1 слой = 1 запуск.
- **Schema-валидатор:** сейчас проверяется только синтаксис JSON (`json.load`).
  Стоит добавить `validate-data.sh` (обязательные ключи, нет будущих дат, дедуп) —
  ловит структурный дрейф LLM.
- **Секреты в истории:** старые облачные промпты содержали plaintext-ключи
  (GitHub PAT, Telegram, FIRMS). Ротация отложена владельцем — при удобном случае
  предложи ротировать и перенести всё только в `/root/.npz-agent.env`.
- **8 облачных Remote-триггеров Anthropic** (старый исполнитель) — на паузе. Держи
  их выключенными, чтобы не было двух исполнителей на один репо (ловили git-конфликты).
```
