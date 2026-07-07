#!/usr/bin/env bash
# setup.sh — идемпотентная подготовка VPS Гермеса к работе карты.
# Проверяет зависимости, секреты и auth; НЕ ставит crontab автоматически
# (крон включается вручную после подтверждения auth — см. HERMES.md §Auth).
#
# Использование:  bash /root/npz-tactical-map/hermes/setup.sh
set -uo pipefail
REPO="${NPZ_REPO:-/root/npz-tactical-map}"
cd "$REPO" || { echo "no repo at $REPO" >&2; exit 2; }
[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env

ok(){ printf "  \033[32m✔\033[0m %s\n" "$1"; }
bad(){ printf "  \033[31mx\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33m•\033[0m %s\n" "$1"; }

echo "== Hermes VPS setup / healthcheck =="

echo "[1] Системные зависимости"
for c in git python3 claude jq curl; do command -v "$c" >/dev/null 2>&1 && ok "$c: $(command -v $c)" || bad "$c ОТСУТСТВУЕТ"; done

echo "[2] Python Pillow (для обложек/карточек бота)"
if python3 -c "import PIL" 2>/dev/null; then ok "Pillow есть"; else
  warn "Pillow нет — ставлю…"; pip3 install --quiet --break-system-packages Pillow 2>/dev/null || pip3 install --quiet Pillow 2>/dev/null
  python3 -c "import PIL" 2>/dev/null && ok "Pillow установлен" || bad "Pillow не установился — поставь вручную: pip3 install Pillow"
fi

echo "[3] Аутентификация Claude headless"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then ok "ANTHROPIC_API_KEY задан в окружении";
else
  # быстрый smoke-тест OAuth-логина
  if echo "reply with the single word PONG" | claude -p --model claude-haiku-4-5-20251001 2>/dev/null | grep -qi pong; then
    ok "claude залогинен (OAuth), headless работает"
  else
    bad "claude НЕ залогинен и нет ANTHROPIC_API_KEY — Гермес не сможет собирать данные."
    warn "Почини: впиши ANTHROPIC_API_KEY в /root/.npz-agent.env  ЛИБО  запусти 'claude' и '/login'"
  fi
fi

echo "[4] Секреты / бот"
[ -s /root/.npz-bot/token ] && ok "Telegram-токен на месте (/root/.npz-bot/token)" || warn "нет /root/.npz-bot/token — рассылка выключится"
[ -s ~/.tavily/api_key ] && ok "Tavily-ключ на месте" || warn "нет ~/.tavily/api_key — веб-фолбэк без Tavily"

echo "[5] Свежесть слоёв (assess)"
bash hermes/scripts/assess.sh "$REPO" 2>/dev/null | sed 's/^/  /' || warn "assess не отработал"

echo
echo "== Готово. Когда [3] зелёный — включи крон:"
echo "   crontab $REPO/hermes/crontab.hermes && crontab -l"
