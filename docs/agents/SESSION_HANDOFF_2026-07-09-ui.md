# Handoff — npz-tactical-map (UI/PWA line) — 2026-07-09

## Status
UI-сессия завершена и в проде: **v1.9.0** (PWA + 5 обложек /analytics + попапы не под тулбаром + русские даты). Ранее в этой же сессии — v1.8.0 (аудит AntiGravity: тикер→карусель, Крым заливка+91 АЗС+сводка, зум bottom-right, ARIA, время МСК, баланс «+57% недобор», мигающая лампа, скелетоны). Осталось: **push-уведомления PWA (фаза 2)**.
> Примечание: есть ВТОРОЙ хендофф `SESSION_HANDOFF_2026-07-09.md` — это ДРУГАЯ (SEO/воронки) сессия, шарящая тот же репо.

## Read first (в порядке)
1. `CLAUDE.md` — правила, ОСОБЕННО новый раздел «Общее рабочее дерево — координация»
2. `AGENT_ACTIVITY.md` + `CHANGELOG.md` — верхние записи 1.9.0/1.8.0 (что и почему)

## In-session decisions (не всё в файлах)
- **Codex работает через `/opt/homebrew/bin/codex`** (npm-обёртка `~/.local/bin/codex` битая: нет `@openai/codex-darwin-arm64`). Обложки: `codex exec --dangerously-bypass-approvals-and-sandbox "…image_gen… save to assets/…"` + `sips -z 675 1200` для 1200×675.
- **Клоббер 3× за сессию:** параллельная (SEO) сессия гоняла ручной `git pull --rebase --autostash` → autostash сносил мои незакоммиченные `app.js`/`index.html`/`analytics.html`. Восстанавливал из `stash@{0}`, коммитил сразу. Правило — в CLAUDE.md. Мораль: свои файлы коммить СРАЗУ; долгую UI-работу — в `git worktree` на ветку.
- **Баланс 35% верен** (115.8/335.6, выбито полностью) + добавлен «недобор ~57%» из `throughput_shortfall_pct`.
- **MiMo сорвался** (0 файлов) → PWA собрал оркестратор сам. DeepSeek-Flash — радар-кластеризация (в 1.8.1). Claude-сабагент — попапы.

## Next step
Фаза 2 — **push в PWA**: VAPID-ключи + `push`/`notificationclick` в `sw.js` (там уже TODO-стаб), минимальный push-сервер на Hermes VPS (рядом с `poll.py`), UI-подписка на карте. Плюс проверить, что фоновая `task_25c28fa9` (даты gridPopup/blackoutPopup → rusDate) долетела в `app.js`.

## First message
```
Продолжаю npz-tactical-map (UI/PWA). Не начинай пока не скажу.

Прочитай:
1. `docs/agents/SESSION_HANDOFF_2026-07-09-ui.md`
2. `CLAUDE.md` — раздел про координацию общего дерева (репо шарится с другой сессией — свои правки коммить сразу)

Задача на старт — фаза 2: push-уведомления в PWA (Web Push + VAPID; `sw.js` уже со стабом; сервер на Hermes VPS рядом с poll.py). Сначала предложи план. Жди мою команду.
```
