#!/usr/bin/env bash
# Update Kanban status after agent run
# Usage: ./update-kanban.sh <task_id> <status> [comment]

TASK_ID="${1:?task_id required}"
STATUS="${2:?status required (complete|block)}"
COMMENT="${3:-}"

case "$STATUS" in
  complete)
    hermes kanban complete "$TASK_ID" 2>/dev/null
    echo "✅ Task $TASK_ID marked as completed"
    ;;
  block)
    hermes kanban block "$TASK_ID" 2>/dev/null
    echo "⚠️ Task $TASK_ID blocked"
    ;;
  comment)
    hermes kanban comment "$TASK_ID" "$COMMENT" 2>/dev/null
    echo "💬 Comment added to $TASK_ID"
    ;;
  *)
    echo "Usage: $0 <task_id> <complete|block|comment> [message]"
    exit 1
    ;;
esac
