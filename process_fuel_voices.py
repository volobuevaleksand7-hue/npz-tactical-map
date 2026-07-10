#!/usr/bin/env python3
import json
from datetime import datetime

# Load the JSON file
with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Get metadata and voices
meta = data['meta']
voices = data['voices']

print(f"Initial record count: {len(voices)}")
print(f"Initial date range: {voices[0]['seen']} to {voices[-1]['seen']}")

# Filter to keep only records where "seen" >= "2026-06-19"
cutoff_date = "2026-06-19"
filtered_voices = [v for v in voices if v['seen'] >= cutoff_date]

print(f"After filtering (seen >= {cutoff_date}): {len(filtered_voices)} records")

# Sort by seen DESC, then date DESC
sorted_voices = sorted(filtered_voices, key=lambda x: (x['seen'], x['date']), reverse=True)

# Keep only the first 60 records
final_voices = sorted_voices[:60]

print(f"Final count (first 60): {len(final_voices)}")
print(f"Numbers removed: {len(voices) - len(final_voices)}")

# Get date range of final records
if final_voices:
    seen_dates = [v['seen'] for v in final_voices]
    date_dates = [v['date'] for v in final_voices]
    print(f"Final 'seen' date range: {min(seen_dates)} to {max(seen_dates)}")
    print(f"Final 'date' field range: {min(date_dates)} to {max(date_dates)}")

# Update meta timestamp
meta['generated_at'] = datetime.utcnow().isoformat() + 'Z'

# Create new data structure
output_data = {
    'meta': meta,
    'voices': final_voices
}

# Save back to the file with indent=1, ensure_ascii=False
with open('/root/npz-tactical-map/data/fuel-voices.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=1, ensure_ascii=False)

print("\nFile saved successfully!")
print("SUMMARY:")
print(f"  - Final record count: {len(final_voices)}")
print(f"  - Records removed: {len(voices) - len(final_voices)}")
if final_voices:
    print(f"  - Date range (seen): {min(seen_dates)} to {max(seen_dates)}")
