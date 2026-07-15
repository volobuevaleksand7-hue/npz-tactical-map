# Handoff — npz-tactical-map — 2026-07-15

## Status
Обложки/сводки на автопилоте (Codex-цепочка + самолечащий сторож), `/npz/kinef` опубликован, W28-baseline готов и его главная рекомендация (реопт `/refineries`) уже закрыта другой сессией 14.07; осталось: **диск VPS 99%**, засорённый трекер позиций, следующая НПЗ-страница, W29-отчёт.

## Read first (in order)
1. auto-memory (инжектится сама): `npz-summary-cover-race-and-watchdog`, `feedback-npz-covers-via-codex`, `npz-openrouter-key-location`, `npz-publish-clean-worktree-recipe`, `npz-seo-agent-system`
2. `docs/agents/seo/reports/2026-W28.md` — baseline аналитики + назначения оркестратору
3. `CLAUDE.md` + `docs/seo-playbook.md` — правила проекта
4. Origin main — источник истины (дерево Мака ресетится git-sync и контестится параллельной сессией)

## In-session decisions
- **Самолечение вместо инцидент-инбокса:** детектор без исполнителя бесполезен — `docs/agents/incidents.md` в кроне никто не читает (отвергнуто: ждать полной сессии Гермеса по HERMES.md §0 — такой рутины нет). Сторож `agents/summary-watchdog.py` теперь сам собирает карточку+обложку и пушит; cron 8:15/20:15 МСК.
- **Обложки Codex-first цепочкой** (`NPZ_COVER_BACKENDS`, деф. `codex-vps,codex-local,openrouter`): OpenRouter стоял первым и сожрал весь $10-лимит ключа (отвергнуто: поднять кап — платно и не нужно, Codex бесплатен). С Мака `codex-vps` идёт по ssh на VPS. Отключить платный: `NPZ_COVER_BACKENDS="codex-vps,codex-local"`.
- **VPS Codex 0.142.5 → 0.144.0:** старый CLI не тянул модель `gpt-5.6-terra` из `~/.codex/config.toml` → обложки на VPS не рисовались.
- **Правки/публикация только через чистый git worktree на origin/main:** общее дерево Мака контестится параллельной сессией, правки откатывались на лету (отвергнуто: править в общем дереве).

## Открытые проблемы (по приоритету)
1. 🔴 **Диск VPS 99%** (336M своб. из 19G). Уронил commit/push сторожа 14.07 (`OSError: [Errno 28] No space left` → `git-sync: ABORT`). Пожиратели: `/root/.nvm` 3.3G, `/root/hermes-stack` 2.2G, `/root/.cache` 867M, `/root/.npm` 551M. Ничего не удалялось — решение за владельцем.
2. 🔴 **Трекер позиций засорён:** `data/yandex-positions.json` снова меряет `обслуживание итп` (чужой logika-itp). VPS-скрипт `~/.hermes/scripts/yandex-position-check.py` читает не тот список; фикс (`data/position-queries.json`, a3187d7) перезатёрт. Позиции для W28 брались напрямую из Вебмастер API.
3. Следующая объектная НПЗ-страница — **Новокуйбышевский** (далее Афипский/Славянский/Новошахтинский). ТАИФ-НК тонкая — кандидат на замену.
4. **W29-отчёт** аналитика (недельный цикл запущен W28-baseline).

## Next step
Разобраться с диском VPS 99% (уже ронял пуш сторожа), затем публиковать НПЗ-страницу Новокуйбышевского через worktree-рецепт.

## First message
```
Продолжаем npz-tactical-map. Не начинай пока не скажу.

Прочитай:
1. `docs/agents/SESSION_HANDOFF_2026-07-15.md`
2. `docs/agents/seo/reports/2026-W28.md`

Приоритеты: 1) диск VPS 99% (336M своб. из 19G — уже уронил commit/push сторожа сводок 14.07; пожиратели /root/.nvm 3.3G, /root/hermes-stack 2.2G, /root/.cache 867M, /root/.npm 551M) — разведать и предложить безопасную чистку; 2) НПЗ-страница Новокуйбышевского через чистый worktree; 3) переключить VPS yandex-position-check.py на data/position-queries.json (трекер засорён чужими «итп»-запросами); 4) W29-отчёт аналитика.

Жди мою команду.
```
