#!/usr/bin/env python3
"""Одно сообщение владельцу о ready-кандидатах (после validate-events.py).

  notify.py [--dry-run] [--queue P] [--max 8]

Токен: env NPZ_BOT_TOKEN -> ~/.npz-bot/token; чат: env NPZ_OWNER_CHAT (по умолчанию
609952529). Отправляет кандидатов без notified_at и ставит notified_at только после
успешной отправки. send(text) -> bool вынесена для подмены в тестах.
"""
import argparse
import hashlib
import inspect
import os
import sys
import urllib.parse
import urllib.request
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

OWNER_DEFAULT = "609952529"
REGION_RU = {"europe": "Европа", "russia_cis": "Россия и СНГ", "middle_east": "Ближний Восток",
             "east_asia": "Восточная Азия", "south_asia": "Южная Азия",
             "north_america": "Северная Америка", "latin_america": "Латинская Америка",
             "africa": "Африка"}


def short_id(cid):
    """Короткий хэш id для callback_data (лимит Telegram 64 байта): wev:a:<10 hex>."""
    return hashlib.sha1(str(cid).encode()).hexdigest()[:10]


def build_markup(cands):
    """Inline-клавиатура: по строке на кандидата, кнопки с порядковым номером."""
    rows = []
    for i, c in enumerate(cands, 1):
        h = short_id(c["id"])
        rows.append([{"text": f"\u2705 Одобрить {i}", "callback_data": f"wev:a:{h}"},
                     {"text": f"\u274c Отклонить {i}", "callback_data": f"wev:r:{h}"}])
    return {"inline_keyboard": rows}


def tg_send(text, markup=None):
    token = os.environ.get("NPZ_BOT_TOKEN", "").strip()
    if not token:
        p = Path.home() / ".npz-bot" / "token"
        token = p.read_text().strip() if p.exists() else ""
    if not token:
        print("notify: нет токена бота, сообщение не отправлено", file=sys.stderr)
        return False
    chat = os.environ.get("NPZ_OWNER_CHAT", OWNER_DEFAULT).strip()
    fields = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
    if markup:
        fields["reply_markup"] = json.dumps(markup)
    data = urllib.parse.urlencode(fields).encode()
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return bool(json.load(r).get("ok"))
    except Exception as e:  # noqa: BLE001
        print(f"notify: ошибка отправки: {e}", file=sys.stderr)
        return False


def pending(queue, limit=8):
    return [c for c in queue.get("candidates", [])
            if c.get("verdict") == "ready" and not c.get("notified_at")][:limit]


def format_message(cands, total_pending=None):
    lines = ["Здравствуйте, Сергей. Это ИИ-ассистент. "
             f"Кандидатов в события /lab/world, прошедших проверку: {len(cands)}."]
    for i, c in enumerate(cands, 1):
        lines.append("")
        lines.append(f"{i}. {c['id']}")
        lines.append(f"{REGION_RU.get(c.get('region'), c.get('region'))} | {c.get('occurred_at')} | {c.get('status')}")
        lines.append(str(c.get("title")))
        for s in c.get("sources", []):
            lines.append(f"  {s.get('publisher')}: {s.get('url')}")
    lines.append("")
    lines.append("Кнопки ниже: Одобрить N / Отклонить N.")
    if total_pending and total_pending > len(cands):
        lines.append("")
        lines.append(f"Ещё в очереди: {total_pending - len(cands)}, придут следующим сообщением.")
    return "\n".join(lines)


def run(queue, send, limit=8, dry=False):
    """-> (отправлено: int, текст|None). Мутирует queue (notified_at) только при успехе."""
    allp = pending(queue, 10 ** 6)
    cands = allp[:limit]
    if not cands:
        return 0, None
    text = format_message(cands, len(allp))
    if dry:
        return 0, text
    markup = build_markup(cands)
    try:
        two = len(inspect.signature(send).parameters) >= 2
    except (TypeError, ValueError):
        two = False
    if send(text, markup) if two else send(text):
        now = C.now_iso()
        for c in cands:
            c["notified_at"] = now
        return len(cands), text
    return 0, text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--queue", default=C.QUEUE)
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args(argv)
    q = C.load_json(a.queue, {"candidates": []})
    n, text = run(q, tg_send, min(a.max, 8), a.dry_run)
    if text is None:
        print("notify: нечего слать")
        return 0
    if a.dry_run:
        print(text)
        print(json.dumps(build_markup(pending(q, a.max)), ensure_ascii=False))
        return 0
    if n:
        C.write_json_atomic(a.queue, q)
    print(f"notify: отправлено {n}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
