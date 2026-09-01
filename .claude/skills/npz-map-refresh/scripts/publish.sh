#!/usr/bin/env bash
# publish.sh — валидировать изменённые data/*.json, проверить conflict-маркеры,
# затем ОДИН безопасный коммит+пуш через agents/git-sync.sh с правильными
# heartbeat-ключами (вычисляются из списка изменённых файлов).
#
# Использование:  bash publish.sh "<commit message>" [REPO_DIR]
# Запускать ПОСЛЕ того как все агенты записали свои data/*.json.
# Совместимо с bash 3.2 (macOS) — без mapfile / associative arrays.
set -uo pipefail
MSG="${1:?commit message required}"
REPO="${2:-$HOME/Documents/npz-tactical-map}"
cd "$REPO" || { echo "no repo at $REPO" >&2; exit 2; }

# 1. какие data-файлы изменены (по одному имени в строке)
CHANGED="$(git status --porcelain -- data/ | awk '{print $2}' | grep -E '\.json$' || true)"
if [ -z "$CHANGED" ]; then
  echo "publish: нет изменённых data/*.json — нечего пушить."; exit 0
fi
echo "publish: изменены:"; printf '  %s\n' $CHANGED

# 2. валидность JSON каждого
BAD=0
for f in $CHANGED; do
  python3 -c "import json;json.load(open('$f'))" 2>/dev/null || { echo "publish: НЕВАЛИДНЫЙ JSON: $f" >&2; BAD=1; }
done
[ "$BAD" = 1 ] && { echo "publish: ABORT — почини битый JSON выше, потом повтори." >&2; exit 3; }

# 3. guard: conflict-маркеры где-либо в data/
if grep -rnE '^(<<<<<<<|=======|>>>>>>>)' data/ >/dev/null 2>&1; then
  echo "publish: ABORT — conflict-маркеры в data/:" >&2
  grep -rnE '^(<<<<<<<|=======|>>>>>>>)' data/ >&2
  exit 3
fi

# 4. изменённые файлы -> heartbeat-ключи (карта WATCH из healthcheck.py); мониторы (health,
#    strike-confirm, capacity-timeline) heartbeat не имеют — пропускаются.
hb_key() {
  case "$1" in
    strikes.json)           echo strikes ;;
    fuel-state.json)        echo npz-status ;;
    history-crimea.json)    echo history-crimea ;;
    roads.json)             echo roads ;;
    grid-state.json)        echo grid-status ;;
    fuel-availability.json) echo fuel-availability ;;
    fuel-voices.json)       echo fuel-voices ;;
    forecast.json)          echo forecast ;;
    economy.json)           echo economy ;;
    *)                      echo "" ;;
  esac
}
KEYS=""
for f in $CHANGED; do
  k="$(hb_key "$(basename "$f")")"
  [ -n "$k" ] && KEYS="$KEYS $k"
done
KEYS="$(echo $KEYS | xargs 2>/dev/null || true)"   # trim
echo "publish: heartbeat keys = [$KEYS]"

# 5. единый безопасный коммит+пуш данных
bash agents/git-sync.sh "$MSG" "$KEYS" || { echo "publish: git-sync упал — пропускаю пост-хуки." >&2; exit $?; }

# 6. ПОСТ-ХУКИ (после успешной публикации данных)
BOT="$HOME/.claude/skills/npz-map-refresh/bot"

# 6a. Регенерировать SEO-раздел новостей из свежих данных (news.html — статик для поиска).
if [ -f agents/gen-news.py ]; then
  echo "publish: регенерирую news.html…"
  python3 agents/gen-news.py >/dev/null 2>&1 && \
    git add news.html sitemap.xml news/ data/news-archive.json assets/cover-*.png 2>/dev/null && \
    git commit -q -m "news: regenerate SEO digest + archive" 2>/dev/null && \
    git push origin HEAD:main 2>/dev/null && echo "publish: news.html + архив обновлены и запушены" || echo "publish: news без изменений/не запушен"
  echo "publish: ⚠ news.html и правки сайта live только после Vercel-деплоя (vercel --prod) — data-слои live сразу через GitHub raw."
fi

# 6b. Telegram-дайджест подписчикам (только НОВОЕ). Тихо пропустить, если бот не настроен.
if [ -f "$HOME/.npz-bot/token" ] && [ -f "$BOT/broadcast.py" ]; then
  echo "publish: Telegram — сбор подписчиков + рассылка дайджеста…"
  NPZ_REPO="$PWD" python3 "$BOT/poll.py" 2>/dev/null || true
  NPZ_REPO="$PWD" python3 "$BOT/broadcast.py" 2>/dev/null || true
fi
