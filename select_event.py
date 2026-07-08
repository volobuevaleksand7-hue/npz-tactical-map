import json
import sys

with open('data/strikes.json') as f:
    data = json.load(f)

strikes = data['strikes']

# Determine the two most recent dates present in the data
dates = sorted(set(s['date'] for s in strikes if 'date' in s), reverse=True)
if len(dates) >= 2:
    target_dates = dates[:2]
else:
    target_dates = dates
print("Considering dates:", target_dates, file=sys.stderr)

def is_npz(target):
    if not target:
        return False
    t = target.lower()
    return ('нпз' in t) or ('нефтеперерабатывающий завод' in t) or ('нефтеперерабатывающий узел' in t)

def is_large_npz(city, target):
    large_cities = {'Омск', 'Куйбышев', 'Рязань', 'Сызрань', 'Ачинск'}
    if city in large_cities:
        return True
    return False

def is_confirmed(conf):
    return conf == 'confirmed'

# Determine the most recent date (today) for "new" bonus
all_dates = [s['date'] for s in strikes if 'date' in s]
if all_dates:
    max_date = max(all_dates)
else:
    max_date = None

def is_new_date(date):
    return date == max_date

def score_strike(strike):
    date = strike.get('date')
    if date not in target_dates:
        return -1  # ignore
    city = strike.get('city', '')
    target = strike.get('target', '')
    conf = strike.get('confidence', '')
    score = 0
    # NPZ down? Assume if NPZ hit then down (status: down)
    if is_npz(target):
        score += 4  # max priority
    # large NPZ
    if is_large_npz(city, target):
        score += 3
    # confirmed
    if is_confirmed(conf):
        score += 2
    # new (today)
    if is_new_date(date):
        score += 1
    return score

candidates = []
for s in strikes:
    sc = score_strike(s)
    if sc >= 0:
        candidates.append((sc, s))

# Sort by score descending, then by date descending (newer first)
def sort_key(item):
    score, strike = item
    date = strike.get('date', '')
    return (score, date)

candidates.sort(key=sort_key, reverse=True)

print("Top candidates:", file=sys.stderr)
for score, s in candidates[:10]:
    print(f"Score {score}: {s.get('city')} - {s.get('target')} ({s.get('date')}) {s.get('confidence')}", file=sys.stderr)

if candidates:
    best_score, best = candidates[0]
    print("\nSelected:", file=sys.stderr)
    print(f"City: {best.get('city')}", file=sys.stderr)
    print(f"Target: {best.get('target')}", file=sys.stderr)
    print(f"Date: {best.get('date')}", file=sys.stderr)
    print(f"Confidence: {best.get('confidence')}", file=sys.stderr)
    # Output as JSON for easy parsing
    result = {
        "city": best.get('city'),
        "target": best.get('target'),
        "date": best.get('date')
    }
    print(json.dumps(result))
else:
    print("{}", file=sys.stderr)
