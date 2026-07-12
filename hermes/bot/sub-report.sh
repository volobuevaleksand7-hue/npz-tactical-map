#!/usr/bin/env bash
# sub-report.sh — счётчик активных подписчиков @BPLAlert_bot → владельцу через бот-отправитель.
# Шлёт ТОЛЬКО при изменении числа (водяной знак sub-report-last.txt), чтобы не спамить каждые 4ч.
# env: NPZ_BPL_DIR (канон-папка), NPZ_REPORT_CHAT (кому), NPZ_REPORT_TOKEN (файл токена отправителя).
set -uo pipefail

BPL_DIR="${NPZ_BPL_DIR:-/root/.npz-bot-bpl}"
SUBS="$BPL_DIR/subscribers.json"
STATE="$BPL_DIR/sub-report-last.txt"
REPORT_CHAT="${NPZ_REPORT_CHAT:-609952529}"
REPORT_TOKEN_FILE="${NPZ_REPORT_TOKEN:-/root/.npz-bot/token}"

[ -f "$SUBS" ] || { echo "sub-report: нет $SUBS"; exit 0; }
[ -f "$REPORT_TOKEN_FILE" ] || { echo "sub-report: нет токена отправителя"; exit 0; }

N=$(python3 -c "import json;print(sum(1 for v in json.load(open('$SUBS'))['subscribers'].values() if v.get('status')=='active'))") || exit 0
LAST=$(cat "$STATE" 2>/dev/null || echo "")

if [ "$N" = "$LAST" ]; then
  echo "sub-report: без изменений ($N)"
  exit 0
fi

TOK=$(cat "$REPORT_TOKEN_FILE")
MSK=$(TZ=Europe/Moscow date '+%d.%m %H:%M МСК')
if curl -sf "https://api.telegram.org/bot$TOK/sendMessage" \
      --data-urlencode "chat_id=$REPORT_CHAT" \
      --data-urlencode "text=📊 @BPLAlert_bot: $N активных подписчиков · $MSK" \
      -d disable_web_page_preview=true >/dev/null; then
  echo "$N" > "$STATE"
  echo "sub-report: отправлено ($LAST→$N)"
else
  echo "sub-report: отправка не удалась, водяной знак не двигаю"
fi
