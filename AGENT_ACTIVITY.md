# AGENT_ACTIVITY — npz-tactical-map

Координация агентов по проекту. Одна строка на значимое действие.

## Зоны ответственности (чтобы агенты не пересекались по файлам)
- **agent:npz-status** → `data/fuel-state.json`: `refineries[]`, `export_terminals[]`, часть `events[]`, `meta`.
- **agent:fuel-market** → `data/fuel-state.json`: `deficit_regions[]`, `national_balance`, `fuel_balance`, часть `events[]`, `meta`.
- **Hermes/VPS routines** → `data/*.json`, `news.html`, `news/*.html`, `sitemap.xml`, `assets/cover-*.png`, Telegram pipeline.
- **UI-shell protected** → `index.html`, `styles.css`, `app.js`, `radar.html`, `version.json`, `CHANGELOG.md`, `.vercelignore`.
  - Эти файлы трогает только человек/основной агент по явному запросу.
  - Любой commit с UI-shell файлами требует `ALLOW_FRONTEND_RELEASE=1`, SemVer и запись в этот журнал.
  - Hermes не делает прямой `vercel deploy --prod` для оболочки; источник правды — `origin/main`.

## Log
- 2026-07-07 — `v1.4.14` (по запросу владельца): Яндекс.Метрика переключена на анонимный счётчик id `110490245` (был `110462213`, привязан к аккаунту владельца). Заменена ВСЯ вставка в `index.html` на новый снипет владельца (добавились опции `ssr`, `ecommerce:"dataLayer"`, `referrer`, `url`). `yandex-verification` мета-тег (Вебмастер) НЕ трогал — новый код не давали, старый ещё висит от прежнего аккаунта. `sources.html` содержит только закомментированный шаблон-заглушку (`YANDEX_METRICA_ID`), не боевой — не трогал.
- 2026-07-07 — ops: verify CI — тестовый коммит после переезда репо, чтобы подтвердить зелёный прогон `.github/workflows/deploy.yml` (VERCEL_* секреты) на новом аккаунте.
- 2026-07-07 — ops (по запросу владельца): Telegram-бэкенд СНОВА ВКЛЮЧЁН — токен `~/.npz-bot/token` восстановлен, cron-строки `broadcast.py --briefing` (утро/вечер) и `cron-radar-alerts.sh` раскомментированы; `getMe` = ok (`@NpzFuel_Bot`). Бот и канал `@NPZmap` оставлены для владельца (подписчиков не было). ВАЖНО: публичные кнопки Telegram на сайте (`index.html`, `radar.html`) остаются УБРАННЫМИ — канал/бот работают приватно, без публичной привязки к сайту. Отменяет строку про «отключение Telegram» из записи v1.4.12.
- 2026-07-07 — `v1.4.13` (по явному запросу владельца): убрана кнопка «Неточность» с `mailto:` на личную почту владельца из шапки карты (`index.html`). Почта больше не встречается ни в одном файле репозитория. Причина — деанон-риск.
- 2026-07-07 — `v1.4.12` (по явному запросу владельца): убраны ссылки на Telegram с сайта — кнопка канала `@NPZmap` (`index.html`) и баннер бота `@NpzFuel_Bot` + CSS (`radar.html`). На Hermes VPS отключена Telegram-публикация: токен `~/.npz-bot/token` деактивирован (→ `token.disabled-*`), закомментированы cron-строки `broadcast.py --briefing` (утро/вечер) и `cron-radar-alerts.sh`; сбор данных/`/news`/git-sync не тронуты (бэкап crontab: `/root/.crontab.backup-*`). Причина — снижение юридических/деанон-рисков; удаление самих канала и бота в Telegram — за владельцем.
- 2026-07-07 — `v1.3.0`: перестройка пайплайна публикаций (Fable 5). Единый рендер (`hermes/bot/render.py`) + единый дедуп (`hermes/bot/day_state.py`) для сводки/молнии/апдейта/БПЛА-алерта. Молния (`strike_pipeline.py`/`radar_publish.py`) переведена из dry-run в прод: TIER1 авто в канал, TIER2 владельцу с кнопками Опубликовать/Отклонить. `broadcast.py --update` — пополнение сводки (editMessageCaption/Text). Legacy editorial/diff-дайджест отключены из publish-путей (`NPZ_LEGACY=1` для ручного вызова). Найден и исправлен баг: `strike_pipeline.py --dry-run` персистил state — добавлен `--backfill` для безопасного включения молнии без спам-рассылки по 65-ударному беклогу. Полный диагноз: `docs/agents/audit-2026-07-07.md`; редполитика: `docs/npz-posting-style-v2.md`; миграция VPS-джобов: `docs/agents/jobs-migration-2026-07-07.md`.
- 2026-07-07 — incident: compact UI `v1.0.0` был опубликован прямым Vercel deploy, но не закреплён в `origin/main`; последующие Hermes/GitHub Actions production deploys перетёрли alias старой оболочкой. Решение: вернуть компактный UI как git-backed release, поднять версию, добавить UI-shell lock в `HERMES.md` и `.githooks/pre-commit`.
- 2026-06-11 — init проекта (Fable 5): каркас, фронт (Leaflet HUD), seed-датасет из ресёрча, скрипты cron-агентов (Haiku), vercel.json. Деплой на Vercel — в процессе.
