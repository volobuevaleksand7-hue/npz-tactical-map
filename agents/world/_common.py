"""Общие функции конвейера событий /lab/world (stdlib). Не запускается сам."""
import datetime as dt
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
D = os.path.join(ROOT, "data", "world")
EVENTS = os.path.join(D, "events.json")
QUEUE = os.path.join(D, "events-queue.json")
sys.path.insert(0, os.path.dirname(HERE))  # agents/ -> neutrality.py

TYPES = {"strike", "attack_shipping", "seizure", "outage", "stocks_release", "opec",
         "sanctions", "shortage", "naval", "other"}
REGIONS = {"europe", "russia_cis", "middle_east", "east_asia", "south_asia",
           "north_america", "latin_america", "africa"}
STATUSES = {"confirmed", "reported"}
NEED_TWO = {"strike", "seizure", "attack_shipping"}
MAX_AGE_DAYS = 14


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return dt.datetime.now(dt.timezone.utc).date()


def parse_ts(s):
    """ISO-дата или дата-время (UTC) -> aware datetime; None при ошибке."""
    try:
        s = str(s).replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json_atomic(path, obj):
    """tmp в том же каталоге + os.replace; сначала сериализуем и проверяем."""
    text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    json.loads(text)
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def publisher_origin(src):
    """Нормализованный издатель: «Reuters (через Al-Monitor)» -> «reuters»."""
    p = str(src.get("publisher", "")).lower()
    p = re.sub(r"\(.*?\)", " ", p)
    p = re.sub(r"\b(через|via)\b.*$", " ", p)
    return re.sub(r"[^a-zа-яё0-9]+", "", p)


def domain(url):
    h = (urlparse(str(url)).hostname or "").lower()
    parts = h.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else h


def independent_count(sources):
    """Число независимых издателей: разные origin И разные домены."""
    seen_o, seen_d = set(), set()
    n = 0
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        o, d = publisher_origin(s), domain(s.get("url"))
        if not o or o in seen_o or d in seen_d:
            continue
        seen_o.add(o)
        seen_d.add(d)
        n += 1
    return n
