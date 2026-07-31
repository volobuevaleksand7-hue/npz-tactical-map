#!/usr/bin/env bash
# Selfcheck for the narrow data/ rollback block in agents/run-agent.sh
# (the "git-sync отказал" branch). No network, no VPS, no real git-sync.sh call.
#
# Extracts the ACTUAL rollback snippet out of the shipped run-agent.sh (sed, by
# the same start/end markers used in the real file) so this test can never drift
# from what actually ships — then exercises it against a throwaway git repo.
#
# Scenario: collector A already wrote its layer (fresh, still uncommitted at the
# moment collector B's run starts). Collector B is the CURRENT run, its own
# git-sync fails (simulated: agents/git-sync.sh does not exist in the throwaway
# repo, so `bash agents/git-sync.sh ...` naturally fails, taking the real "if !"
# branch), and B's output is a brak (literal conflict markers).
#
# Required outcome: A's fresh work survives (tree AND index). B's brak vanishes
# (tree AND index).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_AGENT="$SCRIPT_DIR/run-agent.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init -q
git config user.email test@test.local
git config user.name test

mkdir data
printf '{"v":1}\n' > data/roads.json
printf '{"v":1}\n' > data/wave-state.json
git add data
git commit -qm base

# --- A already ran: fresh, valid, UNCOMMITTED update sitting in the tree ----
printf '{"v":"A-fresh-good"}\n' > data/roads.json

# Snapshot DATA_BEFORE exactly as run-agent.sh does at the start of B's run —
# A's dirty-but-legit change is already on disk, so it lands in this snapshot.
DATA_BEFORE="$(git status --porcelain data/)"

# --- B (this run) writes a brak ----------------------------------------------
printf '<<<<<<< HEAD\nbroken\n=======\n' > data/wave-state.json

# Mirror what the real git-sync.sh does right before it fails: stage data/.
git add data/

# --- extract the ACTUAL rollback block from the shipped script --------------
SNIPPET="$(sed -n '/^if ! bash agents\/git-sync\.sh/,/^fi$/p' "$RUN_AGENT")"
[ -n "$SNIPPET" ] || { echo "FAIL: could not locate rollback block in run-agent.sh"; exit 1; }

# Run it: cwd has no agents/git-sync.sh, so `bash agents/git-sync.sh ...` fails
# on its own (file not found) and the real "if !" branch fires — no stub needed.
export LABEL=wave-state DATA_BEFORE
RC=0
bash -c "$SNIPPET" || RC=$?
[ "$RC" = "1" ] || { echo "FAIL: rollback block exited $RC, expected 1"; exit 1; }

# ---- assertions --------------------------------------------------------------
ok=1
[ "$(cat data/roads.json)" = '{"v":"A-fresh-good"}' ] || { echo "FAIL: A's tree content lost"; ok=0; }
[ "$(git show :data/roads.json)" = '{"v":"A-fresh-good"}' ] || { echo "FAIL: A's index content lost"; ok=0; }
[ "$(cat data/wave-state.json)" = '{"v":1}' ] || { echo "FAIL: B's brak still in tree"; ok=0; }
[ "$(git show :data/wave-state.json)" = '{"v":1}' ] || { echo "FAIL: B's brak still in index"; ok=0; }

if [ "$ok" = 1 ]; then
  echo "PASS: A's work survived (tree+index), B's brak purged (tree+index)"
else
  exit 1
fi
