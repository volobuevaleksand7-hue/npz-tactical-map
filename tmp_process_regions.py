import json
from datetime import datetime

# Read the fuel-availability.json file
with open('/root/npz-tactical-map/data/fuel-availability.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extract regions
regions = data.get('regions', [])

# Parse updated timestamps and sort by oldest first
def parse_date(date_str):
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return datetime.min

# Sort regions by updated timestamp (oldest first)
sorted_regions = sorted(regions, key=lambda r: parse_date(r.get('updated', '1970-01-01T00:00:00Z')))

# Get the 12 oldest regions
oldest_12 = sorted_regions[:12]

print("12 oldest regions (by updated field):")
for i, region in enumerate(oldest_12, 1):
    print(f"{i:2d}. {region.get('region', 'Unknown')} - updated: {region.get('updated', 'Unknown')}")

# Also identify STALE regions (updated older than 7 days)
now = datetime.now()
stale_threshold = now.timestamp() - (7 * 24 * 3600)  # 7 days ago in seconds

stale_regions = []
for region in regions:
    updated_str = region.get('updated', '1970-01-01T00:00:00Z')
    try:
        updated_dt = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
        if updated_dt.timestamp() < stale_threshold:
            stale_regions.append(region)
    except:
        pass

print(f"\nSTALE regions (updated older than 7 days): {len(stale_regions)} regions")
for region in stale_regions[:10]:  # Show first 10
    print(f"  - {region.get('region', 'Unknown')} - updated: {region.get('updated', 'Unknown')}")

if len(stale_regions) > 10:
    print(f"  ... and {len(stale_regions) - 10} more")

# Save the oldest 12 for later use
with open('/root/npz-tactical-map/tmp_oldest_12_regions.json', 'w', encoding='utf-8') as f:
    json.dump(oldest_12, f, ensure_ascii=False, indent=2)

print("\nSaved oldest 12 regions to /root/npz-tactical-map/tmp_oldest_12_regions.json")