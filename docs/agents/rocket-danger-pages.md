# Линия «ракетная опасность &lt;город&gt;» (long-tail SEO)

Региональные страницы под freshness-хвост из брифа: `ракетная опасность <город>`
(Волгоград ~35к, Ульяновск ~30к, Казань ~28к/мес). Воронка на `/radar`.
Нейтральный OSINT-тон (см. `CLAUDE.md`, `sanitize-strikes`) зашит в генератор —
копирайт руками не писать.

## Инструменты

- `agents/gen-rocket-danger.py` — шаблон + словарь `CITIES`. Новый город из
  хвоста = одна запись в `CITIES`, не новый файл.
  - `python3 agents/gen-rocket-danger.py --list` — города, slug, объём.
  - `... <key>` → черновик в `drafts/rocket-danger/`.
  - `... <key> --root` → в корень (для публикации).
  - `... <key> --registry` → строка для `data/seo-topics.jsonl` (тип `region`).
- `agents/publish-rocket-danger.py <key>` — идемпотентная публикация одного
  города: ген в корень → строка в реестр → запись в `sitemap.xml` →
  `build-nav.py` → `check-ia.py` → commit (`ALLOW_FRONTEND_RELEASE=1`) →
  `git pull --rebase --autostash` → `git push`. Есть `--dry-run`.
- `agents/build-nav.py` — подписи/хаб-карточки трёх городов уже добавлены
  (`LABELS`/`HUB`), тип `region` → группа меню «Регионы».

## Автопубликация

Локальная запланированная рутина `npz-rocket-danger-morning-release`
(`~/.claude/scheduled-tasks/`) в **04:00 МСК** ежедневно публикует ОДИН самый
горячий из ещё не выпущенных городов. За несколько утр закрывает весь хвост,
затем простаивает. Выбор города: активность в `data/strikes.json` / свежей
сводке / `api/radar-state` на сегодня; при ничьей — по объёму
(volgograd &gt; ulyanovsk &gt; kazan).

Нюансы механизма: работает пока открыт Claude-app (если закрыт в 04:00 — при
следующем запуске утром); первый прогон может спросить разрешения на Bash —
пре-апрув через «Run now» один раз.

## Ручной фолбэк (если рутина промахнулась)

```
cd ~/Documents/npz-tactical-map
python3 agents/publish-rocket-danger.py volgograd   # или ulyanovsk / kazan
```

Работает только с ЖИВОЙ копией `~/Documents/npz-tactical-map` (не «Alarm NPZ»).
Публиковать по одному городу за раз.
