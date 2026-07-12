# Handoff — npz-tactical-map — 2026-07-12 (SEO-волны + VPN)

## Status
ТАНЕКО/Башнефть-Уфа/ТАИФ-НК/Ильский НПЗ-страницы + флагман /udary-azovskoe-more опубликованы (prod 200); VPN-нудж hidemy раскатан на картах и контентных страницах, владелец доработал до v1.19.1 (язычок вместо поповера); открытых блокеров нет.

## Read first (in order)
1. auto-memory (инжектится сам): `npz-seo-wave2-and-non-refinery-cities`, `npz-vpn-nudge-placement`, `npz-publish-clean-worktree-recipe`, `npz-git-sync-hard-reset-hazard`
2. `CLAUDE.md` + `docs/seo-playbook.md` — правила проекта и SEO против каннибализации
3. Origin main — источник истины (локальное дерево Мака ресетится git-sync'ом)

## In-session decisions
- Правки/публикация фронтенда — только через чистый git worktree на origin/main + сразу commit+push; общее дерево Мака hard-ресетится фоновым git-sync (снесло VPN-правки целиком) — отвергнуто: править в общем дереве.
- После правки styles.css/vpn-nudge.js обязательно бампать ?v= на ссылающихся страницах — иначе Vercel-edge отдаёт stale (блок вышел без стилей) — отвергнуто: менять контент без бампа версии.
- Гейт index.html/styles.css — `ALLOW_FRONTEND_RELEASE=1` env-префиксом; пуш анон-аккаунтом `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue) git push`.
- Курск/Брянск/Севастополь — не НПЗ-города (нет заводов), страниц /npz/ по ним не делать.

## Next step
Опубликовать следующую объектную НПЗ-страницу для /refineries (#2 по трафику) — приоритет Кинеф (2-й НПЗ РФ), далее Новокуйбышевский/Афипский/Славянский/Новошахтинский; ТАИФ-НК тонкая, кандидат на замену Новокуйбышевским.

## First message
Продолжаем npz-tactical-map. Хэндоф-нота: docs/agents/SESSION_HANDOFF_2026-07-12-seo-vpn.md, плюс CLAUDE.md проекта. Прошлая сессия опубликовала 4 НПЗ-страницы + флагман /udary-azovskoe-more и раскатала VPN-нудж hidemy на картах/контенте (владелец доработал до v1.19.1). Первым делом: подними чистый worktree на origin/main, проверь prod-статус (200) текущих страниц и живость /news за 12.07. Дальше — публикация следующей объектной НПЗ-страницы (Кинеф) для линии /refineries по правилам seo-playbook.md. Жди мою команду.
