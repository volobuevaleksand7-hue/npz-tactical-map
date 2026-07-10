import re
import json
from datetime import datetime, timedelta
import subprocess
import sys
import urllib.request

def fetch_telegram_channel(channel):
    url = f'https://t.me/s/{channel}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching {channel}: {e}", file=sys.stderr)
        return None

def extract_messages(html):
    # Pattern to find message blocks: each message has a time tag and a text div
    # We'll look for <time datetime="..."> and then the next div with class containing "tgme_widget_message_text"
    messages = []
    pattern = re.compile(r'<div class="tgme_widget_message[^>]*>.*?<time[^>]*datetime="([^"]*)"[^>]*>.*?</time>.*?<div class="tgme_widget_message_text[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE)
    matches = pattern.findall(html)
    for dt_str, text in matches:
        # Clean HTML tags from text
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        try:
            # Parse datetime string
            if dt_str.endswith('Z'):
                dt_str = dt_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(dt_str)  # This returns an aware datetime if timezone present
            # Convert to naive UTC for comparison
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
        except Exception as e:
            # Try alternative format
            try:
                dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S%z')
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
            except:
                continue
        messages.append((dt, text))
    return messages

def is_strike_message(text):
    # Keywords indicating a strike on Russian oil infrastructure
    # Using escaped Cyrillic to avoid confusable characters
    patterns = [
        r'(?i)(\u0443\u0434\u0430\u0440|\u0443\u0434\u0430\u0440[ья]|\u0443\u0434\u0430\u0440[оу]|\u0443\u0434\u0430\u0440[а-я]*).*?(\u0434\u0440\u043e\u043d\u044b|\u0411\u041f\u041b|\u0431\u0435\u0441\u043f\u0438\u043b\u043e\u043b\u0438\u0442\u043d\u0438\u043a)',
        r'(?i)(\u0434\u0440\u043e\u043d\u044b|\u0411\u041f\u041b|\u0431\u0435\u0441\u043f\u0438\u043b\u043e\u043b\u0438\u0442\u043d\u0438\u043a).*?(\u0443\u0434\u0430\u0440|\u0443\u0434\u0430\u0440[ья]|\u0443\u0434\u0430\u0440[оу]|\u0443\u0434\u0430\u0440[а-я]*|\u0443\u0434\u0430\u0440\u0443\u0434\u0430\u0440|удар|ударить|поразил)',
        r'(?i)(\u043d\u0435\u0444\u0442\u0435\u043f\u0435\u0440\u0430\u0431\u043e\u0442\u044c\u043d\u044b\u0439 \u0437\u0430\u0432\u043e\u0434|\u043d\u0435\u0444\u0442\u0435\u0431\u0430\u0437\u0430|\u043d\u0435\u0444\u0442\u0435\u043f\u0440\u043e\u0432\u043e\u0434|\u0442\u043e\u043f\u043b\u0438\u0432)',
        r'(?i)(\u0413\u0421\u041c|\u0442\u043e\u043f\u043b\u0438\u0432|\u043d\u0435\u0444\u0442).*?(\u0443\u0434\u0430\u0440|\u0443\u0434\u0430\u0440[ья]|\u0443\u0434\u0430\u0440[оу]|\u0443\u0434\u0430\u0440[а-я]*|\u0443\u0434\u0430\u0440\u0443\u0434\u0430\u0440|удар|попадание|пожар|взрыв)',
        r'(?i)(\u0413\u0423\u0420|\u0413\u0435\u043d\u0448\u0442\u0430\u0412\u0423\u0421|\u0423\u043a\u0440\u0430\u0438\u043d\u0441\u043a\u0438\u0435 \u0421\u0438\u043b\u044b).*?(\u0443\u0434\u0430\u0440|\u0443\u0434\u0430\u0440[ья]|\u0443\u0434\u0430\u0440[оу]|\u0443\u0434\u0430\u0440[а-я]*|\u0443\u0434\u0430\u0440\u0443\u0434\u0430\u0440)',
        r'(?i)(\u0434\u0440\u043e\u043d[аы]?|\u0411\u0435\u0441\u043f\u0438\u043b\u043e\u0442\u043d\u0438\u043a).*?\u0443\u0434\u0430\u0440',
        r'(?i)(\u043f\u0430\u0440\u0438\u0432\u0430\u043b|\u043f\u0430\u0440\u0438\u0432\u0430\u043b[ья]|\u043f\u0430\u0440\u0438\u0432\u0430\u043b[оу]|\u043f\u0430\u0440\u0438\u0432\u0430\u043b[а-я]*).*?(\u043d\u0435\u0444\u0442\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442|\u043d\u0435\u0444\u0442\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442|нефть|ГСМ|завод|депо)',
    ]
    for pat in patterns:
        if re.search(pat, text):
            return True
    return False

def extract_details(text, dt):
    # Extract city and region from text
    city = ''
    region = ''
    # Look for patterns like "в [Город], [область]" or "в [Город] ([область])"
    # We'll look for sequences of Cyrillic words that might be city and region.
    # This is a heuristic and might not be perfect.
    # Pattern: "в " followed by one or two words (city) then comma or space, then one or two words (region) that might contain "область", "край", "респ", etc.
    match = re.search(r'в\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)*)\s*[,\s]+\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)*(?:\s+(?:область|край|респ|республика|округ|АО|АО))?', text)
    if match:
        city = match.group(1)
        region = match.group(2)
    else:
        # Try just city
        match = re.search(r'в\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)*)', text)
        if match:
            city = match.group(1)
    # Defaults
    lat = None
    lon = None
    # Type
    typ = 'drone' if re.search(r'(?i)(дроны?|БПЛА|беспилотник)', text) else 'unknown'
    # Count - unknown
    count = None
    # Target - extract phrase after "удар" or "по удар"
    target = ''
    match = re.search(r'(?i)(?:удар[ья]?\s+по\s+|по\s+удар[ья]?\s+)([^\.]+)', text)
    if match:
        target = match.group(1).strip()
    else:
        # Try just after "удар"
        match = re.search(r'(?i)удар[ья]?\s+([^\.]+)', text)
        if match:
            target = match.group(1).strip()
    # Casualties
    casualties = ''
    match = re.search(r'(?:погиб|ранен|жертв|пострадал)[^.]*\d+', text, re.I)
    if match:
        casualties = match.group(0).strip()
    # Title - first 100 chars
    title = text[:100].strip()
    # Detail - first 500 chars
    detail = text[:500].strip()
    # Source URL - we'll approximate by using the timestamp
    # We don't have the message ID, so we'll leave a placeholder and update later if possible?
    # For now, we'll set to the channel URL (we don't know which channel, but we'll set it later)
    source_url = ''  # Will be set later
    # Confidence
    confidence = 'reported'
    if re.search(r'(?i)(подтверждено|подтверждает|подтверждается|официально|ГШ ВСУ|ГУР)', text):
        confidence = 'confirmed'
    elif re.search(r'(?i)(слухи|неподтверждённо|возможно|по данным)', text):
        confidence = 'rumored'
    return {
        'date': dt.strftime('%Y-%m-%d'),
        'time': dt.strftime('%H:%M'),
        'city': city,
        'region': region,
        'lat': lat,
        'lon': lon,
        'type': typ,
        'count': count,
        'target': target,
        'casualties': casualties,
        'title': title,
        'detail': detail,
        'source_url': source_url,
        'confidence': confidence
    }

def load_existing_strikes():
    try:
        with open('/root/npz-tactical-map/data/strikes.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('strikes', [])
    except Exception as e:
        print(f"Error loading strikes.json: {e}", file=sys.stderr)
        return []

def is_duplicate(new_strike, existing_strikes):
    for ex in existing_strikes:
        if ex['date'] == new_strike['date'] and ex.get('city') == new_strike.get('city'):
            # Check time within 2 hours
            try:
                t1 = datetime.strptime(ex['date'] + ' ' + (ex.get('time') or '00:00'), '%Y-%m-%d %H:%M')
                t2 = datetime.strptime(new_strike['date'] + ' ' + (new_strike.get('time') or '00:00'), '%Y-%m-%d %H:%M')
                if abs((t1 - t2).total_seconds()) <= 2 * 3600:
                    # Additionally check target similarity if both have targets
                    if ex.get('target') and new_strike.get('target'):
                        # Simple word overlap
                        set1 = set(ex['target'].lower().split())
                        set2 = set(new_strike['target'].lower().split())
                        if len(set1 & set2) > 0:
                            return True
                    else:
                        # If no target, consider duplicate if same date and city and time close
                        return True
            except:
                pass
    return False

def main():
    channels = ['exilenova_plus', 'radarrussiia', 'noel_reports']
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    new_strikes = []
    for channel in channels:
        html = fetch_telegram_channel(channel)
        if not html:
            continue
        messages = extract_messages(html)
        for dt, text in messages:
            if dt < one_hour_ago:
                continue
            if is_strike_message(text):
                strike = extract_details(text, dt)
                strike['source_url'] = f'https://t.me/{channel}/{int(dt.timestamp())}'  # approximate
                new_strikes.append(strike)
    # Deduplicate
    existing = load_existing_strikes()
    filtered = []
    for strike in new_strikes:
        if not is_duplicate(strike, existing):
            filtered.append(strike)
    if filtered:
        print(f"Found {len(filtered)} new strike(s)")
        # Load existing data to update
        with open('/root/npz-tactical-map/data/strikes.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Prepend new strikes (so newest first)
        data['strikes'] = filtered + data['strikes']
        # Update generated_at
        data['generated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        # Write back
        with open('/root/npz-tactical-map/data/strikes.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Updated strikes.json")
        # Commit and push
        subprocess.run(['bash', '/root/npz-tactical-map/agents/git-sync.sh', 
                        f'data(newswatch): sync {datetime.utcnow().isoformat(timespec="seconds")}', 
                        'strikes'], 
                        cwd='/root/npz-tactical-map', check=False)
        # Run strike pipeline
        subprocess.run(['python3', '/root/npz-tactical-map/hermes/bot/strike_pipeline.py'], 
                        cwd='/root/npz-tactical-map', check=False)
        print("Executed strike pipeline")
    else:
        print("No new strikes found")
        # Still update generated_at
        with open('/root/npz-tactical-map/data/strikes.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['generated_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        with open('/root/npz-tactical-map/data/strikes.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Updated generated_at only")
        # Do not run strike pipeline per instructions

if __name__ == '__main__':
    main()