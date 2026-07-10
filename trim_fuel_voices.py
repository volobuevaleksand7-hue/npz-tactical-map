import json
from datetime import datetime

# Read the JSON file
with open('data/fuel-voices.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extract meta and voices
meta = data['meta']
voices = data['voices']

# Initial count
initial_count = len(voices)
print(f"Initial record count: {initial_count}")

# Step 1: Filter by seen >= 2026-06-19
ttl_date = datetime.strptime('2026-06-19', '%Y-%m-%d')
filtered_voices = []

for voice in voices:
    seen_date = datetime.strptime(voice['seen'], '%Y-%m-%d')
    if seen_date >= ttl_date:
        filtered_voices.append(voice)

ttl_removed = initial_count - len(filtered_voices)
print(f"Records removed by TTL filter (seen < 2026-06-19): {ttl_removed}")
print(f"Records after TTL filter: {len(filtered_voices)}")

# Step 2: Sort by seen DESC, then by date DESC
filtered_voices.sort(
    key=lambda x: (x['seen'], x['date']),
    reverse=True
)

# Step 3: Trim to exactly 60 records
trim_count = len(filtered_voices) - 60
final_voices = filtered_voices[:60]

print(f"Records trimmed to reach 60-record limit: {trim_count}")
print(f"Final record count: {len(final_voices)}")

# Get first and last seen dates
if final_voices:
    first_seen = final_voices[0]['seen']
    last_seen = final_voices[-1]['seen']
    print(f"First seen date: {first_seen}")
    print(f"Last seen date: {last_seen}")

# Step 4: Reconstruct JSON with updated meta.generated_at
meta['generated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%MZ')
meta['updated_by'] = 'agent:fuel-voices-trim'

output_data = {
    'meta': meta,
    'voices': final_voices
}

# Step 5: Save with UTF-8, ensure_ascii=False, indent=1
with open('data/fuel-voices.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=1)

# Step 6: Validate JSON
with open('data/fuel-voices.json', 'r', encoding='utf-8') as f:
    validated = json.load(f)

print(f"\nJSON validation: SUCCESS")
print(f"Final voices count in validated file: {len(validated['voices'])}")
