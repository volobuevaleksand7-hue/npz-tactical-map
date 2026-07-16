#!/usr/bin/env bash
# NPZ TACTICAL MAP — safe data sync/commit/push for ALL routines (local + cloud).
#
# WHY THIS EXISTS
# ---------------
# data/last-sync.txt repeatedly appeared on origin/main containing raw git
# stash/merge conflict markers:
#     <<<<<<< Updated upstream
#     2026-06-22T04:27Z
#     =======
#     2026-06-22T04:32Z
#     >>>>>>> Stashed changes
# Root cause: routines ran `git pull --rebase --autostash` while last-sync.txt
# (and heartbeats.json) were dirty. Several routines run concurrently and every
# one of them touches those two files, so the autostash `git stash pop` collided
# on the same line and git wrote conflict markers INTO the tracked file. The
# routine then blindly `git add data/ && git commit && git push`, publishing the
# corrupted file to origin.
#
# THIS SCRIPT REMOVES BOTH FAILURE MODES
#   1. Never pull with a dirty tree and NEVER use --autostash. We commit locally
#      first (clean tree), then `git pull --rebase`, so a stash-pop can never run.
#   2. A hard guard refuses to commit/push if any conflict marker is present in
#      data/. The same guard is also installed as a git pre-commit hook so even a
#      hand-typed `git commit` is protected.
#   3. last-sync.txt is written ATOMICALLY (temp file + mv) as a single fresh UTC
#      timestamp line — it is never left half-merged.
#
# USAGE:  bash agents/git-sync.sh "<commit message>"
# Run it from the repo root, AFTER all data/*.json edits + heartbeat are done.
set -uo pipefail

MSG="${1:?commit message required}"
HB_KEYS="${2:-}"                          # optional space-separated heartbeat keys to stamp
MARKER_RE='^(<<<<<<<|=======|>>>>>>>)'   # git conflict / stash markers
EPHEMERAL=(data/last-sync.txt data/heartbeats.json)  # regenerated every run; safe to auto-resolve

# ---- 0. must be at repo root with a data/ dir -------------------------------
[ -d data ] || { echo "git-sync: run from repo root (no data/ dir here)" >&2; exit 2; }
[ -d .git ] || { echo "git-sync: not a git work tree" >&2; exit 2; }

# ---- 1. install the pre-commit guard hook (idempotent) ----------------------
# core.hooksPath -> .githooks means even a manual `git commit` is guarded.
if [ "$(git config core.hooksPath 2>/dev/null)" != ".githooks" ] && [ -f .githooks/pre-commit ]; then
  git config core.hooksPath .githooks
fi

# ---- 2. atomic last-sync.txt stamp ------------------------------------------
stamp_last_sync() {
  local ts tmp
  ts="$(date -u +%Y-%m-%dT%H:%MZ)"
  tmp="$(mktemp "data/.last-sync.XXXXXX")"
  printf '%s\n' "$ts" > "$tmp"
  mv -f "$tmp" data/last-sync.txt        # atomic replace: full overwrite, one fresh line
}

# Stamp liveness for the given heartbeat keys, so "data committed but heartbeat
# forgotten" is structurally impossible — the heartbeat rides this same commit.
# A routine that ran (even with no news) always reaches here, so heartbeat == "alive".
#
# HB_KEYS is expected to be a space-separated list of AGENT LABELS (e.g. "strikes"
# or "strikes roads"), never a free-text sentence. If a caller passes a whole
# summary string (a cloud/Remote-trigger bug seen in the past), naive .split()
# pollutes data/heartbeats.json with junk tokens like "agent:", "update",
# "(July", "6)". To make that structurally impossible we validate every token
# against the same agent whitelist used by agents/healthcheck.py and silently
# drop anything that isn't a known agent name.
stamp_heartbeats() {
  [ -z "$HB_KEYS" ] && return 0
  python3 - "$HB_KEYS" <<'PY'
import json, os, subprocess, sys, datetime

VALID_AGENTS = {
    "npz-status", "fuel-market", "history-crimea", "strikes", "roads",
    "forecast", "economy", "fuel-availability", "fuel-voices",
    "grid-status", "newswatch", "radar-state",
}

keys = [k for k in sys.argv[1].split() if k in VALID_AGENTS]
skipped = [k for k in sys.argv[1].split() if k not in VALID_AGENTS]
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
p = "data/heartbeats.json"


def _load_heartbeats():
    """Последнее хорошее состояние. Пустой словарь — только если файла нет вовсе.

    16.07: битый/полузаписанный файл ронял json.load, `except: {}` и агент стирал
    чужие 11 ключей своим одним — watchdog объявил живых агентов мёртвыми. Читаем
    fallback из git HEAD: потерять чужой heartbeat хуже, чем не обновить свой.
    """
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            return d
    except FileNotFoundError:
        return {}
    except Exception:
        pass
    try:
        out = subprocess.run(["git", "show", "HEAD:data/heartbeats.json"],
                             capture_output=True, text=True, timeout=10)
        d = json.loads(out.stdout)
        if isinstance(d, dict):
            print("git-sync: heartbeats.json битый — подняли версию из HEAD (%d ключей)" % len(d))
            return d
    except Exception:
        pass
    print("git-sync: heartbeats.json битый и HEAD не помог — стартуем с пустого")
    return {}


hb = _load_heartbeats()
for k in keys:
    hb[k] = now
# Атомарно: сосед-читатель никогда не увидит полуфайл (radar-cron вне flock).
tmp = p + ".tmp.%d" % os.getpid()
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(hb, f, ensure_ascii=False, indent=1)
os.replace(tmp, p)
if keys:
    print("git-sync: heartbeat", ", ".join(keys), "->", now)
if skipped:
    print("git-sync: ignored non-agent heartbeat token(s):", ", ".join(skipped))
PY
}

# ---- 3. the guard: abort if ANY conflict marker is anywhere in data/ --------
guard_no_markers() {
  if grep -rnE "$MARKER_RE" data/ ; then
    echo "git-sync: ABORT — conflict markers present in data/ (see lines above)" >&2
    return 1
  fi
  return 0
}

stamp_last_sync
stamp_heartbeats

if ! guard_no_markers; then
  # last-sync.txt was just rewritten cleanly above, so any remaining marker is in
  # a REAL data file. Refuse to touch it — never commit a corrupted JSON.
  echo "git-sync: refusing to commit; fix the file(s) above by hand." >&2
  exit 3
fi

# Nothing staged-worthy? still commit (heartbeat + stamp change every run).
git add data/

# Defense in depth: inspect what is actually STAGED for added marker lines.
if git diff --cached -U0 -- data/ | grep -qE '^\+(<<<<<<<|=======|>>>>>>>)'; then
  echo "git-sync: ABORT — staged diff introduces conflict markers" >&2
  exit 3
fi

# Distinguish "nothing to commit" from a real failure (the pre-commit hook also
# exits 1 — we must NOT treat a hook rejection as a clean no-op and push anyway).
if git diff --cached --quiet; then
  echo "git-sync: nothing staged to commit; skipping commit"
else
  if ! git commit -m "$MSG" --quiet; then
    echo "git-sync: ABORT — commit failed (pre-commit hook rejected or git error)" >&2
    exit 3
  fi
fi

# ---- 4. push with a clean-tree rebase retry (NO autostash) ------------------
push_with_retry() {
  local tries=0 max=4
  while [ "$tries" -lt "$max" ]; do
    if git push --quiet 2>/dev/null; then
      echo "git-sync: pushed -> live via GitHub raw"
      return 0
    fi
    tries=$((tries+1))
    echo "git-sync: push rejected (attempt $tries/$max) — rebasing onto origin"
    # Tree is clean here (everything is committed), so plain --rebase never
    # invokes a stash; --autostash is intentionally NOT used.
    if ! git pull --rebase --quiet; then
      # A rebase conflict. Auto-resolve ONLY the ephemeral, regenerated files;
      # bail on anything else rather than risk corrupting real data.
      local unresolved=0 f
      while IFS= read -r f; do
        [ -z "$f" ] && continue
        case " ${EPHEMERAL[*]} " in
          *" $f "*) git checkout --theirs -- "$f" 2>/dev/null; git add "$f" ;;
          *) echo "git-sync: unresolved conflict in $f" >&2; unresolved=1 ;;
        esac
      done < <(git diff --name-only --diff-filter=U)
      if [ "$unresolved" = "1" ]; then
        git rebase --abort 2>/dev/null || true
        echo "git-sync: ABORT — real conflict left local commit unpushed (next run will sync)" >&2
        return 4
      fi
      stamp_last_sync                       # re-stamp after taking theirs
      stamp_heartbeats                      # re-apply our liveness onto upstream heartbeats
      git add "${EPHEMERAL[@]}" 2>/dev/null || true
      guard_no_markers || { git rebase --abort 2>/dev/null || true; return 4; }
      git rebase --continue --quiet 2>/dev/null || GIT_EDITOR=true git rebase --continue 2>/dev/null || true
    fi
  done
  echo "git-sync: push still failing after $max attempts" >&2
  return 5
}

push_with_retry
