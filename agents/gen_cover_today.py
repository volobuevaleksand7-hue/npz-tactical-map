#!/usr/bin/env python3
"""Generate today's cover using smart city selection from strikes.json.
Uses PIL fallback when image_gen (Codex) is unavailable (429)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from caption_cover import pick_top_strike, caption_cover
from PIL import Image, ImageDraw, ImageFont
import platform as _plat

W, H = 1200, 630
BG = (15, 20, 35)
AMBER = (255, 206, 107)

if _plat.system() == "Darwin":
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
else:
    FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def _make_dark_bg():
    """Create a dark background with industrial glow effects."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Industrial glow — upper right (fire)
    for r in range(300, 0, -3):
        intensity = (300 - r) / 300.0
        color = (
            min(255, int(15 + 90 * intensity)),
            min(255, int(20 + 35 * intensity)),
            min(255, int(35 + 15 * intensity)),
        )
        d.ellipse([900 - r, 150 - r, 900 + r, 150 + r], fill=color)

    # Industrial glow — lower left (dimmer)
    for r in range(200, 0, -3):
        intensity = (200 - r) / 200.0 * 0.4
        color = (
            min(255, int(15 + 50 * intensity)),
            min(255, int(20 + 20 * intensity)),
            min(255, int(35 + 25 * intensity)),
        )
        d.ellipse([300 - r, 400 - r, 300 + r, 400 + r], fill=color)

    # Industrial towers
    towers = [
        (850, 100, 18, 200), (890, 120, 14, 180), (930, 80, 20, 220),
        (780, 140, 12, 160), (960, 110, 16, 190),
        (1020, 150, 10, 140), (810, 130, 14, 170),
    ]
    for bx, by, bw, bh in towers:
        d.rectangle([bx, by, bx + bw, by + bh], fill=(25, 30, 45))
        d.line([(bx, by), (bx, by + bh)], fill=(35, 40, 55), width=1)
        d.rectangle([bx - 2, by - 12, bx + bw + 2, by + 2], fill=(180, 80, 20))
        d.rectangle([bx + 2, by - 18, bx + bw - 2, by - 10], fill=(220, 120, 30))
        d.rectangle([bx + 4, by - 22, bx + bw - 4, by - 16], fill=(255, 160, 40))

    # Piping
    for ly in [290, 310]:
        d.line([(780, ly), (1050, ly)], fill=(30, 35, 48), width=2)
    d.line([(820, 290), (820, 310)], fill=(30, 35, 48), width=2)
    d.line([(950, 290), (950, 310)], fill=(30, 35, 48), width=2)

    # Horizontal rules
    for ly in [180, 420]:
        d.line([(48, ly), (W - 48, ly)], fill=(30, 35, 50), width=1)

    return img


def generate_cover_auto():
    """Auto-select top strike and generate cover."""
    strikes_path = os.path.join(os.path.dirname(__file__), "..", "data", "strikes.json")
    strike = pick_top_strike(strikes_path, hours=24)

    if not strike:
        print("ERROR: No strikes found in last 24h")
        sys.exit(1)

    city = strike["city"]
    # Truncate long target descriptions for cover
    target = strike["target"]
    if len(target) > 60:
        target = target[:57] + "..."
    event = target
    date_str = strike["date"]  # "2026-07-06"

    # Format date for display
    from datetime import datetime
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    months = {6: "июня", 7: "июля"}
    date_rus = f"{dt.day} {months.get(dt.month, str(dt.month))}"

    print(f"Selected: {city} | {event} | {date_rus}")
    print(f"Confidence: {strike['confidence']}, Score: {strike['score']}")

    # Generate dark background
    bg_path = "/tmp/cover_bg.png"
    bg = _make_dark_bg()
    bg.save(bg_path, "PNG")

    # Apply caption overlay
    # Always save as today's date for the cover filename
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = f"/root/npz-tactical-map/assets/cover-{today}.png"
    caption_cover(bg_path, out_path, city, event, date_rus)

    # Cleanup
    os.remove(bg_path)
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    generate_cover_auto()
