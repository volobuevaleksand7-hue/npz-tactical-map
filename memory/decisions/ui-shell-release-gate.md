---
name: ui-shell-release-gate
description: Почему index.html/styles.css/app.js/radar.html/version.json/CHANGELOG.md заперты за ALLOW_FRONTEND_RELEASE=1 — читать перед любой правкой фронтенда.
type: decision
trust: internal
approved_by: 2ea839a6-91da-4d77-a654-1596ac52fe93
---

# UI-shell release gate

## Решение

Файлы `index.html`, `styles.css`, `app.js`, `radar.html`, `version.json`, `CHANGELOG.md`, `.vercelignore` — «protected UI/release files». Коммит с ними блокируется `.githooks/pre-commit`, если не выставлена `ALLOW_FRONTEND_RELEASE=1`. Осознанный UI-релиз дополнительно требует SemVer-бампа и записи в `AGENT_ACTIVITY.md`.

## Почему

2026-07-07: компактный UI (`v1.0.0`) выкатили прямым `vercel deploy --prod`, но не закрепили в `origin/main`. Следующий автодеплой (GitHub Action по пушу в main) перетёр alias старой оболочкой — релиз откатился незаметно. Источник правды для оболочки — только `origin/main`; прямой `vercel deploy` в обход git для shell-файлов запрещён.

Дальше выяснилось, что агенты-сборщики (Haiku на cron) и параллельные Claude-сессии регулярно трогают репозиторий без понимания, что фронтенд — не такой же файл, как `data/*.json`. Гейт не даёт headless-агенту случайно закоммитить правку оболочки в общем потоке data-коммитов.

## Что я сломаю, если не буду это знать

- Молча закоммичу правку `app.js` вместе с data-коммитом — хук заблокирует пуш с непонятной ошибкой, если не знать про флаг.
- Забуду проставить `ALLOW_FRONTEND_RELEASE=1` для намеренного UI-релиза — коммит просто не пройдёт, и придётся гадать, почему.
- Не подниму SemVer/CHANGELOG — фронтенд-релизы теряют версионную дисциплину, `version.json` на сайте разойдётся с реальным состоянием оболочки.

## Как это работает на практике

`agents/README.md` и `AGENT_ACTIVITY.md` прямо указывают: перед UI-работой читать `AGENT_ACTIVITY.md`, чтобы не столкнуться с другой сессией, тронувшей те же файлы. Hermes/VPS-рутины НЕ делают прямой `vercel deploy --prod` для оболочки — только пуш в main, дальше CI.
