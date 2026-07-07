# NPZ editorial posting plan

Date: 2026-07-07

## Goal

Make Telegram posting useful for subscribers: one recognizable Russian-language style,
no repeated facts, visible main point, and a fresh visual for each normal post.

## Done means

- `python3 -m unittest hermes.bot.test_editorial_digest -v` passes.
- `NPZ_EDITORIAL=1 python3 hermes/bot/broadcast.py --editorial-dry-run` prints a post preview without Telegram token.
- `hermes/publish-vps.sh` can run the editorial mode explicitly.

## Scope

1. Add an editorial builder that chooses one of two production formats:
   - `event`: one lead event, consequence, current status, map CTA.
   - `monitoring`: routine subscriber-friendly snapshot when there is no strong lead.
2. Add exact-fact dedupe with a small editorial state file.
3. Render a new stat/event card through the existing `render_card.py`.
4. Keep the old diff digest behind the default path until the publish script opts into
   `NPZ_EDITORIAL=1`.

## Non-goals

- No scraping changes in this pass.
- No AI image-generation pipeline in cron yet. For now "new visual" means a freshly
  rendered branded card. AI covers remain for a later controlled step.
