#!/usr/bin/env python3
# day_state.py — единое состояние публикации дня + единый дедуп для ВСЕХ форматов
# (сводка/молния/апдейт/страница сайта). Заменяет три разрозненных хранилища:
#   data/pipeline-state.json      (strike-id хэши, strike_pipeline.py)
#   ~/.npz-bot/state.json         (diff-снапшот, broadcast.py compute_digest)
#   ~/.npz-bot/editorial-state.json (dedupe_key + timestamp, editorial_digest.py)
#
# Хранится ВНЕ репозитория (секретов нет, но это оперативное состояние бота,
# как остальные файлы ~/.npz-bot/) — по образцу существующих state-файлов.
#
# Единый ключ дедупа (redpolitika v2, §7):
#   "{date}:{тип}:{город}:{объект}"
# где тип ∈ {strike, voice, molniya, azs, update}.
#
# Публичный API:
#   load_state() -> dict
#   save_state(state)
#   new_day_state(date_iso) -> dict
#   ensure_today(state=None, date_iso=None) -> dict   (сбрасывает day-часть, если день сменился)
#   is_published(state, key) -> bool
#   mark_published(state, key)
#   add_update_line(state, line_html, max_lines=3) -> state
#   migrate_legacy(state) -> state  (одноразовая миграция старых стейтов, идемпотентна)
import datetime
import fcntl
import json
import os

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
DATA_DIR = os.path.join(REPO, "data")

DAY_STATE_PATH = os.path.join(BOT_DIR, "day-state.json")
LOCK_PATH = os.path.join(BOT_DIR, "day-state.lock")

# Легаси-пути для одноразовой миграции.
LEGACY_PIPELINE_STATE = os.path.join(DATA_DIR, "pipeline-state.json")
LEGACY_BROADCAST_STATE = os.path.join(BOT_DIR, "state.json")
LEGACY_EDITORIAL_STATE = os.path.join(BOT_DIR, "editorial-state.json")

MAX_UPDATE_LINES = 3
MAX_PUBLISHED_KEYS = 500  # keep the tail manageable


def _jload(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _jsave(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


_lock_fh = None  # process-lifetime handle: held from load_state() to save_state()


def _acquire_lock():
    """audit H8: day-state.json has no file lock, so independent one-shot processes
    (broadcast.py, radar_publish.py, strike_pipeline.py) can race a load->mutate->save
    and lose each other's writes (the tmp+rename in _jsave — H9, already fixed — only
    makes each individual write atomic, it doesn't serialize the read-modify-write
    cycle across processes). Exclusive flock held from load_state() until the matching
    save_state(); re-acquiring in the same process is a harmless no-op. If a caller
    never calls save_state(), the lock is released when the process exits — fine for
    these one-shot cron scripts, would need a context manager for a long-lived daemon."""
    global _lock_fh
    os.makedirs(BOT_DIR, exist_ok=True)
    if _lock_fh is None:
        _lock_fh = open(LOCK_PATH, "w")
    fcntl.flock(_lock_fh, fcntl.LOCK_EX)


def _release_lock():
    global _lock_fh
    if _lock_fh is not None:
        fcntl.flock(_lock_fh, fcntl.LOCK_UN)


def _msk_now():
    """МСК = UTC+3 круглый год (без DST) — тот же приём, что уже в _now_msk_str()
    ниже и в agents/strike-candidates.py. Без zoneinfo/pytz, т.к. смещение фиксировано."""
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)


def today_iso():
    """Дата дня по МСК (audit H7): продукт МСК-native (редполитика v2, §7), день
    рвётся в 00:00 МСК. Раньше считали по UTC — событие 00:30-02:59 МСК попадало
    под вчерашний дедуп-ключ. Дедуп/ensure_today/day-rollover — всё через эту дату."""
    return _msk_now().strftime("%Y-%m-%d")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def new_day_state(date_iso=None):
    return {
        "date": date_iso or today_iso(),
        "media_message_id": None,
        "text_message_id": None,
        "mode": None,          # "caption" | "split"
        "last_update_msk": None,
        "version": 0,
        "site_page": None,
        "update_lines": [],    # list[str] (rendered 🔄 HTML lines), newest first, max 3
        "molniya_refs": [],    # list[{"headline","url","key"}] published today
        "published_keys": [],  # list[str] — ЕДИНЫЙ дедуп на все форматы (across days, capped)
        "migrated_legacy": False,
    }


def load_state():
    _acquire_lock()
    state = _jload(DAY_STATE_PATH, None)
    if state is None:
        state = new_day_state()
        state = migrate_legacy(state)
        _jsave(DAY_STATE_PATH, state)
    return state


def save_state(state):
    _jsave(DAY_STATE_PATH, state)
    _release_lock()


def ensure_today(state=None, date_iso=None):
    """Если день сменился — сбросить day-часть (message ids, mode, update_lines),
    но published_keys (общий дедуп-журнал) сохраняются между днями."""
    state = state or load_state()
    target_date = date_iso or today_iso()
    if state.get("date") != target_date:
        published_keys = state.get("published_keys", [])
        molniya_refs_prev = state.get("molniya_refs", [])
        fresh = new_day_state(target_date)
        fresh["published_keys"] = published_keys
        fresh["migrated_legacy"] = state.get("migrated_legacy", False)
        state = fresh
        save_state(state)
    return state


def make_key(date_iso, kind, city, target):
    """Единый ключ дедупа: {date}:{тип}:{город}:{объект}."""
    def norm(s):
        return "".join(ch for ch in str(s or "").strip().lower() if ch.isalnum())
    return "%s:%s:%s:%s" % (date_iso, kind, norm(city), norm(target))


def is_published(state, key):
    return key in set(state.get("published_keys", []))


def mark_published(state, key):
    keys = state.setdefault("published_keys", [])
    if key not in keys:
        keys.insert(0, key)
    state["published_keys"] = keys[:MAX_PUBLISHED_KEYS]
    return state


def add_update_line(state, line_html, max_lines=MAX_UPDATE_LINES):
    lines = state.setdefault("update_lines", [])
    lines.insert(0, line_html)
    state["update_lines"] = lines[:max_lines]
    state["version"] = int(state.get("version", 0)) + 1
    state["last_update_msk"] = _now_msk_str()
    return state


def _now_msk_str():
    return _msk_now().strftime("%H:%M")


def add_molniya_ref(state, headline, url, key):
    refs = state.setdefault("molniya_refs", [])
    refs.insert(0, {"headline": headline, "url": url, "key": key})
    state["molniya_refs"] = refs[:10]
    return state


def set_publish_result(state, mode, media_message_id=None, text_message_id=None, site_page=None):
    state["mode"] = mode
    if media_message_id is not None:
        state["media_message_id"] = media_message_id
    if text_message_id is not None:
        state["text_message_id"] = text_message_id
    if site_page is not None:
        state["site_page"] = site_page
    state["version"] = int(state.get("version", 0)) + 1
    state["last_update_msk"] = _now_msk_str()
    return state


# ──────────────────────────────────────────────────────────────
# МИГРАЦИЯ СТАРЫХ СТЕЙТОВ (одноразовая, идемпотентная)
# ──────────────────────────────────────────────────────────────

def _skey(x):
    return "|".join([str(x.get(k, "")) for k in ("date", "time", "city", "target")])


def migrate_legacy(state):
    """Переносит существующие ключи из трёх легаси-хранилищ в published_keys,
    чтобы в день переключения ничего не задвоилось. Идемпотентно: если
    migrated_legacy уже True — не трогает состояние повторно."""
    if state.get("migrated_legacy"):
        return state

    keys = set(state.get("published_keys", []))
    today = today_iso()

    # 1) editorial-state.json: {"published": [{"key": "...", "published_at": ...}]}
    editorial = _jload(LEGACY_EDITORIAL_STATE, {})
    for item in (editorial.get("published") or []):
        k = item.get("key")
        if k:
            keys.add("legacy-editorial:%s" % k)

    # 2) pipeline-state.json: {"last_strike_ids": [hash, ...]}
    pipeline = _jload(LEGACY_PIPELINE_STATE, {})
    for sid in (pipeline.get("last_strike_ids") or []):
        keys.add("legacy-pipeline:%s" % sid)

    # 3) ~/.npz-bot/state.json: {"strike_keys": [...], "voice_keys": [...]}
    broadcast = _jload(LEGACY_BROADCAST_STATE, {})
    for sk in (broadcast.get("strike_keys") or []):
        keys.add("legacy-broadcast-strike:%s" % sk)
    for vk in (broadcast.get("voice_keys") or []):
        keys.add("legacy-broadcast-voice:%s" % vk)

    state["published_keys"] = list(keys)[:MAX_PUBLISHED_KEYS]
    state["migrated_legacy"] = True
    return state


def strike_key(strike, date_iso=None):
    return make_key(date_iso or str(strike.get("date", ""))[:10] or today_iso(),
                     "strike", strike.get("city", ""), strike.get("target") or strike.get("title", ""))


def is_strike_published(state, strike):
    """Проверяет и текущий ключ, и легаси-хэш (pipeline_id), чтобы не задвоить
    удар, который уже был опубликован старым пайплайном до миграции."""
    key = strike_key(strike)
    if is_published(state, key):
        return True
    # legacy pipeline hash fallback
    import hashlib
    parts = [str(strike.get("date", "")), str(strike.get("time", "")),
              str(strike.get("city", "")), str(strike.get("target", ""))[:80]]
    legacy_hash = "legacy-pipeline:%s" % hashlib.md5("|".join(parts).encode()).hexdigest()[:12]
    if is_published(state, legacy_hash):
        return True
    legacy_bkey = "legacy-broadcast-strike:%s" % _skey(strike)
    return is_published(state, legacy_bkey)


def _selftest_msk():
    """ponytail: assert-based smoke test (no pytest suite for hermes/bot/*.py) — proves
    today_iso()/_now_msk_str() are computed from MSK (UTC+3), not raw UTC (audit H7)."""
    utc = datetime.datetime.now(datetime.timezone.utc)
    expected_date = (utc + datetime.timedelta(hours=3)).strftime("%Y-%m-%d")
    expected_hm = (utc + datetime.timedelta(hours=3)).strftime("%H:%M")
    assert today_iso() == expected_date, (today_iso(), expected_date)
    assert _now_msk_str() == expected_hm, (_now_msk_str(), expected_hm)
    print("OK: today_iso()/_now_msk_str() selftest passed (MSK = UTC+3, not raw UTC)")


def _selftest_lock():
    """ponytail: assert-based smoke test (no pytest suite for hermes/bot/*.py) — proves
    the flock actually serializes concurrent load->mutate->save cycles instead of
    letting independent processes race and lose each other's writes (audit H8). Uses
    os.fork() (POSIX only, same as this whole codebase) so the children inherit the
    monkeypatched paths below via copy-on-write, no pickling/spawn complications."""
    global BOT_DIR, DAY_STATE_PATH, LOCK_PATH
    global LEGACY_PIPELINE_STATE, LEGACY_BROADCAST_STATE, LEGACY_EDITORIAL_STATE
    import tempfile
    import time

    BOT_DIR = tempfile.mkdtemp(prefix="day_state_selftest_")
    DAY_STATE_PATH = os.path.join(BOT_DIR, "day-state.json")
    LOCK_PATH = os.path.join(BOT_DIR, "day-state.lock")
    # migrate_legacy() reads these on first load_state() — point them at nonexistent
    # files in the temp dir so this test doesn't pick up real ~/.npz-bot/ state.
    LEGACY_PIPELINE_STATE = os.path.join(BOT_DIR, "no-such-pipeline-state.json")
    LEGACY_BROADCAST_STATE = os.path.join(BOT_DIR, "no-such-broadcast-state.json")
    LEGACY_EDITORIAL_STATE = os.path.join(BOT_DIR, "no-such-editorial-state.json")

    n = 5
    pids = []
    for i in range(n):
        pid = os.fork()
        if pid == 0:  # child
            state = load_state()
            state.setdefault("published_keys", [])
            time.sleep(0.05)  # widen the race window a lock would need to close
            state["published_keys"].append("k%d" % i)
            save_state(state)
            os._exit(0)
        pids.append(pid)
    for pid in pids:
        os.waitpid(pid, 0)

    final = _jload(DAY_STATE_PATH, {})
    keys = final.get("published_keys", [])
    assert len(keys) == n, "lost update: expected %d keys, got %r" % (n, keys)
    print("OK: flock serialized %d concurrent load->mutate->save cycles, no lost update" % n)


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest_msk()
        raise SystemExit(0)
    if "--selftest-lock" in sys.argv:
        _selftest_lock()
        raise SystemExit(0)
    st = load_state()
    st = ensure_today(st)
    print(json.dumps(st, ensure_ascii=False, indent=2))
