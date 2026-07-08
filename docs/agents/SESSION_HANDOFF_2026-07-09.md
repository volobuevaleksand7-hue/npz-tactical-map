# Handoff — npz-tactical-map — 2026-07-09

## Status
Линия «статьи-воронки на карты» запущена и в проде: `/karta-benzina-krym` (48к→карта АЗС), `/attacks` реопт (freshness→радар), `/karta-bpla` (126к map-интент→радар). IA починена (единая навигация + чип свежей статьи + sitemap). Осталась реоптимизация `/radar` и топливная ветка.

## Read first (в порядке)
1. `docs/tz-funnel-maps-2026-07.md` — план воронок (АЗС + радар), кластеры, расписание
2. `docs/tz-radar-cluster-2026-07.md` — гражданский кластер БПЛА/тревога (XMLRiver, реальные частоты) + ТЗ /karta-bpla
3. `CLAUDE.md` — правила проекта (нейтральность, обложки-Codex, guardrails)
4. auto-memory: `npz-funnel-maps-track`, `npz-article-nav-registry-driven`, `xmlriver-api-credentials`, `npz-neutral-osint-guard`

## In-session decisions
- **Навигация registry-driven через один `agents/build-nav.py`:** генерит меню лендингов + дропдаун ГЛАВНОЙ + хаб `/analytics` + «Свежее»-чип на карте из `data/seo-topics.jsonl`. Меню/чип руками не править. `check-ia.py` стережёт сирот.
- **Единый sitemap:** `gen-news.py` теперь зовёт `seo/generate-sitemap.py` (раньше свой куцый генератор затирал лендинги при каждой сводке). `/support` в EXCLUDE. Бэкфиллить руками не надо.
- **Единая шапка** на `/radar` и `/sources` (были урезанные меню = «отдельные сайты»).
- **Радар-freshness** решили реоптом `/attacks`, отдельную live-страницу не плодили.
- **XMLRiver-ресёрч:** гражданский кластер гигантский (`бпла сегодня` 1М, `ракетная опасность` 1М, map-интент `карта бпла` 126к). Взяли MAP-интент под `/karta-bpla`, freshness-миллионники не таргетим (news-SERP).

## Infra (критично)
- **Пуш только `ssh hermes-vps` → `bash agents/git-sync.sh "<msg>"`** (НЕ `git pull --rebase --autostash` — крон пишет data/, будут конфликт-маркеры). Сначала свой `git commit`, потом git-sync.
- **Фронтенд-ядро** (`index.html`, `styles.css`, `app.js`, `radar.html`, `version.json`) — коммит под `ALLOW_FRONTEND_RELEASE=1` + запись в `AGENT_ACTIVITY.md`.
- Деплой авто: push в main → GH Action → Vercel. Данные live через GitHub raw.
- **XMLRiver Wordstat:** `user=21268`, ключ в памяти `[[xmlriver-api-credentials]]`, эндпоинт `xmlriver.com/wordstat/new/json`, гонять с VPS (из US таймаутит). Сырой пул по тревоге: VPS `/root/staged/civil-wordstat.json`.
- Добавил страницу → строка в `seo-topics.jsonl` + лейбл/HUB в `build-nav.py` → `build-nav.py` + `generate-sitemap.py` + `check-ia.py`.

## Next step
Реопт `/radar` SEO: title/description под «карта бпла онлайн» + текстовый блок под H1 (сейчас радар — голое приложение без текста, а на нём миллионный freshness). Гейт-коммит.

## First message
```
Продолжаю npz-tactical-map (линия воронок на карты + SEO). Не начинай пока не скажу.
Прочитай: docs/agents/SESSION_HANDOFF_2026-07-09.md, docs/tz-funnel-maps-2026-07.md, docs/tz-radar-cluster-2026-07.md, CLAUDE.md.
Затем жди мою команду.
```
