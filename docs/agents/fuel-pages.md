# Топливная ветка SEO-страниц

Страницы из брифа: `/benzin-na-trasse` («бензин на трассе»), `/gde-dizel`
(«где дизель»). Тип `explainer` → группа меню «Объяснялки». Воронка на карты
(`/`, `/karta-benzina-krym`) и `/deficit`. Нейтральный тон, «оценка, не гарантия
наличия» — зашито в генератор, копирайт руками не писать.

## Инструменты

- `agents/gen-fuel-pages.py` — шаблон news.css-лендинга + словарь `PAGES`
  (title/desc/kw/hero/секции/FAQ на страницу). Новая топливная страница = запись
  в `PAGES`.
  - `--list` · `<key>` (черновик в `drafts/fuel/`) · `<key> --root` ·
    `<key> --registry` (строка для реестра).
- `agents/publish-fuel-pages.py <key> | --all [--dry-run]` — идемпотентная
  публикация: ген в корень → реестр → sitemap → build-nav → check-ia →
  commit(`ALLOW_FRONTEND_RELEASE=1`) → rebase → push.
- `build-nav.py` — подписи/хаб-карточки уже добавлены.

## Автопубликация

Локальная рутина `npz-fuel-pages-morning-release` (`~/.claude/scheduled-tasks/`)
в **08:00 МСК** ежедневно: `publish-fuel-pages.py --all` — публикует все
невыпущенные, затем простаивает. Нюансы механизма те же, что у
[[rocket-danger-pages]]: работает пока открыт app (иначе при следующем запуске),
первый прогон может спросить Bash-разрешения.

## Ручной фолбэк

```
cd ~/Documents/npz-tactical-map
python3 agents/publish-fuel-pages.py --all
```

Только ЖИВАЯ копия `~/Documents/npz-tactical-map` (не «Alarm NPZ»).
