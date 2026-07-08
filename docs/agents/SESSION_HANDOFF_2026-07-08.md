# Handoff — npz-tactical-map — 2026-07-08

## Status
SEO-неделя: 3/7 страниц готовы и в проде (Московский НПЗ, /talony, /moskva). Данные за 8 июля догнаны (удар по танкерам Азова). Проведена анти-пропаганда чистка + защита (санитайзер, гвард публикации, правила коллекторам). Деплой почин��н.

## Read first (в порядке)
1. `docs/tz-articles-2026-07-08.md` — ТЗ на все 7 страниц недели (черновики title/H1/FAQ, фактура, ловушки)
2. `docs/hermes-run-prompt.md` — как исполнять страницу (эталоны, чек-лист приёмки, правки от 08.07)
3. `CLAUDE.md` — правила проекта (нейтральность, обложки-Codex, guardrails)
4. auto-memory (инжектится): `npz-neutral-osint-guard`, `feedback-npz-covers-via-codex`, `npz-vercel-deploy-token-broken`, `npz-two-repo-copies`

## Осталось по неделе (1 страница/день, YMYL)
- Сб 11.07 — `/npz/slavneft-yanos` (ЯНОС) — ТЗ П4
- Вс 12.07 — `/npz/kujbyshevskij-npz` (НЕ путать с Новокуйбышевским) — П5
- Пн 13.07 — `/npz/ryazanskij-npz` (в strikes.json нет ударов — хронику не выдумывать) — П6
- Вт 14.07 — реоптимизация `/attacks`, `/refineries`, `/crimea` — П7

## Инфра (критично)
- **Репо живой:** `~/Documents/npz-tactical-map`. Пуш только через `ssh hermes-vps` (локальный sergeyramas → 403). После scp правок на VPS: git add/commit/`git pull --rebase --autostash`/push.
- **Деплой работает сам:** VERCEL_TOKEN обновлён 08.07 → GH Actions авто-деплой зелёный. Резерв: VPS умеет `vercel --prod` (сессия CLI в `~/.local/share/com.vercel.cli`).
- ⚠️ **claude CLI на VPS не залогинен** (коммит 1d9fdcb) — Гермес НЕ может гонять LLM-агентов; SEO-страницы собирает Claude-сессия (я), не крон.
- Данные карты live сразу через GitHub raw; статические страницы (`/news`, лендинги) — только после деплоя.

## Защита нейтральности (уже в проде, не ослаблять)
`agents/sanitize-strikes.py` в `.githooks/pre-commit` (чистит strikes.json + history-crimea.json) + `hermes/bot/content_guard.py` гвардом ПЕРЕД публикацией молнии в `strike_pipeline.py` + правила в 10 промптах-коллекторах + CLAUDE.md.

## Next step
Собрать Сб-страницу `/npz/slavneft-yanos` по ТЗ П4 (эталон `npz/omskij-npz.html`, свежая фактура из `data/*.json`), опубликовать через VPS.

## First message
```
Продолжаю npz-tactical-map (SEO-неделя + карта). Не начинай пока не скажу.
Прочитай: docs/agents/SESSION_HANDOFF_2026-07-08.md, docs/tz-articles-2026-07-08.md, CLAUDE.md.
Затем жди мою команду.
```
