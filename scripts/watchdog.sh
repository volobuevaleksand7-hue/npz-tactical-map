#!/usr/bin/env bash
# NPZ Tactical Map Watchdog - encapsulated script for health checking and alerting
set -euo pipefail

REPO_ROOT="/root/npz-tactical-map"
cd "$REPO_ROOT"

# Update repository with stash handling for local changes
if ! git diff-index --quiet HEAD --; then
    echo "Local changes detected, stashing before pull"
    git stash push -m "watchdog stash before pull $(date -u +%Y-%m-%dT%H:%MZ)"
fi
git pull --rebase
# Restore stashed changes if any
if git stash list | grep -q "watchdog stash"; then
    git stash pop
fi

# Run health check and capture output
HEALTH_OUTPUT=$(python3 agents/healthcheck.py 2>&1) || {
    echo "Health check script failed, treating as degraded"
    HEALTH_OUTPUT="health: degraded | stale 0/10 | dead 1 | hb_dead 0"
}
echo "$HEALTH_OUTPUT"

# Parse health.json for overall and dead_count
OVERALL=$(jq -r '.meta.overall // empty' data/health.json)
DEAD_COUNT=$(jq -r '.meta.dead_count // 0' data/health.json)
STALE_COUNT=$(jq -r '.meta.stale_count // 0' data/health.json)

# Get heartbeat_dead_count from health.json
HB_DEAD=$(jq -r '.meta.heartbeat_dead_count // 0' data/health.json)

# Determine if alert needed
ALERT_NEEDED=false
if [[ "$OVERALL" != "healthy" || "$DEAD_COUNT" -gt 0 || "$HB_DEAD" -gt 0 ]]; then
    ALERT_NEEDED=true
fi

# Check cooldown - only alert if last alert was >2 hours ago
COOLDOWN_FILE="/root/.npz-bot/last-watchdog-alert"
if [[ "$ALERT_NEEDED" == true && -f "$COOLDOWN_FILE" ]]; then
    LAST_ALERT=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo "0")
    NOW=$(date +%s)
    ELAPSED=$((NOW - LAST_ALERT))
    if [[ "$ELAPSED" -lt 7200 ]]; then
        echo "Watchdog: cooldown active (${ELAPSED}s since last alert, need 7200s). Skipping alert."
        ALERT_NEEDED=false
    fi
fi

if [[ "$ALERT_NEEDED" == true ]]; then
    # Identify dead agents (status == "dead")
    DEAD_AGENTS=$(jq -c '.meta.files[] | select(.status == "dead")' data/health.json 2>/dev/null || true)
    if [[ -n "$DEAD_AGENTS" && "$DEAD_AGENTS" != "null" ]]; then
        # Build messages for each dead agent
        TEXT=""
        while IFS= read -r agent; do
            # Extract fields
            NAME=$(echo "$agent" | jq -r '.agent // empty')
            GENERATED_AT=$(echo "$agent" | jq -r '.generated_at // empty')
            HEARTBEAT_AT=$(echo "$agent" | jq -r '.heartbeat_at // empty')
            AGE_HOURS=$(echo "$agent" | jq -r '.age_hours // empty')
            HEARTBEAT_AGE_HOURS=$(echo "$agent" | jq -r '.heartbeat_age_hours // empty')
            # Determine last update time and age
            if [[ -n "$GENERATED_AT" && "$GENERATED_AT" != "null" ]]; then
                LAST_UPDATE="$GENERATED_AT"
                AGE="$AGE_HOURS"
            else
                LAST_UPDATE="$HEARTBEAT_AT"
                AGE="$HEARTBEAT_AGE_HOURS"
            fi
            # Extract agent name inside parentheses if format is npz-data (name)
            AGENT_NAME=$(echo "$NAME" | sed -n 's/.*(\(.*\)).*/\1/p')
            if [[ -z "$AGENT_NAME" ]]; then
                AGENT_NAME="$NAME"
            fi
            # Format hours with one decimal
            AGE_DISPLAY=$(printf "%.1f" "$AGE")
            # Compose message for this agent
            MSG="🚨 WATCHDOG ALERT: Агент $AGENT_NAME мёртв!
Последнее обновление: $LAST_UPDATE
Возраст: $AGE_DISPLAY часов
Действие: Проверить логи agents/logs/${AGENT_NAME}.log
"
            TEXT="${TEXT}${MSG}"
        done <<< "$DEAD_AGENTS"
    else
        # No dead agents per status, but alert needed due to overall degraded or hb_dead>0
        if [[ "$HB_DEAD" -gt 0 && "$DEAD_COUNT" -eq 0 && "$OVERALL" == "healthy" ]]; then
            TEXT="🚨 WATCHDOG ALERT: Heartbeat issues detected! $HB_DEAD agents have not sent recent heartbeats despite having fresh data. Check agent logs and healthcheck.py output."
        else
            TEXT="🚨 WATCHDOG ALERT: Overall status degraded or dead_count > 0, but no agents marked dead in health.json.
Check data/health.json for details.
Healthcheck output: $HEALTH_OUTPUT"
        fi
    fi
    # Send via Telegram
    BOT_TOKEN_FILE="/root/.npz-bot/token"
    CHAT_ID_FILE="/root/.npz-bot/chat_id"
    if [[ -f "$BOT_TOKEN_FILE" && -f "$CHAT_ID_FILE" ]]; then
        TOKEN=$(cat "$BOT_TOKEN_FILE")
        CHAT_ID=$(cat "$CHAT_ID_FILE")
        curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
            -d chat_id="${CHAT_ID}" \
            -d text="$TEXT" \
            -d parse_mode="HTML" > /dev/null
        echo "Telegram alert sent"
        # Update cooldown file
        date +%s > "$COOLDOWN_FILE"
    else
        echo "Telegram credentials not found at $BOT_TOKEN_FILE or $CHAT_ID_FILE" >&2
    fi
fi

# Update heartbeat via git-sync
bash agents/git-sync.sh "health: watchdog $(date -u +%Y-%m-%dT%H:%MZ)"
