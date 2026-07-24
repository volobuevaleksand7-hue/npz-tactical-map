# Handoff — npz-tactical-map: смена VPN-партнёрки — 2026-07-24

## Status
VPN-монетизация карты живёт на проде (hidemy). Итог: ~300 кликов, **0 продаж** (цена 990₽ высока). Решено сменить партнёрку на RKNoff. Замена НЕ начата — её выполняет новый чат.

## Задача
Заменить реф hidemy → RKNoff на всех точках показа + передеплой.
- Старый: `https://hidemn.club/#6a514a15942d6`
- Новый:  `https://t.me/rknoff_bot?start=ref-609952529`

## Где менять (2 файла)
1. `vpn-nudge.js:7` — `var REF = '...'` (контекстные плашки на статике + плавающий блок на карте)
2. `app.js:36` — захардкоженный href в попапах карты. 🔴 Там же СТАРЫЙ текст кнопки «→ Получить доступ через hidemy» — привести к общему стилю.

## 🔴 Новый реф — Telegram-БОТ, не сайт (дизайн-решение, не только swap URL)
Кнопка «Открыть источник» подразумевает «прочитать заблок-статью через VPN». `t.me/rknoff_bot` открывает бота, а не статью → мисматч сильнее прежнего. НАДО пересмотреть текст кнопки/подписи под бота (напр. «Получить VPN в Telegram»), не оставлять «Открыть источник». RKNoff = «РКН off», anti-censorship VPN через ТГ-бота — по бренду ближе к аудитории.

## Read first (в порядке)
1. `CLAUDE.md` — правила репо (🔴 git-гигиена НПЗ, аноним-аккаунт)
2. память `project_npz_vpn_monetization` — вся история монетизации, точки показа, экономика, замер
3. этот файл

## 🔴 Деплой (общий клон + активный fleet-агент — ОПАСНО)
- НЕ `git add -u/-A` (сгребёт чужую незакоммиченную работу флота — уже обжигались). Только `git add <файл>` точечно.
- Деплой изолированным worktree от origin/main: `git worktree add -b <br> <dir> origin/main` → правки → `git add vpn-nudge.js app.js` → commit → push → `git worktree remove`.
- Push: `GH_TOKEN=$(gh auth token -u volobuevaleksand7-hue) git push origin HEAD:main` (без `gh auth switch`).
- UI-файлы: `ALLOW_FRONTEND_RELEASE=1 git commit`.
- `python3 agents/build-nav.py` перештампует `?v=` на vpn-nudge.js + app.js (оба в ASSET_RE) — иначе кэш отдаст старый реф.
- Vercel: скопировать `.vercel/project.json` в worktree → `vercel --prod --yes` (аккаунт sergeyramas, git-автодеплой НЕ настроен).
- Проверить на проде: новый href в плашке И в попапе карты + новый текст кнопки.

## Замер после смены
Клики: Метрика-цель `vpn_click` (счётчик 110490245) + Vercel outbound. Продажи RKNoff — в его партнёрке (ref-609952529). Сравнить click→sale с hidemy (0/300).

## Next step
Пересмотреть текст кнопки под ТГ-бота → заменить реф в vpn-nudge.js:7 и app.js:36 → задеплоить через worktree → проверить прод (оба места показа).

## First message
```
Продолжаю npz-tactical-map — смена VPN-партнёрки hidemy → RKNoff. Не начинай пока не скажу.

Прочитай:
1. `docs/agents/SESSION_HANDOFF_2026-07-24_vpn-swap.md`
2. `CLAUDE.md` (git-гигиена НПЗ)

Затем жди мою команду.
```
