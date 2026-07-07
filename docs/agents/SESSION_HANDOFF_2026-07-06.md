# Handoff — npz-tactical-map — 2026-07-06

## Status
Новостной раздел `/news` = полноценный сайт-архив (индекс-лента + страница на каждый день +
`data/news-archive.json` + обложки город+подпись + баланс как на карте). Всё задеплоено.
Обложки: **30/30 дат готовы** (последние 2 добил Hermes-VPS). Данные карты свежие на 05.07.

## Read first (in order)
1. `docs/news-pipeline.md` — весь конвейер обновления новостей+обложек простыми словами
2. `~/.claude/skills/npz-map-refresh/SKILL.md` — как запускать refresh + covers (скилл «обнови новости»)
3. `CLAUDE.md` — правила проекта
4. auto-memory `npz-cover-image-style` — стиль обложек (НЕ мрачно; город+подпись)

## In-session decisions
- **Обложки:** реальное фото события (`og:image` из `source_url` лид-удара) → img2img через
  `codex exec image_gen` → подпись `agents/caption_cover.py` (Pillow). Нет годного фото → генерация по тексту.
  Скрипт: `scripts/build-covers.py --missing|--all|--dates`.
- **Баланс в /news** обогащён до уровня карты: 31% · ~104/336 млн т/год · недобор 47% ·
  спарклайн 18→26% (`capacity-timeline.json`) · чипы 8/9/15 (`refineries[]`). Правка в `agents/gen-news.py`.
- **Cache-busting** `?v=<хэш>` на css в `gen-news.py` — иначе браузер держит старый CSS (был «вырви глаз»).
- **Codex image_gen** упирается в ~14 картинок/аккаунт («out of credits»). Меняешь аккаунт → добиваешь.
- `codex:codex-rescue` для картинок капризничает — зови `codex exec` напрямую.

## Watch out
- Параллельно работает **Hermes на VPS** (cron: /news + Telegram-дайджест, см. коммиты `76745c8`,
  `ac28ca1`). `caption_cover.py` теперь кросс-платформенный (Mac Arial / VPS Liberation Sans) — не ломать.
- Незакоммичены (НЕ мои, не трогать без спроса): `index.html`, `styles.css`, `agents/update-prompt-voices.md`.

## Next step
Ждать команду. Типовое: «обнови новости» → скилл `npz-map-refresh` (assess → агенты по слоям →
verify → build-covers → publish.sh → gen-news → `vercel --prod` → Telegram).

## First message
```
Продолжаю npz-tactical-map. Не начинай пока не скажу.

Прочитай:
1. docs/agents/SESSION_HANDOFF_2026-07-06.md
2. docs/news-pipeline.md

Затем запусти скилл npz-map-refresh и жди мою команду.
```
