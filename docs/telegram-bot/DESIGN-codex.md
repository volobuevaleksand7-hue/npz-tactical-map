# Telegram-бот «Топливный фронт РФ» — дизайн архитектуры

## Цель и критерии готовности

Цель: публичный Telegram-бот, на которого можно подписаться с сайта карты и который после каждого обновления карты рассылает короткий дайджест по новым данным: удары, 2-3 свежих голоса, сводка по АЗС, ссылки на карту и вкладку АЗС.

Критерии MVP:
- подписка работает через кнопку на сайте `t.me/<bot>?start=site`;
- `chat_id` и настройки не попадают в публичный GitHub-репозиторий;
- рассылка запускается после обновления `data/*.json`, идемпотентна и не шлет один и тот же апдейт дважды;
- дайджест строится только из diff опубликованных JSON, без генерации фактов.

## Ключевая рекомендация

Рекомендую связку: **Vercel Serverless Functions для Telegram webhook и API рассылки + Upstash Redis/Vercel KV для подписчиков и состояния + GitHub Action on push по `data/**` как основной триггер рассылки**.

Почему так для этого проекта:
- сайт уже на Vercel, значит endpoint бота можно держать рядом с сайтом без отдельного сервера;
- данные уже версионируются в GitHub, поэтому diff удобнее и надежнее считать на событии push, а не пытаться угадать апдейт по cron;
- текущий пайплайн обновления ручной, поэтому hook в `publish.sh` полезен как быстрый MVP, но GitHub Action лучше как независимый контур после фактического попадания данных в repo;
- бот не должен трогать `data/`: он читатель diff и отправитель сообщений.

## 1. Хостинг бэкенда бота

### Варианты

**Vercel Serverless webhook**
- Плюсы: уже есть Vercel-проект и домен; удобно хранить секреты в Vercel env; Telegram webhook естественно ложится в HTTP endpoint; нет постоянного процесса.
- Минусы: serverless не подходит для долгих массовых рассылок тысячам подписчиков; лимиты выполнения функции; cold start.
- Вывод: хороший выбор для `/start`, `/stop`, `/settings`, healthcheck и небольших рассылок через отдельный protected endpoint.

**GitHub Actions**
- Плюсы: лучший доступ к git diff между commit'ами; естественный триггер `on: push` по `data/**`; можно хранить state в Redis и секреты в GitHub Actions Secrets; не зависит от локального `publish.sh`.
- Минусы: не подходит как Telegram webhook; публичный repo требует аккуратности с secrets; Actions могут быть выключены/ограничены.
- Вывод: лучший выбор для вычисления diff и запуска рассылки после обновления данных.

**Отдельный воркер/VPS/cron**
- Плюсы: можно держать очередь, rate limiting, retries, long-running рассылку; проще масштабировать на большое число подписчиков.
- Минусы: новая инфраструктура, мониторинг, деплой, секреты, uptime; избыточно для ручного пайплайна и статического сайта.
- Вывод: отложить до фазы 2, если подписчиков станет много или появятся тяжелые ретраи/очереди.

### Решение

MVP: Vercel Functions:
- `POST /api/telegram/webhook/<secret>` — прием Telegram updates;
- `POST /api/telegram/broadcast` — protected endpoint, вызываемый GitHub Action после diff;
- опционально `GET /api/telegram/health` — проверка env и KV без раскрытия секретов.

GitHub Action:
- срабатывает на push в `main`, paths: `data/*.json`;
- получает `before`/`after` SHA из события;
- строит diff только нужных файлов;
- вызывает Vercel endpoint с payload дайджеста или с SHA-диапазоном.

Trade-off: рассылочный код можно держать либо в Action, либо в Vercel. Лучше держать **формирование diff в Action**, а **подписчиков, rate limit и Telegram send в Vercel**, чтобы `BOT_TOKEN` и доступ к базе были в одном runtime. Action получает только `BROADCAST_SECRET`.

## 2. Хранилище подписчиков

### Рекомендация: Upstash Redis через Vercel KV

Хранить:
- `subscribers` set: `chat_id`;
- `subscriber:<chat_id>` hash/json: `created_at`, `status`, `prefs`, `last_seen_at`, `source`, `lang`;
- `broadcast:last_sent_commit` string;
- `broadcast:sent:<digest_id>` string с TTL 90-180 дней;
- `broadcast:lock` ephemeral lock на время рассылки.

Почему Redis/KV:
- простая модель: set/hash/strings, без реляционной схемы;
- хорошо подходит для идемпотентности и locks;
- есть serverless-friendly HTTP API;
- Vercel KV фактически удобно подключается к Vercel-проекту и не требует отдельного backend-сервера.

Trade-off:
- Supabase дает SQL, аудит и удобную админку, но для MVP это больше поверхности и миграций;
- JSON/file в приватном месте дешевле, но хуже для конкурентных webhook/update, locks и удаления заблокировавших бота;
- публичный repo запрещен для `chat_id`, даже если файл неочевидный.

Если ожидаются десятки тысяч подписчиков и нужна аналитика по доставке, фаза 2: Supabase Postgres для `subscribers`, `deliveries`, `digest_runs`, а Redis оставить для locks/rate-limit.

## 3. Подписка с сайта

Поток:
1. На сайте кнопка «Подписаться в Telegram».
2. Ссылка: `https://t.me/<public_bot_username>?start=site_all`.
3. Пользователь открывает Telegram и нажимает Start.
4. Webhook получает `/start site_all`, валидирует payload и записывает `chat_id`.
5. Бот отвечает коротко: подписка включена, что будет приходить, кнопки «Открыть карту», «Вкладка АЗС», «Настройки».

Фильтры:
- MVP: один режим `all`, без сложных настроек. Это снижает риск пустых/разных дайджестов и упрощает идемпотентность.
- Допустимые команды сразу заложить в интерфейс: `/start`, `/stop`, `/status`.
- Фаза 2: `/settings` с темами `all`, `strikes`, `azs`. `voices` отдельно не нужен как первый фильтр: голоса являются частью контекста к топливной ситуации.

Deep-link payload:
- `site_all` — подписка с сайта на все дайджесты;
- позже можно добавить `site_azs`, `site_strikes`, если на сайте появятся отдельные CTA.

Прямые ссылки:
- карта: `https://npz-tactical-map.vercel.app/`;
- вкладка АЗС: лучше добавить поддержку URL-состояния на сайте, например `https://npz-tactical-map.vercel.app/?view=azs`.

Сейчас в коде вкладки переключаются через DOM `data-view`, без видимого URL-state. Поэтому ссылка на вкладку АЗС требует маленького изменения сайта в MVP: читать `?view=azs` при загрузке и переключать активную вкладку.

## 4. Триггер после каждого обновления карты

### Как узнаем факт апдейта

Основной триггер: GitHub Action:
- `on.push.branches: [main]`;
- `paths: ["data/*.json"]`;
- Action получает `github.event.before` и `github.sha`;
- diff строится между этими SHA.

Почему не только `publish.sh`:
- локальный `publish.sh` может завершиться до фактического push/deploy или быть обойден другим агентом;
- GitHub push является фактом попадания данных в source of truth;
- Action не требует менять `data/` и не зависит от машины, где запустили refresh.

Где встроить:
- MVP допускает быстрый hook в `agents/git-sync.sh` или publish-скрипт после успешного push: вызвать `POST /api/telegram/broadcast?commit=<sha>`.
- Рекомендуемый production-контур: GitHub Action on push. Hook в publish-скрипте оставить только как ручной fallback `workflow_dispatch`.

### Идемпотентность

Digest ID:
- `digest_id = <after_sha>` или `digest:<before_sha>:<after_sha>`.

Перед рассылкой:
- взять Redis lock `broadcast:lock` через `SET NX EX 300`;
- проверить `broadcast:sent:<digest_id>`;
- проверить, что `after_sha` не равен `broadcast:last_sent_commit`;
- если уже отправлено — завершить без сообщений.

После успешной рассылки:
- записать `broadcast:sent:<digest_id> = sent_at`;
- обновить `broadcast:last_sent_commit = after_sha`;
- сохранить минимальный summary run: count subscribers, count sent, count failed.

### Слать только новое

Diff считать по стабильным ключам:
- `strikes`: если нет `id`, ключ `date|time|city|target|source_url`;
- `fuel-voices`: ключ `date|seen|city|quote|source_url`;
- `fuel-availability.regions`: ключ региона, сравнение полей `level`, `queues_hours`, `ai95_price_rub`, `diesel_price_rub`, `networks[].status/limit_l/note`.

Если поле `generated_at` поменялось, но новых/измененных элементов нет, рассылку не отправлять или отправлять только владельцу debug-уведомление. Публичным подписчикам пустой «апдейт» не нужен.

## 5. Генерация дайджеста

Источники:
- `data/strikes.json` — новые удары/события;
- `data/fuel-voices.json` — новые или свежие голоса;
- `data/fuel-availability.json` — изменения по регионам/сетям/лимитам/очередям;
- опционально `data/health.json` — техническая дата обновления, не как содержательная новость.

Правила сборки:
- максимум 3 новых strikes, сортировка по date/time, confirmed выше unconfirmed;
- 2-3 голоса с `seen` или `date` в текущем diff, короткая цитата до 180-220 символов;
- АЗС: 2-4 региона с ухудшением/улучшением/новыми лимитами; если изменений нет — строка «По АЗС без существенных новых изменений».
- Не суммировать старые факты как новые.
- Не писать оценочные формулировки сверх того, что есть в JSON.

Формат Telegram:
- использовать HTML parse mode, потому что проще экранировать и контролировать жирный текст/ссылки;
- не использовать MarkdownV2 в MVP: он ломкий на русских кавычках, дефисах, скобках и URL;
- целиться в 1200-2500 символов, жесткий максимум 3500, чтобы не упираться в лимит Telegram 4096.

Шаблон:

```text
<b>Топливный фронт РФ: обновление карты</b>
<i>4 июля 2026</i>

<b>Новые события</b>
1. Санкт-Петербург — удар БПЛА по нефтяному терминалу. Подтверждение: confirmed.
2. ...

<b>Кто что говорит</b>
• Чита: "..."
• ...

<b>АЗС</b>
• Крым: severe, лимиты до 20 л, очереди ~1.5 ч.
• ...

Источник: открытые данные карты.
```

Inline-кнопки:
- `Открыть карту` → `https://npz-tactical-map.vercel.app/`;
- `Вкладка АЗС` → `https://npz-tactical-map.vercel.app/?view=azs`;
- опционально `Отписаться` → callback button или команда `/stop`.

Для callback-кнопок нужен webhook handler callback_query. В MVP можно не делать callback для отписки и использовать `/stop`, но inline URL-кнопки обязательны.

## 6. Лимиты, анти-спам и безопасность

Telegram send limits:
- ориентир: не превышать 25-30 сообщений/сек глобально;
- для MVP слать последовательно или батчами по 10-20 с паузой 1 сек;
- на HTTP 429 читать `retry_after` и повторять;
- на 403/400 `bot was blocked by the user` помечать подписчика `status=blocked` или удалять из set.

Анти-спам:
- одна публичная рассылка на один `digest_id`;
- если за один push нет нового содержимого, не рассылать;
- если несколько push подряд в течение короткого окна, можно в фазе 2 добавить debounce 5-10 минут через Action concurrency или Redis delayed run.

Чистка:
- при `/stop` удалить `chat_id` из `subscribers`, запись оставить в `subscriber:<chat_id>` со статусом `stopped` без лишних данных;
- при Telegram 403 удалить из активного set;
- периодическая чистка не нужна для MVP, потому что чистка происходит на рассылках.

Безопасность:
- создать нового публичного бота, не использовать приватный watchdog bot;
- `TELEGRAM_BOT_TOKEN`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `BROADCAST_SECRET`, `WEBHOOK_SECRET` хранить в Vercel env / GitHub Secrets;
- webhook path делать непредсказуемым: `/api/telegram/webhook/<WEBHOOK_SECRET>`;
- дополнительно проверять Telegram header `X-Telegram-Bot-Api-Secret-Token`, если используется `setWebhook secret_token`;
- `POST /api/telegram/broadcast` принимать только с `Authorization: Bearer <BROADCAST_SECRET>`;
- логировать без `chat_id` в открытом виде: маска `609***529` или hash.

## 7. MVP и фаза 2

### MVP

1. Создать нового публичного Telegram-бота через BotFather.
2. Добавить Vercel env для токена, Redis/KV и секретов.
3. Сделать Vercel webhook:
   - `/start` регистрирует подписчика;
   - `/stop` отписывает;
   - `/status` показывает состояние подписки.
4. Добавить кнопку на сайт: `t.me/<bot>?start=site_all`.
5. Добавить URL-state для вкладки АЗС: `?view=azs`.
6. Сделать GitHub Action on push `data/*.json`:
   - вычисляет diff `before..after`;
   - вызывает protected broadcast endpoint.
7. Broadcast endpoint:
   - проверяет idempotency;
   - собирает дайджест из новых strikes, voices, fuel-availability changes;
   - рассылает HTML-сообщение с inline URL-кнопками;
   - чистит заблокировавших бота.

### Фаза 2

- настройки тем: `all`, `strikes`, `azs`;
- очередь рассылки/воркер, если подписчиков станет много;
- delivery log и admin summary владельцу после каждого запуска;
- debounce нескольких push в один дайджест;
- preview mode: Action сначала отправляет владельцу черновик, затем публикует после подтверждения;
- Supabase Postgres, если понадобится аудит, сегменты, история доставок и удобная админка.

## Вывод

Для этого проекта не нужен отдельный постоянно работающий бот-сервер: оптимальная архитектура — Vercel webhook для подписки и отправки, Upstash/Vercel KV для приватных `chat_id` и состояния, GitHub Action по push в `data/*.json` для надежного diff-триггера после обновления карты. MVP должен быть максимально узким: одна подписка `all`, HTML-дайджест только из новых JSON-элементов, idempotency по commit SHA и прямые кнопки на карту/АЗС.
