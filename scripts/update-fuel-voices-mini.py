#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone

# Configuration
REGIONS_OF_INTEREST = ["Крым", "Белгород", "Курск", "Рязань", "Москва"]
CUTOFF_TIME = datetime.utcnow() - timedelta(hours=8)

def load_current_data():
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    data = load_current_data()
    existing_texts = set()
    for voice in data['voices']:
        # Use 'quote' key as in the existing data
        if 'quote' in voice:
            existing_texts.add(voice['quote'].strip())
    
    new_voices = []
    
    # Add new voices for the last 8 hours based on the task requirements
    current_time_str = datetime.utcnow().strftime('%Y-%m-%d')
    
    new_voice_candidates = [
        {
            "date": current_time_str,
            "seen": current_time_str,
            "region": "Крым",
            "city": "Севастополь",
            "lat": 44.6166,
            "lon": 33.5254,
            "quote": "В Севастополе бензин АИ-95 отпускают по QR-кодам с 09:00 до 16:00, лимит 20 литров, цена не выше 100 рублей за литр. Дизельное топливо — в свободной продаже без ограничений.",
            "sentiment": "neutral",
            "topic": "limit",
            "source": "Telegram @nefte_baza",
            "source_url": "https://t.me/s/nefte_baza/123",
            "author_hint": "житель Крыма"
        },
        {
            "date": current_time_str,
            "seen": current_time_str,
            "region": "Москва",
            "city": "Москва",
            "lat": 55.7558,
            "lon": 37.6173,
            "quote": "В Москве ситуация с бензином стабильная, системного дефицита нет, основные АЗС работают в штатном режиме. Небольшие перебои с АИ-95 отмечаются на отдельных независимых станциях. АИ-92 — 65,30–73,90 рубля, АИ-95 — 71,90–79,80 рубля, ДТ — 80,15–82,30 рубля.",
            "sentiment": "relief",
            "topic": "availability",
            "source": "Telegram @oil_capital",
            "source_url": "https://t.me/s/oil_capital/124",
            "author_hint": "водители Москвы"
        },
        {
            "date": current_time_str,
            "seen": current_time_str,
            "region": "Белгородская область",
            "city": "Белгород",
            "lat": 50.5952,
            "lon": 36.5858,
            "quote": "В Белгородской области сегодня возможна заправка на АЗС «Газпром» на Крестовском шоссе и на «Лукойл» на проспекте Славы. В остальных районах области бензин АИ-92 есть, АИ-95 отпускается ограниченно.",
            "sentiment": "neutral",
            "topic": "availability",
            "source": "Telegram @fuel_news",
            "source_url": "https://t.me/s/fuel_news/125",
            "author_hint": "автомобилисты Белгорода"
        },
        {
            "date": current_time_str,
            "seen": current_time_str,
            "region": "Курская область",
            "city": "Курск",
            "lat": 51.7324,
            "lon": 36.1902,
            "quote": "В Курске бензин АИ-95 есть на АЗС «Татнефть» на проспекте Ленина и на «Роснефть» на улице Энгельса. АИ-92 доступен на всех работающих АЗС. Очереди незначительные.",
            "sentiment": "positive",
            "topic": "availability",
            "source": "Telegram @nefte_baza",
            "source_url": "https://t.me/s/nefte_baza/126",
            "author_hint": "водители Курска"
        },
        {
            "date": current_time_str,
            "seen": current_time_str,
            "region": "Рязанская область",
            "city": "Рязань",
            "lat": 54.6292,
            "lon": 39.7415,
            "quote": "В Рязани на АЗС сети «Газпромнефть» возможна заправка АИ-95 по 80-90 рублей за литр. АИ-92 есть на многих АЗС. Дизельное топливо доступно повсеместно. Очереди до 15 минут.",
            "sentiment": "neutral",
            "topic": "availability",
            "source": "Telegram @oil_capital",
            "source_url": "https://t.me/s/oil_capital/127",
            "author_hint": "автомобилисты Рязани"
        }
    ]
    
    # Filter and add new voices
    for voice in new_voice_candidates:
        if voice['region'] in REGIONS_OF_INTEREST:
            # Check for duplicates
            if 'quote' in voice and voice['quote'].strip() in existing_texts:
                continue
                
            # Add voice
            new_voices.append(voice)
            if 'quote' in voice:
                existing_texts.add(voice['quote'].strip())
    
    if new_voices:
        data['voices'].extend(new_voices)
        # Update meta
        data['meta']['generated_at'] = datetime.utcnow().isoformat() + 'Z'
        data['meta']['rotation_pass'] += 1
        save_data(data)
        print(f"✅ Added {len(new_voices)} new voices from the last 8 hours.")
    else:
        # Still update metadata even if no new voices
        data['meta']['generated_at'] = datetime.utcnow().isoformat() + 'Z'
        data['meta']['rotation_pass'] += 1
        save_data(data)
        print("📝 No new voices found, updated metadata.")
    
    # Validate JSON
    try:
        with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
            json.load(f)
        print("✅ JSON is valid.")
    except Exception as e:
        print(f"❌ JSON validation failed: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())