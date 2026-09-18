#!/usr/bin/env python3
import json
from datetime import datetime, timezone

# Read the current fuel-voices.json
with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Update metadata
now = datetime.now(timezone.utc)
data['meta']['generated_at'] = now.isoformat()
data['meta']['rotation_pass'] = data['meta']['rotation_pass'] + 1

# Count voices by date
dates = {}
for voice in data['voices']:
    date = voice.get('date')
    if date:
        dates[date] = dates.get(date, 0) + 1

print(f"Updated fuel-voices.json at {now.isoformat()}")
print(f"Rotation pass: {data['meta']['rotation_pass']}")
print(f"Total voices: {len(data['voices'])}")
print(f"Dates found: {sorted(dates.keys())}")
print(f"Voices from 2026-09-18: {dates.get('2026-09-18', 0)}")

# Write back to file
with open('/root/npz-tactical-map/data/fuel-voices.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n✅ fuel-voices.json updated successfully")