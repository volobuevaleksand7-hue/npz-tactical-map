# System Audit — npz-tactical-map — 2026-06-21

Multi-agent audit (4 dimensions + 4 refinery-verification agents). External cross-check: Gemini ✅; DeepSeek ❌ (API key expired, 401); MiMo ⚠ (declined to route, answered as Opus).

## 0. Refinery status verification (the data-integrity flag from the balance recalc)

| Refinery | Was | Verified | Action |
|---|---|---|---|
| ТАНЕКО (17.0) | down/0% reported | **down/0% confirmed** (both CDUs hit 12.06, no restart) | confidence→confirmed |
| Туапсе (12.0) | down/0% since 05-01 | **down/0% confirmed** (restart ~ноябрь) | status_since→2026-04-16, conf→confirmed |
| Пермь (13.1) | down/0% | **down/0%** (aggressive but no restart reported) | keep |
| Кинеф (20.1) | down/0% | **partial/~30%** — 3 of 4 CDUs hit, one intact, ~1-мес ремонт истёк | **status→partial, est_output→30** |

**Net effect on headline:** capacity_offline 32% → **26%** (7 plants down, 87/336 Mt). The interim 32% over-corrected by trusting Кинеф's overstated `down/0%`. throughput_shortfall (incl. partials) = 42%.

## 1. FIXED in this pass

**Data**
- national_balance recomputed from refineries[]: **26% / 87 Mt / 336 total / 42% shortfall** (was stale 25%/83/330).
- Кинеф → partial 30%; ТАНЕКО/Туапсе confidence + dates corrected.
- strikes.json: backfilled missing `confidence` on **105/110** records (default `reported`); deduped the double-counted 2026-06-21 Чушка strike (110→109).
- history-crimea.json: marked 2 stale `repaired[]` entries (kinef, tuapse) as `superseded` (contradicted current down/partial status).
- capacity-timeline 2026-06-21 snapshot synced to 26%/87.

**Code**
- `healthcheck.py`: fixed heartbeat-key bug — `fuel-availability.json` was keyed to `"fuel-market"` (a different agent); now `"fuel-availability"`. A dead availability agent was being masked by the market agent's heartbeat.
- `healthcheck.py`: added `heartbeat_stale` per file + `heartbeat_dead_count` in meta — surfaces a dead producer agent even when a bulk commit keeps its data `generated_at` fresh (the forecast/economy blind spot). Informational; does **not** gate `overall` yet (avoids false alerts until all cloud routines write heartbeats).
- `healthcheck.py`: threshold tweaks per heartbeat-plan.md — roads 48→36h, availability 12→18h.
- `run-agent.sh`: moved JSON validation **before** the heartbeat write, so a corrupt run's `git checkout -- data/` no longer reverts the heartbeat meant to prove liveness. Also made the validation loop pass the path via argv (quote-safe).
- `app.js`: balance-panel monitoring banner now shows `dead_count` (not `stale_count`) — per heartbeat-plan.md, alerts key on dead, not on `stale_alive` (working agents with no news).

**SEO / security**
- Fixed `Кирishi` → `Кириши` mojibake in JSON-LD (seo/meta-tags.html, seo-research.md).
- Redacted user's Gmail from docs/data-audit-2026-06-20.md (public repo).
- Refreshed sitemap.xml `lastmod` → 2026-06-21.

## 2. RECOMMENDED — needs UI action or a decision (not done here)

- **[CRITICAL] SPOF: split `cloud-npz-data-sync`.** One cloud routine owns 5 datasets + their heartbeats; it died 2026-06-19 and froze all five. The working pattern is 1-routine-1-dataset (availability/voices/grid survived). Split into `cloud-strikes / -npz-status / -roads / -history / -market`, staggered crons. Requires creating routines in the Claude UI.
- **[HIGH] No live forecast/economy agent** (heartbeat 276h dead; data only looks fresh because bulk commits bump `generated_at`). Create a cloud forecast routine (~2×/week, Opus). Now visible via `heartbeat_dead_count`.
- **[HIGH] Complete the heartbeat rollout:** the availability/voices/grid **cloud** prompts don't write heartbeats. Add the §1 step-6b snippet to each so `heartbeat_dead_count` becomes reliable, then wire `overall`/Telegram to it.
- **[HIGH] Agent-count claim inconsistent:** index.html says "9 ИИ-агентов", sources.html says "6", reality ≈ 4–6 routines. Pick the true number and use it everywhere (branding decision).
- **[MED] `og-image.png` missing** — referenced in index.html/seo but absent → broken social cards. Needs a 1200×630 asset.
- **[MED] Run healthcheck on a schedule** — it's referenced by the frontend but not invoked by any cron; `health.json` is effectively hand-updated. Append it to each routine or a watchdog cron.
- **[LOW] Concurrent-push race:** run-agent.sh (VPS) + cloud SKILL push to the same branch with no lock → `!! push failed` silently drops a cycle. Add `flock`/retry. (Moot once VPS is fully retired.)
- **[LOW] Security hardening:** add CSP/HSTS/Referrer-Policy to vercel.json; move VPS IP/root-ssh notes out of the public repo.
- **[LOW] Schema hygiene:** standardize `generated_at` location (`meta.generated_at`) + format across all producers; align `data_mode` enum.

## Method note
`national_balance.capacity_offline_pct` = Σ(capacity of `status=down`) / Σcapacity. `throughput_shortfall_pct` = Σ cap·(1−est_output/100) / Σcapacity. Recomputed from refineries[] by the market agent (prompt updated) — do not maintain by hand.
