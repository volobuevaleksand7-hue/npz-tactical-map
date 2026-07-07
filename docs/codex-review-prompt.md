# NPZ Tactical Map — Devil's Advocate Review (Codex 5.5)

## Context
You are reviewing the architecture of an automated news aggregation system for a tactical map of Russia's oil refinery status (https://npz-tactical-map.vercel.app). The system uses AI agents to collect OSINT data, update JSON files, and publish to a static website.

## Current Architecture (Hermes Agent)

### Data Flow
```
Hermes Cron (3×/day) → WebSearch + Telegram → Update JSON → Git push → Vercel auto-deploy
```

### Agents (14 total)
1. STRIKES — drone/missile strikes on cities (3×/day)
2. NPZ-STATUS — refinery status (3×/day)
3. FUEL-MARKET — fuel deficit/balance (3×/day)
4. NEWSWATCH — hourly fast-lane strikes (urgent alerts)
5. FUEL-VOICES — people's reports from gas stations (8h)
6. WATCHDOG — health monitoring (hourly)
7. HISTORY-CRIMEA — chronicle + Crimea events (6h) [Phase2]
8. ROADS — roads/fuel logistics (6h) [Phase2]
9. GRID-STATUS — electricity grid (6h) [Phase2]
10. FUEL-AVAILABILITY — gas stations (4h) [Phase2]
11. FORECAST — weekly scenario forecast [Phase3]
12. ECONOMY — economic effect analysis [Phase3]
13. STRIKE-CONFIRM — GDELT+FIRMS verification [Phase3]
14. COVERS — image generation (2×/day) [Phase3]

### Models
- Free tier (mimo-auto:free): Simple tasks
- Fallback:10 free models (OpenRouter)
- Paid (mimo-v2.5-pro): Complex tasks (FORECAST, ECONOMY)
- Codex: Image generation, code review

### Urgent Alert Workflow
```
NEWSWATCH detects strike → Sends alert with buttons to Telegram
→ User clicks "Publish" → Agent creates post → Publishes to Telegram + website
```

### Kanban Dashboard
- Visual Kanban board for tracking agent status
- Shows: Ready, Running, Completed, Blocked
- Auto-refreshes every30 seconds

## Questions for Devil's Advocate Review

### 1. Architecture Risks
- Single point of failure?
- Data consistency issues?
- Race conditions with concurrent agents?

### 2. Data Quality
- How to prevent fake news?
- Confidence levels (confirmed/reported/rumored)?
- Source verification?

### 3. Cost Optimization
- Are we using the right models for each task?
- Can we use cheaper models for more tasks?
- Token usage estimates?

### 4. Scalability
- What happens if news volume increases?
- Can we handle100+ strikes per day?
- Storage/processing limits?

### 5. User Experience
- Is the urgent alert workflow intuitive?
- Button vs text command for actions?
- Notification frequency (too many/too few)?

### 6. Legal/Ethical
- OSINT aggregation risks?
- Attribution requirements?
- Content moderation?

### 7. Technical Debt
- Code maintainability?
- Testing strategy?
- Monitoring/alerting?

## Deliverable
Provide a structured review with:
1. Critical issues (must fix before production)
2. Warnings (should fix soon)
3. Suggestions (nice to have)
4. Questions for clarification

Rate each item: 🔴 Critical / 🟡 Warning / 🟢 Suggestion

## File Location
Save review to: /root/npz-tactical-map/docs/codex-review.md
