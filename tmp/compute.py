import json
import sys

with open('data/fuel-state.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

refineries = data['refineries']
total_capacity = sum(r['capacity_mt_year'] for r in refineries)
offline_capacity = sum(r['capacity_mt_year'] for r in refineries if r['status'] == 'down')
offline_pct = round(offline_capacity / total_capacity * 100) if total_capacity else 0
# throughput shortfall: sum(capacity * (1 - est_output_pct/100))
shortfall = sum(r['capacity_mt_year'] * (1 - r['est_output_pct']/100) for r in refineries)
throughput_shortfall_pct = round(shortfall / total_capacity * 100) if total_capacity else 0

# gasoline and diesel output loss percentages: we can keep existing or compute? 
# We'll keep existing for now.
# We'll also compute total gasoline and diesel production? Not needed.

print(f"refining_capacity_total_mt_year: {total_capacity:.1f}")
print(f"capacity_offline_mt_year: {offline_capacity:.1f}")
print(f"capacity_offline_pct: {offline_pct}")
print(f"throughput_shortfall_pct: {throughput_shortfall_pct}")

# Also compute counts
status_counts = {}
for r in refineries:
    s = r['status']
    status_counts[s] = status_counts.get(s, 0) + 1
print(f"Status counts: {status_counts}")