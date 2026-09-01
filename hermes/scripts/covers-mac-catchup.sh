#!/usr/bin/env bash
# Догон обложек с МАКА. Запускается по расписанию launchd, см. заголовок ниже.
#
# 🔴 Зачем отдельный скрипт на Маке, хотя сводки собирает сторож на VPS:
# на hermes у Codex ОТОЗВАН OAuth-токен ("code": "token_revoked", проверено
# 01.09.2026 прямым вызовом). Для сторожа, живущего на VPS, оба звена цепочки
# build-covers — codex-vps и codex-local — это одна и та же разлогиненная
# машина, поэтому никакой фолбэк ВНУТРИ VPS дыру не закрывает: он либо рисует
# типографику через PIL, либо пишет «долг». Единственный живой Codex — на Маке.
#
# Пока на VPS не сделают `codex login` заново (или не дадут API-ключ через
# `codex login --with-api-key`), фотообложки делает эта задача.
#
# ponytail: тонкая обёртка над build-covers --missing, своей логики нет.
set -uo pipefail

REPO="${NPZ_REPO:-$HOME/Documents/npz-tactical-map}"
LOG="$REPO/agents/logs/covers-mac.log"
cd "$REPO" || exit 1
mkdir -p "$(dirname "$LOG")"

say() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M')" "$*" >> "$LOG"; }

# Ничего не делаем на грязном дереве: чужая незакоммиченная работа важнее обложек.
if [ -n "$(git status --porcelain -- . 2>/dev/null | grep -v '^?? ')" ]; then
  say "SKIP: дерево грязное, не лезу"; exit 0
fi

git fetch --quiet origin && git reset --quiet --hard origin/main || { say "SKIP: git не синкнулся"; exit 0; }

# Codex жив? Дешёвая проба до генерации — иначе намолотим GENFAIL впустую.
if ! codex login status >/dev/null 2>&1; then
  say "SKIP: codex не авторизован на этой машине"; exit 0
fi

out="$(NPZ_COVER_BACKENDS=codex-local python3 hermes/scripts/build-covers.py --missing 2>&1)"
ok="$(printf '%s\n' "$out" | grep -c '^OK ')"
fail="$(printf '%s\n' "$out" | grep -c '^GENFAIL')"
say "build-covers: ok=$ok genfail=$fail"
printf '%s\n' "$out" | grep -E '^OK |^GENFAIL' >> "$LOG"

[ "$ok" -eq 0 ] && exit 0

python3 agents/optimize_covers.py >/dev/null 2>&1
python3 agents/gen-news.py        >/dev/null 2>&1

git add assets/ news.html news/ rss.xml sitemap.xml news-sitemap.xml data/news-archive.json 2>/dev/null
git diff --cached --quiet && { say "нечего коммитить"; exit 0; }

ALLOW_FRONTEND_RELEASE=1 git -c user.name="npz-agent" -c user.email="agent@npz.local" \
  commit -q -m "assets: обложки догнаны с Мака (codex), дат: $ok" || { say "коммит не прошёл"; exit 1; }

git fetch --quiet origin && git rebase --quiet origin/main || { say "ребейз не прошёл"; exit 1; }
GH_TOKEN="$(gh auth token -u volobuevaleksand7-hue)" \
  git -c credential.helper= -c credential.helper='!gh auth git-credential' \
  push --quiet origin HEAD:main && say "запушено: $ok обложек" || say "push не прошёл"
