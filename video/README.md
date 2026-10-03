# video/ — ежедневный ролик-сводка (HyperFrames)

Вертикальный ролик 1080×1920, 13–20 с: обложка сводки → число ударов за сутки →
карточки ударов по НПЗ/энергетике → источник (адрес сводки + плашка «ОЦЕНКА»).
Каталог исключён из деплоя Vercel (`.vercelignore`) — на сайт не публикуется.

## Откуда данные (ничего не захардкожено)

| Что | Источник |
|---|---|
| дата по умолчанию | последний `news/YYYY-MM-DD.html` |
| число ударов, «N по НПЗ/энергетике», заголовок дня | `data/news-archive.json` → `briefs[<дата>].strikes`, классификация — функции `agents/gen-news.py` (те же, что у страницы `/news/<дата>`) |
| карточки | удары по НПЗ/энергетике с `confidence` confirmed/reported (слухи не показываем), порядок — `strike_rank` из gen-news, дубли одного объекта склеены; мощность — `data/fuel-state.json` → `refineries[]` |
| обложка | `assets/cover-<дата>.png` (или `-restored`), нет — общая `og-image.png`, как на сайте |

Карточек 0..N: при 0 сцена с карточками пропускается (ролик короче), при 1–3 — все,
при >3 — топ-3 и строка «и ещё K объектов».

## Рендер

```bash
cd video
npm ci                      # один раз (hyperframes + gsap, ~130 МБ в node_modules)
./render.sh                 # последняя сводка
./render.sh 2026-09-26      # конкретная дата
# -> video/out/npz-<дата>.mp4
```

Рендер офлайн: шрифты лежат в `template/assets/fonts`, GSAP берётся из `node_modules`,
телеметрия и проверки обновлений HyperFrames выключены переменными в `render.sh`.
Переменные: `HF_WORKERS` (по умолчанию `auto`; на машинах ≤8 ГБ HyperFrames сам
уходит в low-memory режим с 1 воркером), `HF_QUALITY` (`draft|looks|delivery`).

### По умолчанию — Hermes (hermes-vps)

Каждый день по cron (строка в `crontab -l`, ищи `video/render.sh`), после вечерней
публикации сводки; лог — `agents/logs/video.log`. Шаблон приезжает на сервер через
ежечасный `git pull` клона `/root/npz-tactical-map`. Chromium для рендера ставится
`npx hyperframes browser ensure` (кэш в `~/.cache/hyperframes`).

Забрать ролик на Мак:

```bash
scp hermes-vps:/root/npz-tactical-map/video/out/npz-<дата>.mp4 .
```

Перерендерить вручную на сервере:

```bash
ssh hermes-vps 'cd /root/npz-tactical-map/video && ./render.sh 2026-10-03'
```

### Мак — запасной/срочный путь

Тот же `./render.sh` в `~/Documents/npz-tactical-map/video` (нужны node, ffmpeg,
python3; Chrome HyperFrames скачает при первом `npx hyperframes browser ensure`).
На M-серии ~20–50 с на ролик.

## Звук

- Эффекты синтезированы ffmpeg-ом (`sfx/make-sfx.sh`, ничего не скачивается):
  `whoosh.wav` — смена сцены, `impact.wav` — появление цифры, `click.wav` — карточки.
- **Музыка:** положите файлы (`mp3/m4a/aac/wav/ogg/opus/flac`) в `video/music/` на той
  машине, где идёт рендер (на Hermes — `scp трек.mp3 hermes-vps:/root/npz-tactical-map/video/music/`).
  Трек выбирается по дате (тот же день — тот же трек), зацикливается под длину ролика,
  идёт на −10 дБ, приседает под эффекты (sidechain), fade in 1,2 с / fade out 1,8 с.
  Папка пустая — в ролике только эффекты. В git музыка не коммитится (публичный репо и
  права на треки) — `.gitignore` пропускает только `music/.gitkeep`.

## Хранение роликов

**Залитый ролик удаляется; хранится только то, что ещё не загружено, но не больше 7 штук.**

`cleanup.sh` (вызывается в cron сразу после рендера):

1. если рядом с `out/npz-<дата>.mp4` лежит маркер `out/npz-<дата>.uploaded` — mp4
   удаляется, маркер **остаётся** (по нему будущий загрузчик видит, что дата уже
   залита, и не зальёт повторно), факт пишется в `out/uploaded.log`;
2. страховка, пока загрузчика нет: из оставшихся `npz-YYYY-MM-DD.mp4` хранятся 7 самых
   свежих по дате (`KEEP=7`).

Маркер пишет загрузчик (следующий этап) только после успешной загрузки; содержимое —
любое (например, id ролика), первые 300 байт попадают в `uploaded.log`.

## Файлы

- `template/index.html` — композиция с плейсхолдерами `{{…}}`, стили и GSAP-таймлайн
- `build.py` — `compose` (данные → `.build/<дата>/`), `mix` (звук), `latest`
- `render.sh` — одна команда на ролик; `cleanup.sh` — хранение
- `sfx/` — эффекты + скрипт синтеза; `music/` — слот под музыку (не в git)
