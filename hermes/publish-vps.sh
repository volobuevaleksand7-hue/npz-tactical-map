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
    if ! git add news.html sitemap.xml news/ data/news-archive.json assets/cover-*.png 2>/dev/null; then
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
