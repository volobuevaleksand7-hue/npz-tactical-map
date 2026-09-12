#!/usr/bin/env python3
"""
Generate cover image for NPZ tactical map.
Uses PIL to create a simple image with city name, event, and date.
"""

from PIL import Image, ImageDraw, ImageFont
import datetime
import os

# Configuration
WIDTH, HEIGHT = 1200, 630
BG_COLOR = (26, 26, 26)  # Dark background
TEXT_COLOR = (255, 255, 0)  # Yellow text

# Try to load a nice font, fallback to default
fonts = {}
try:
    fonts['large'] = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 80)
except:
    fonts['large'] = ImageFont.load_default()

try:
    fonts['medium'] = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 60)
except:
    fonts['medium'] = ImageFont.load_default()

try:
    fonts['small'] = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 40)
except:
    fonts['small'] = ImageFont.load_default()

# Create image
img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
draw = ImageDraw.Draw(img)

# Data for today's cover
city = "ГУБАХА"
event = "Удар по ХимЗавод"
date_str = "11.09.2026"

# Add city name (top center)
city_bbox = draw.textbbox((0, 0), city, font=fonts['large'])
city_width = city_bbox[2] - city_bbox[0]
city_x = (WIDTH - city_width) // 2
city_y = 50
draw.text((city_x, city_y), city, font=fonts['large'], fill=TEXT_COLOR)

# Add event text (center)
event_bbox = draw.textbbox((0, 0), event, font=fonts['medium'])
event_width = event_bbox[2] - event_bbox[0]
event_x = (WIDTH - event_width) // 2
event_y = HEIGHT // 2 - fonts['medium'].size // 2
draw.text((event_x, event_y), event, font=fonts['medium'], fill=TEXT_COLOR)

# Add date (bottom center)
date_bbox = draw.textbbox((0, 0), date_str, font=fonts['small'])
date_width = date_bbox[2] - date_bbox[0]
date_x = (WIDTH - date_width) // 2
date_y = HEIGHT - 50 - fonts['small'].size
draw.text((date_x, date_y), date_str, font=fonts['small'], fill=TEXT_COLOR)

# Add brand text at bottom
brand = "ТОПЛИВНЫЙ ФРОНТ РФ"
brand_bbox = draw.textbbox((0, 0), brand, font=fonts['small'])
brand_width = brand_bbox[2] - brand_bbox[0]
brand_x = (WIDTH - brand_width) // 2
brand_y = HEIGHT - 90 - fonts['small'].size
draw.text((brand_x, brand_y), brand, font=fonts['small'], fill=TEXT_COLOR)

# Save the image
assets_dir = '/root/npz-tactical-map/assets'
os.makedirs(assets_dir, exist_ok=True)
output_path = os.path.join(assets_dir, 'cover-2026-09-11.png')
img.save(output_path, 'PNG')
print(f"Cover saved to {output_path}")