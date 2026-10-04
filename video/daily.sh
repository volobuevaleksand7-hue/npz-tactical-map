#!/usr/bin/env bash
# Ежедневный конвейер ролика (cron на Гермесе): рендер -> загрузка на YouTube -> очистка.
#   ./daily.sh [YYYY-MM-DD]   — без даты берётся последняя сводка
# Загрузка пропускается, если нет OAuth-секретов (~/.config/npz-youtube, см. upload.py);
# очистка идёт всегда — залитые mp4 удаляются, незалитых хранится 7 последних.
set -uo pipefail
VIDEO="$(cd "$(dirname "$0")" && pwd)"
cd "$VIDEO"
rc=0
DATE="${1:-$(python3 build.py latest)}"
TOKEN="${NPZ_YT_SECRETS:-$HOME/.config/npz-youtube}/token.json"
./render.sh "$DATE" || rc=$?
if [ -f "$TOKEN" ]; then
  python3 upload.py || rc=$?   # без даты — заодно дольёт пропущенные раньше
else
  echo "daily: нет токена YouTube — загрузка пропущена"
fi
# реестр data/videos.json (ссылки на ролики со страниц /news) — общим безопасным синком данных
if [ -n "$(git -C .. status --porcelain -- data/videos.json)" ]; then
  (cd .. && bash agents/git-sync.sh "data(video): реестр роликов YouTube") || rc=$?
fi
bash ./cleanup.sh || rc=$?
exit $rc
