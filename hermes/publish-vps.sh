#!/usr/bin/env bash
# publish-vps.sh — ПОСТ-пайплайн после волны сбора данных (для Гермеса на VPS).
#
# Коллекторы (agents/run-agent.sh) уже коммитят каждый свой data/*.json сами.
# Этот скрипт делает то, что идёт ПОСЛЕ данных:
#   1) git pull — подтянуть все свежие data-коммиты волны
#   2) регенерировать SEO-раздел /news (agents/gen-news.py) + архив + коммит/пуш
#   3) Telegram: собрать новых подписчиков (poll) + разослать дайджест ТОЛЬКО нового (broadcast)
#
# Секреты (Telegram-токен, подписчики, снапшот) живут в $NPZ_BOT_DIR (по умолчанию
# ~/.npz-bot, вне репозитория). В коде секретов нет.
#
# Использование:  bash hermes/publish-vps.sh
# Ставится в cron ПОСЛЕ окна сбора (см. hermes/crontab.hermes).
set -uo pipefail

# секреты окружения (ANTHROPIC_API_KEY / ключи) — файл ВНЕ репозитория
[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env
[ -f "$HOME/.npz-agent.env" ] && . "$HOME/.npz-agent.env"

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
BOT="$REPO/hermes/bot"
BOT_DIR="${NPZ_BOT_DIR:-$HOME/.npz-bot}"
cd "$REPO" || { echo "no repo at $REPO" >&2; exit 2; }

echo "=== publish-vps $(date -u +%Y-%m-%dT%H:%MZ) ==="

# git pull — НЕ глушим ошибку: рабочее дерево должно быть чистым и в актуальном
# состоянии, прежде чем мы будем что-то коммитить поверх него. Если и rebase,
# и plain pull провалились (конфликт/нет сети), останавливаемся — коммит на
# грязном/расходящемся дереве рискует запушить битые данные.
if ! git pull --rebase --quiet 2>/dev/null && ! git pull --quiet 2>/dev/null; then
  echo "publish-vps: ОШИБКА — git pull не удался (конфликт или нет сети); прерываю, ничего не коммичу" >&2
  exit 3
fi

# 1. Регенерировать news.html (статик для поиска) + архив из свежих данных.
if [ -f agents/gen-news.py ]; then
  echo "publish-vps: регенерирую news.html…"
  if python3 agents/gen-news.py >/dev/null 2>&1; then
    # /refineries: перегенерировать data-блоки + FAQ/JSON-LD из свежего fuel-state.
    # Неблокирующе (|| echo) — если упадёт, публикацию не роняем. Без этого GEN-блоки
    # и FAQ отстают от данных (дрейф FAQ чинили 16.07); теперь /refineries едет тем же
    # коммитом. FAQ/JSON-LD генерятся из данных, разъехаться не могут.
    python3 agents/gen-refineries.py >/dev/null 2>&1 || echo "publish-vps: ⚠ gen-refineries упал — пропускаю"
    # /rabotayut-li-npz-rossii: та же логика, что и /refineries выше — генератор из
    # свежего fuel-state.json, неблокирующе. Без этого статус/дни простоя/FAQ на
    # странице отстают от данных ровно тем же классом дрейфа, что чинили на /refineries.
    python3 agents/gen-npz-status-page.py >/dev/null 2>&1 || echo "publish-vps: ⚠ gen-npz-status-page упал — пропускаю"
    # 🔴 28.08.2026, ЧЕТВЁРТЫЙ рецидив класса «генератор пишет, git add не знает» —
    # но ломалось не то, что раньше: сама страница В списке git add ниже. Беда была
    # в порядке. Генераторы выше перевыпускают страницы из шаблона со СТАРОЙ
    # навигацией (у rabotayut-li-npz-rossii.html падало с 3 вхождений nav-dropdown
    # до 1), а build-nav.py — единственный владелец <header class="news-header"> —
    # здесь не вызывался вовсе. Он дочинивал меню ПОЗЖЕ, отдельным прогоном, и та
    # правка уже никем не коммитилась: файл оставался вечно modified и заклинивал
    # `git pull --rebase` всему флоту. Публикация вставала так дважды за двое суток
    # (26.08 и 28.08), оба раза с осиротевшим стэшем ровно этой страницы.
    #
    # Лечение — вернуть порядок: сгенерировали → сразу привели навигацию к канону →
    # и только потом коммитим. Неблокирующе, как соседи: упавший build-nav не должен
    # ронять публикацию данных.
    #
    # 🔴 И отдельно — почему git add тут по СПИСКУ ФАЙЛОВ, а не по фиксированному
    # перечню имён: build-nav владеет навигацией на ВСЕХ страницах, а перечень ниже
    # знает про четыре. Первый заход этой правки это и показал — build-nav тронул
    # news/2026-08.html и две страницы складов, они остались modified, то есть
    # рецидив просто переехал на другие файлы. Поэтому берём снимок ДО и ПОСЛЕ и
    # добавляем ровно те html, которые сделал грязными сам build-nav. Огульный
    # `git add *.html` тут запрещён: он утащил бы в коммит чужую незакоммиченную
    # правку страницы (ровно тем классом сносили архивы, см. data/).
    _html_before="$(git status --porcelain -- '*.html' 'news/' 2>/dev/null | cut -c4- | sort)"
    python3 agents/build-nav.py >/dev/null 2>&1 || echo "publish-vps: ⚠ build-nav упал — навигация может отстать"
    _html_after="$(git status --porcelain -- '*.html' 'news/' 2>/dev/null | cut -c4- | sort)"
    _nav_touched="$(comm -13 <(printf '%s\n' "$_html_before") <(printf '%s\n' "$_html_after") | grep . || true)"
    if [ -n "$_nav_touched" ]; then
      echo "publish-vps: build-nav обновил навигацию, добавляю в коммит:"
      printf '  %s\n' $_nav_touched
      # shellcheck disable=SC2086 — пути без пробелов, разбиение по словам намеренное
      git add -- $_nav_touched || echo "publish-vps: ⚠ git add навигации не удался" >&2
    fi
    # ВСЕ артефакты gen-news (он внутри зовёт seo/generate-sitemap.py + agents/gen-rss.py):
    # news.html, sitemap.xml, news-sitemap.xml, rss.xml, news/, news-archive.json.
    # Раньше здесь не было news-sitemap.xml/rss.xml — gen-rss переписывал их каждый
    # прогон, но они НЕ коммитились -> вечно modified -> блокировали git-sync всех
    # агентов (pull --rebase на грязном дереве), публикация вставала на часы каждые 6ч.
    # Список синхронен с эталоном в agents/summary-watchdog.py:heal().
    # krupnejshie-npz-rossii.html — вторая RANK_PAGE gen-refineries.py; без неё
    # в git add файл вечно modified → блокирует pull всех агентов (инцидент 17.07).
    # 🔴 09.08.2026, третий рецидив той же грабли: optimize_covers кладёт рядом с
    # cover-*.png лёгкий cover-*.webp (54 КБ против 202 КБ), news.html ссылается
    # именно на него — а в git add был только *.png. Итог: 6 обложек за 03–09.08
    # отдавали 404 на проде, /news неделю показывал битые картинки, а сами файлы
    # копились untracked и роняли `git pull --rebase` всем агентам.
    if ! git add news.html sitemap.xml news-sitemap.xml rss.xml news/ data/news-archive.json assets/cover-*.png assets/cover-*.webp assets/thumb/cover-*.webp refineries.html krupnejshie-npz-rossii.html rabotayut-li-npz-rossii.html 2>/dev/null; then
      echo "publish-vps: ОШИБКА — git add не удался" >&2
      exit 4
    fi
    if ! git diff --cached --quiet 2>/dev/null; then
      if ! git commit -q -m "news: regenerate SEO digest + archive"; then
        echo "publish-vps: ОШИБКА — git commit не удался" >&2
        exit 5
      fi
      if git push origin HEAD:main 2>/dev/null; then
        echo "publish-vps: news обновлён и запушен"
      else
        echo "publish-vps: ОШИБКА — news push не прошёл (проверь git-доступ)" >&2
        exit 6
      fi
    else
      echo "publish-vps: news без изменений"
    fi
  else
    echo "publish-vps: ⚠ gen-news.py упал — пропускаю news"
  fi
fi

# 2. Telegram: poll подписчиков/кнопок + radar-алерты. Редполитика v2 (2026-07-07):
#    editorial_digest/compute_digest БОЛЬШЕ НЕ постят в канал сами — единственные
#    публикаторы канала теперь: broadcast.py --briefing (сводка утро/вечер) и
#    strike_pipeline.py/radar_publish.py (молния TIER1/TIER2). PUBLISH-джоба
#    только собирает подписчиков (poll), гоняет alerts и регенерирует /news —
#    сама в канал НЕ пишет.
if [ -f "$BOT_DIR/token" ] && [ -f "$BOT/broadcast.py" ]; then
  # poll.py убран 2026-07-12: его getUpdates конфликтовал с демоном poll_bot.py за один
  # токен (409). /start, кнопки регионов/таймера И кнопки публикации молнии теперь
  # обрабатывает сам демон в реальном времени (poll_bot.on_publish_callback). Здесь — только alerts.
  echo "publish-vps: Telegram — radar-alerts…"
  NPZ_REPO="$REPO" NPZ_BOT_DIR="$BOT_DIR" python3 "$BOT/radar_alerts.py" --send 2>/dev/null || true
else
  echo "publish-vps: бот не настроен ($BOT_DIR/token нет) — Telegram пропущен"
fi

echo "publish-vps: готово."
