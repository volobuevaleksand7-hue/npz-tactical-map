# Handoff — npz-tactical-map — 2026-07-10

## Status
АЗС-линия статей запущена (1 live, 2 по расписанию). Обложки сводок ЗАБЛОКИРОВАНЫ — все
image-бэкенды мертвы, ждём ключ OpenRouter. Инфра публикации переведена на изолированный worktree.

## Read first (in order)
1. `docs/agents/SESSION_HANDOFF_2026-07-09-seo.md` — предыдущий контекст SEO/git-safety
2. Skill `npz-map-refresh` + `HERMES.md` §0 (протокол координации, несколько сессий в одном дереве)
3. `CLAUDE.md` + auto-memory `npz-publish-clean-worktree-recipe`, `npz-cover-image-style`

## Открытые items (главное)
- **🔴 Обложки — блокер.** 08:00-бриф переиспользовал старую cover-2026-07-09 (Тверь, драм.закат):
  за 10.07 обложки/брифа нет (0 ударов). ВСЕ image-бэкенды сдохли: Codex `image_gen` (out of
  credits), Gemini image (429, free-tier квота=0 — и ключ `AQ.A…`, и ротация 6 акк.), OpenRouter
  (ключа нет). Построен `~/.claude/skills/npz-map-refresh/scripts/gen-cover-openrouter.py` (nano-banana
  через OpenRouter → PNG → caption_cover → деплой), синтаксис ОК, ЖДЁТ ключ.
  **Разблокировка:** ключ в `~/.openrouter/api_key` (или env `OPENROUTER_API_KEY`), ЛИБО пополнить
  Codex-кредиты (тогда штатный `build-covers.py`). Затем: перегенерить Тверь-9.07 в ДНЕВНОЙ палитре +
  подпись + `vercel`/CI-деплой.
- **АЗС-статьи (новая линия `agents/azs-pages.py`, отдельно от gen-fuel-pages — чтобы fuel-morning
  `--all` их не сгребал).** `/gde-est-benzin` — ✅ live. `/zakrytye-azs` (14:00 МСК) и
  `/ocheredi-na-azs` (18:00 МСК) — разовые задачи через обёртку. **Проверить, что вышли 200**;
  если задача запнулась на approval — нажать «Run now» разок. Контент прошёл ревью Codex+MiMo.

## In-session decisions
- **Публикация ТОЛЬКО через `~/.claude/scripts/npz-publish-safe.sh`** (чистый worktree на origin/main;
  грязь общего дерева больше не блокирует). Ежедневные rocket/fuel-morning уже переведены на неё.
- **Push-auth:** osxkeychain протухает → пуш токеном `gh auth token -u volobuevaleksand7-hue`
  (inline-helper; репо публичный, fetch анонимный). Отражено в `npz-publish-clean-worktree-recipe`.
- **Внешние модели:** Gemini квота=0, DeepSeek 402 (нет баланса), Codex image=0 кредитов. Живы для
  ревью текста: Codex (`codex:codex-rescue`), MiMo (`mimo-sub`).

## Next step
Проверить, появился ли `~/.openrouter/api_key`. Если да — перегенерить обложку Тверь-9.07 (дневная
палитра) через `gen-cover-openrouter.py` + деплой. Плюс проверить, что АЗС-статьи 14:00/18:00 вышли 200.

## First message
```
Продолжаю npz-tactical-map. Не начинай пока не скажу.

Прочитай по порядку:
1. `docs/agents/SESSION_HANDOFF_2026-07-10.md`
2. `HERMES.md` §0 (протокол координации) + верх `AGENT_ACTIVITY.md`
3. `CLAUDE.md`

Главное: обложки заблокированы (нет image-бэкенда) — жду ключ OpenRouter в `~/.openrouter/api_key`;
публикация только через `~/.claude/scripts/npz-publish-safe.sh`.

Жди мою команду.
```
