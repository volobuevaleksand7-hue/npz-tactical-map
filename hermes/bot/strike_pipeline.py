#!/usr/bin/env python3
"""
strike_pipeline.py — Unified pipeline: detect → classify → publish → update map → git push

Usage:
  python3 strike_pipeline.py [--dry-run] [--force-major] [--backfill]

  --backfill — разовый прогон ПЕРЕД включением автопубликации: помечает весь
  текущий беклог как обработанный БЕЗ отправки. Без него первый крон-прогон
  выплюнет в канал молнии задним числом (16.07 состояние стояло с 08.07 —
  накопилось 53 таких удара). Флаг был, но в этой строке не значился.

Workflow:
  1. detect_new_strikes()    Compare strikes.json vs pipeline-state.json, find new entries
  2. classify_and_publish()  For each new strike: classify, publish (tier 1 auto, tier 2 admin)
  3. update_map()            If major: update fuel-state.json (refinery status, balance, events)
  4. git push                Commit and push to trigger Vercel auto-deploy

State tracked in: /root/npz-tactical-map/data/pipeline-state.json
"""

import json
import os
import sys
import subprocess
import hashlib
from datetime import datetime, timezone

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
STRIKES_PATH = os.path.join(DATA_DIR, "strikes.json")
FUEL_STATE_PATH = os.path.join(DATA_DIR, "fuel-state.json")
PIPELINE_STATE_PATH = os.path.join(DATA_DIR, "pipeline-state.json")

# ─── Import radar_publish ────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(BASE_DIR, "hermes", "bot"))
try:
    from radar_publish import classify_news, publish_strike_molniya, publish_strike_tier2
except ImportError:
    print("WARNING: Could not import radar_publish. Classification will be skipped.")
    classify_news = None
    publish_strike_molniya = None
    publish_strike_tier2 = None
try:
    from content_guard import reason_bad
except ImportError:
    reason_bad = None  # без гварда лучше публиковать, чем упасть; санитайзер добьёт на коммите


def jload(path, default=None):
    """Load JSON from file."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def jsave(path, data):
    """Save JSON atomically (tmp + os.replace) so a crash mid-write can't truncate
    the state file into `{}` and mass-rebroadcast every historical strike (audit H9)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _strike_id(strike):
    """Generate a stable ID for a strike from its key fields."""
    parts = [
        str(strike.get("date", "")),
        str(strike.get("time", "")),
        str(strike.get("city", "")),
        str(strike.get("target", ""))[:80],
    ]
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DETECT NEW STRIKES
# ═══════════════════════════════════════════════════════════════════════════════

def load_pipeline_state():
    """Load last processed strike IDs from pipeline state."""
    state = jload(PIPELINE_STATE_PATH, {"last_strike_ids": [], "last_run": None})
    return set(state.get("last_strike_ids", []))


def save_pipeline_state(processed_ids):
    """Save processed strike IDs."""
    state = {
        "last_strike_ids": list(processed_ids),
        "last_run": datetime.now(timezone.utc).isoformat(),
    }
    jsave(PIPELINE_STATE_PATH, state)


def detect_new_strikes():
    """
    Compare latest strikes.json with previous state, find new entries.
    Returns list of new strike dicts.
    """
    strikes_data = jload(STRIKES_PATH, {})
    strikes = strikes_data.get("strikes", [])
    if not strikes:
        print("[detect] No strikes found in strikes.json")
        return []

    processed_ids = load_pipeline_state()
    new_strikes = []

    for strike in strikes:
        sid = _strike_id(strike)
        if sid not in processed_ids:
            strike["_pipeline_id"] = sid
            new_strikes.append(strike)

    print(f"[detect] Total strikes: {len(strikes)}, previously processed: {len(processed_ids)}, new: {len(new_strikes)}")
    return new_strikes


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CLASSIFY AND PUBLISH
# ═══════════════════════════════════════════════════════════════════════════════
# Форматирование текста теперь ЦЕЛИКОМ в hermes/bot/render.py (render_molniya) —
# см. radar_publish.publish_strike_molniya / publish_strike_tier2, единый рендер
# и единый дедуп (day_state.py) для всех уровней (TIER1/TIER2/сводка/сайт).

def classify_and_publish(new_strikes, dry_run=False, force_major=False):
    """
    For each new strike:
      a. Classify using radar_publish.classify_news()
      b. If TIER 1 (major): auto-publish via publish_strike_molniya() (render.py + day_state dedup)
      c. If TIER 2 (regular): send to admin chat via publish_strike_tier2() with inline buttons
    Returns list of (strike, tier, result) tuples.
    """
    if classify_news is None:
        print("[classify] WARNING: radar_publish not available, skipping classification")
        return []

    results = []
    for strike in new_strikes:
        # ГВАРД НЕЙТРАЛЬНОСТИ: не публиковать укр-вербатим/пропаганду/офф-топик в канал
        # и подписчикам (это происходит ДО git-commit, т.е. до санитайзера в pre-commit).
        _bad = reason_bad(strike) if reason_bad else None
        if _bad:
            print(f"  [guard] SKIP публикацию — ненейтральный контент ({_bad}): "
                  f"{strike.get('city', '?')} | {str(strike.get('target', ''))[:50]}")
            results.append({"strike": strike, "tier": "blocked", "info": {"reason": _bad},
                            "publish_result": {"blocked": True}})
            continue
        tier, info = classify_news(strike)

        # Force major if requested
        if force_major:
            tier = "major"
            info["reason"] = "forced (--force-major)"

        print(f"\n[classify] {strike.get('city', '?')}: {strike.get('target', '?')[:50]}")
        print(f"  Tier: {tier.upper()} | Reason: {info.get('reason', '')}")

        result = {"strike": strike, "tier": tier, "info": info, "publish_result": None}

        if tier == "major":
            print(f"  → Publishing as МОЛНИЯ (TIER 1)")
            if publish_strike_molniya:
                pub_result = publish_strike_molniya(strike, reason=info.get("reason", ""), dry_run=dry_run)
                result["publish_result"] = pub_result
                if pub_result.get("skipped_duplicate"):
                    print(f"  → SKIP: уже опубликовано сегодня (dedup key={pub_result.get('key')})")
                else:
                    print(f"  → Result: channel_ok={pub_result.get('channel_ok')}, subs_sent={pub_result.get('subscribers_sent')}")
            else:
                print("  → [SKIP] radar_publish not available")

        elif tier == "regular":
            print(f"  → Sending to admin chat (TIER 2)")
            if publish_strike_tier2:
                pub_result = publish_strike_tier2(strike, reason=info.get("reason", ""), dry_run=dry_run)
                result["publish_result"] = pub_result
                if pub_result.get("skipped_duplicate"):
                    print(f"  → SKIP: уже опубликовано сегодня (dedup key={pub_result.get('key')})")
                else:
                    print(f"  → Result: sent={pub_result.get('sent')}")
            else:
                print("  → [SKIP] radar_publish not available")

        results.append(result)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 3. UPDATE MAP
# ═══════════════════════════════════════════════════════════════════════════════

def _match_refinery_id(strike):
    """
    Try to match a strike to a refinery ID in fuel-state.json.
    Returns (refinery_id, match_type) or (None, None).
    """
    fuel = jload(FUEL_STATE_PATH, {})
    refineries = fuel.get("refineries", [])

    target_lower = str(strike.get("target", "")).lower()
    city_lower = str(strike.get("city", "")).lower()
    title_lower = str(strike.get("title", "")).lower()
    searchable = f"{target_lower} {title_lower} {city_lower}"

    # Keyword mappings for refinery matching
    refinery_keywords = {
        "kinef": ["кире", "кинеф", "кириши"],
        "ryazan": ["рязан"],
        "moscow": ["московск", "капотн"],
        "perm": ["перм"],
        "syzran": ["сызран"],
        "tuapse": ["туапс"],
        "kuibyshev": ["куйбышев"],
        "novokuibyshevsk": ["новокуйбышев"],
        "nnos": ["норси", "кстово", "нижегород"],
        "yanos": ["янос", "ярослав", "славнефть-ян"],
        "volgograd": ["волгоград"],
        "omsk": ["омск"],
        "taneco": ["танеко", "нижнекам"],
        "ufa": ["уф", "башнефть"],
        "achinsk": ["ачинск"],
        "angarsk": ["ангарск"],
        "komsomolsk": ["комсомольск"],
    }

    for ref_id, keywords in refinery_keywords.items():
        for kw in keywords:
            if kw in searchable:
                # Verify this refinery exists in fuel-state.json
                for ref in refineries:
                    if ref.get("id") == ref_id:
                        return ref_id, "keyword_match"
                # Fallback: refinery not in fuel-state.json yet
                return ref_id, "keyword_match"

    return None, None


def _recalculate_national_balance(fuel):
    """
    Recalculate national_balance from refineries[].
    capacity_offline = sum of capacities where status=down
    throughput_shortfall = weighted by est_output_pct
    """
    refineries = fuel.get("refineries", [])
    total_capacity = 0
    offline_capacity = 0
    total_weighted = 0

    for ref in refineries:
        cap = ref.get("capacity_mt_year", 0)
        total_capacity += cap
        status = ref.get("status", "operational")
        output_pct = ref.get("est_output_pct", 100)

        if status == "down":
            offline_capacity += cap
        elif status == "partial":
            offline_capacity += cap * (1 - output_pct / 100.0)

        total_weighted += cap * (1 - output_pct / 100.0)

    if total_capacity > 0:
        offline_pct = int(round(offline_capacity / total_capacity * 100))
        shortfall_pct = int(round(total_weighted / total_capacity * 100))
    else:
        offline_pct = 0
        shortfall_pct = 0

    fuel["national_balance"]["refining_capacity_total_mt_year"] = round(total_capacity, 1)
    fuel["national_balance"]["capacity_offline_mt_year"] = round(offline_capacity, 1)
    fuel["national_balance"]["capacity_offline_pct"] = offline_pct
    fuel["national_balance"]["throughput_shortfall_pct"] = shortfall_pct

    return fuel


def update_map(strike_data, dry_run=False):
    """
    If major strike: update fuel-state.json
      a. Set hit refinery to "down" or "partial"
      b. Recalculate national_balance
      c. Add event to events array
      d. Git commit and push
    """
    ref_id, match_type = _match_refinery_id(strike_data)

    if not ref_id:
        print(f"[update_map] No refinery match for: {strike_data.get('target', '')[:60]}")
        return False

    fuel = jload(FUEL_STATE_PATH)
    if not fuel:
        print(f"[update_map] ERROR: Cannot load {FUEL_STATE_PATH}")
        return False

    refineries = fuel.get("refineries", [])
    target_ref = None
    for ref in refineries:
        if ref.get("id") == ref_id:
            target_ref = ref
            break

    if not target_ref:
        print(f"[update_map] Refinery {ref_id} not found in fuel-state.json")
        return False

    old_status = target_ref.get("status", "unknown")
    city = strike_data.get("city", "")
    title = strike_data.get("title", "")
    detail = strike_data.get("detail", "")

    # Determine new status based on strike info
    strike_text = f"{strike_data.get('target', '')} {title} {detail}".lower()
    if "полностью останов" in strike_text or "полностью выведен" in strike_text:
        new_status = "down"
        new_output = 0
    elif any(kw in strike_text for kw in ["поврежд", "частичн", "снижен", "понижен", "горит", "пожар"]):
        new_status = "partial"
        new_output = max(target_ref.get("est_output_pct", 100) - 30, 15)
    else:
        new_status = "partial"
        new_output = max(target_ref.get("est_output_pct", 100) - 20, 20)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"\n[update_map] Refinery: {target_ref.get('name', ref_id)}")
    print(f"  Old status: {old_status} → New status: {new_status} (output: {new_output}%)")
    print(f"  Damage: {strike_data.get('detail', '')[:80]}...")

    if dry_run:
        print("  [DRY-RUN] Would update fuel-state.json")
        return True

    # a. Update refinery status
    target_ref["status"] = new_status
    target_ref["status_since"] = today
    target_ref["est_output_pct"] = new_output
    target_ref["damage"] = detail[:500] if detail else target_ref.get("damage", "")
    target_ref["source_url"] = strike_data.get("source_url", target_ref.get("source_url", ""))
    target_ref["confidence"] = strike_data.get("confidence", "reported")

    # b. Recalculate national balance
    fuel = _recalculate_national_balance(fuel)

    # c. Add event
    if "events" not in fuel:
        fuel["events"] = []

    event_text = f"Удар по {target_ref.get('name', ref_id)} ({city}): {title or detail[:100]}"
    fuel["events"].insert(0, {
        "date": today,
        "text": event_text,
        "source_url": strike_data.get("source_url", ""),
    })

    # Keep events manageable (last 30)
    fuel["events"] = fuel["events"][:30]

    # d. Save
    fuel["meta"]["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    fuel["meta"]["updated_by"] = "agent:strike-pipeline"
    jsave(FUEL_STATE_PATH, fuel)

    print(f"  ✓ fuel-state.json updated")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GIT COMMIT AND PUSH
# ═══════════════════════════════════════════════════════════════════════════════

def git_commit_push(message, dry_run=False):
    """Git add, commit, and push. Returns True on success."""
    if dry_run:
        print(f"\n[git] [DRY-RUN] Would commit and push: {message}")
        return True

    try:
        # Stage all data changes
        subprocess.run(
            ["git", "add", "data/fuel-state.json", "data/pipeline-state.json", "data/strikes.json"],
            cwd=BASE_DIR, capture_output=True, timeout=30
        )

        # Check if there are changes to commit
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=10
        )
        if not status.stdout.strip():
            print("[git] No changes to commit")
            return True

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=30
        )
        print(f"[git] Commit: {result.stdout.strip()[:200]}")
        if result.returncode != 0:
            print(f"[git] Commit warning: {result.stderr.strip()[:200]}")

        # Push
        result = subprocess.run(
            ["git", "push"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print("[git] Push OK → Vercel auto-deploy triggered")
            return True
        else:
            print(f"[git] Push failed: {result.stderr.strip()[:200]}")
            return False

    except Exception as e:
        print(f"[git] Error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline(dry_run=False, force_major=False):
    """
    Full pipeline: detect → classify → publish → update map → git push
    Returns summary dict.
    """
    print("=" * 60)
    print(f"STRIKE PIPELINE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    if force_major:
        print("⚠️  --force-major: all strikes will be classified as TIER 1")
    print("=" * 60)

    summary = {
        "new_strikes": 0,
        "major_count": 0,
        "regular_count": 0,
        "map_updated": False,
        "git_pushed": False,
    }

    # 1. Detect
    print("\n── STEP 1: Detect new strikes ──")
    new_strikes = detect_new_strikes()
    summary["new_strikes"] = len(new_strikes)

    if not new_strikes:
        print("No new strikes. Pipeline complete.")
        return summary

    # Show new strikes
    for i, strike in enumerate(new_strikes, 1):
        print(f"  [{i}] {strike.get('date', '?')} {strike.get('city', '?')}: {strike.get('target', '?')[:60]}")

    # 2. Classify and publish
    print("\n── STEP 2: Classify & publish ──")
    results = classify_and_publish(new_strikes, dry_run=dry_run, force_major=force_major)

    major_results = [r for r in results if r["tier"] == "major"]
    regular_results = [r for r in results if r["tier"] == "regular"]
    summary["major_count"] = len(major_results)
    summary["regular_count"] = len(regular_results)

    # 3. Update map for major strikes
    print("\n── STEP 3: Update map ──")
    map_updated = False
    if major_results:
        for result in major_results:
            strike = result["strike"]
            ref_id, _ = _match_refinery_id(strike)
            if ref_id:
                updated = update_map(strike, dry_run=dry_run)
                if updated:
                    map_updated = True
            else:
                print(f"  No refinery match for: {strike.get('target', '')[:50]}")
    else:
        print("  No major strikes to update map.")

    summary["map_updated"] = map_updated

    # 4. Git commit and push
    # ВАЖНО: dry_run НИКОГДА не должен персистить pipeline-state.json — иначе
    # повторные --dry-run прогоны молча "съедают" удары из очереди на публикацию
    # (баг, воспроизведён 2026-07-07: dry-run пометил 65 ударов как обработанные,
    # хотя ничего не было реально опубликовано). Только реальный (не dry-run) прогон
    # обновляет state, независимо от map_updated.
    if not dry_run:
        print("\n── STEP 4: Git commit & push ──")
        # Mark all as processed
        all_ids = load_pipeline_state()
        for strike in new_strikes:
            all_ids.add(_strike_id(strike))
        save_pipeline_state(all_ids)

        commit_msg = f"strike-pipeline: {len(new_strikes)} strikes ({summary['major_count']} major, {summary['regular_count']} regular) — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        pushed = git_commit_push(commit_msg, dry_run=dry_run)
        summary["git_pushed"] = pushed
    else:
        print("\n── STEP 4: Skipped (dry-run — не персистим state, не коммитим) ──")

    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"  New strikes:    {summary['new_strikes']}")
    print(f"  Major (TIER 1): {summary['major_count']}")
    print(f"  Regular (TIER 2): {summary['regular_count']}")
    print(f"  Map updated:    {summary['map_updated']}")
    print(f"  Git pushed:     {summary['git_pushed']}")
    print("=" * 60)

    return summary


def backfill_baseline():
    """Одноразовая операция при включении молнии в прод (2026-07-07): пайплайн
    раньше гонялся ТОЛЬКО с --dry-run, поэтому в strikes.json накопился долг
    необработанных событий (на момент миграции — 65, из них ~27 TIER1) начиная
    с мая. Живой запуск без бэкафилла разослал бы десятки МОЛНИЙ по историческим
    ударам разом. backfill помечает весь текущий беклог как processed БЕЗ
    классификации/публикации/git push — чтобы молния начала стрелять только по
    ударам, добавленным ПОСЛЕ этого момента."""
    new_strikes = detect_new_strikes()
    if not new_strikes:
        print("[backfill] Нечего помечать — беклога нет.")
        return
    print(f"[backfill] Помечаю {len(new_strikes)} исторических ударов как обработанные "
          f"(БЕЗ публикации) — устанавливаю чистую точку отсчёта для молнии.")
    all_ids = load_pipeline_state()
    for strike in new_strikes:
        all_ids.add(_strike_id(strike))
    save_pipeline_state(all_ids)
    print(f"[backfill] Готово. pipeline-state.json теперь содержит {len(all_ids)} обработанных ID.")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force_major = "--force-major" in args

    if "--help" in args or "-h" in args:
        print("""
strike_pipeline.py — Unified strike detection → classify → publish → map update pipeline

Usage:
  python3 strike_pipeline.py [OPTIONS]

Options:
  --dry-run       Show what would happen without publishing or pushing (state NOT persisted)
  --force-major   Classify all strikes as TIER 1 (major)
  --backfill      One-time: mark current backlog as processed WITHOUT publishing
                  (use once when flipping molniya live, to avoid a spam burst
                  of historical events — see docs/agents/audit-2026-07-07.md)
  --help, -h      Show this help

Files:
  Input:  /root/npz-tactical-map/data/strikes.json
  State:  /root/npz-tactical-map/data/pipeline-state.json
  Output: /root/npz-tactical-map/data/fuel-state.json (if major strikes)
""")
        sys.exit(0)

    if "--backfill" in args:
        backfill_baseline()
        sys.exit(0)

    summary = run_pipeline(dry_run=dry_run, force_major=force_major)
    sys.exit(0 if summary["new_strikes"] == 0 or summary["git_pushed"] or dry_run else 1)
