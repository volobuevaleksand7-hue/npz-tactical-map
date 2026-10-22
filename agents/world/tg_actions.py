#!/usr/bin/env python3
"""Обработка кнопок «Одобрить / Отклонить» (callback_data wev:a|r:<hash>) для /lab/world.

Чистая логика без Telegram: handle(data, from_id) -> (toast, result_line|None, approved).
Вызывается из hermes/bot/poll_bot.py (единственный потребитель getUpdates токена бота).
approve/reject идут через approve.py под flock npz-world.lock; после одобрения
trigger_news() асинхронно запускает run-news.sh (выпуск «Всемирных новостей» + git-sync).
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _common as C  # noqa: E402

OWNER = os.environ.get("NPZ_OWNER_CHAT", "609952529").strip()
LOCK = "/var/lock/npz-world.lock"


def short_id(cid):
    return hashlib.sha1(str(cid).encode()).hexdigest()[:10]


def parse(data):
    """'wev:a:<h>' -> ('a'|'r', h) или None."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "wev" or parts[1] not in ("a", "r") or not parts[2]:
        return None
    return parts[1], parts[2]


def find(queue, h):
    for c in queue.get("candidates", []):
        if short_id(c.get("id", "")) == h:
            return c
    return None


def _run_locked(args):
    r = subprocess.run(["flock", "-w", "60", LOCK] + args, capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def handle(data, from_id, queue_path=None, events_path=None, runner=None):
    """-> (toast, result_line|None, approved_bool). runner(args)->(rc,out) подменяется в тестах."""
    if str(from_id) != OWNER:
        return "Нет доступа", None, False
    pr = parse(data)
    if not pr:
        return "Неверная кнопка", None, False
    act, h = pr
    qp = queue_path or C.QUEUE
    ep = events_path or C.EVENTS
    q = C.load_json(qp, {"candidates": []})
    c = find(q, h)
    if c is None:
        return "Уже обработано или нет в очереди", None, False
    cid = c["id"]
    args = [sys.executable, os.path.join(HERE, "approve.py"), "--queue", qp, "--events", ep]
    args += [cid] if act == "a" else ["--reject", cid]
    rc, out = (runner or _run_locked)(args)
    lines = (out or "").strip().splitlines()
    msg = lines[-1] if lines else f"rc={rc}"
    if rc != 0:
        return f"Не выполнено: {msg}"[:190], f"⚠️ {msg}", False
    if act == "a":
        return "Одобрено", f"✅ {msg}", True
    return "Отклонено", f"❌ {msg}", False


def trigger_news(popen=subprocess.Popen):
    """Фоном: выпуск новостей под flock -w 600; бот не блокируется."""
    log = open(os.path.join(C.ROOT, "agents", "logs", "world-news-trigger.log"), "a")
    return popen(["flock", "-w", "600", LOCK, "bash", os.path.join(HERE, "run-news.sh")],
                 cwd=C.ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                 start_new_session=True)
