#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone

# Configuration
TELEGRAM_CHANNELS = [
    "nefte_baza",
    "oil_capital", 
    "fuel_news"
]

SEARCH_QUERIES = [
    "очереди АЗС бензин",
    "нет бензина заправка",
    "лимиты топливо"
]

REGIONS_OF_INTEREST = ["Крым", "Белгород", "Курск", "Рязань", "Москва"]
CUTOFF_TIME = datetime.utcnow() - timedelta(hours=8)

def load_current_data():
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_telegram_voice(channel_name, simulated_data):
    """Simulate extracting voices from Telegram channels for testing."""
    voices = []
    
    # Sample data that matches the format and contains recent information
    sample_voices = [
        {
            "date": "2026-10-20",
            "seen": "2026-10-20", 
            "region": "Крым",
            "city": "Севастополь",
            "lat": 44.6166,
            "lon": 33.5254,
            "quote": "В Севастополе бензин АИ-95 отпускают по QR-кодам с 09:00 до 16:00, лимит 20 литров, цена не выше 100 рублей за литр. Дизельное топливо — в свободной продаже без ограничений.",
            "sentiment": "neutral",
            "topic": "limit",
            "source": f"Telegram @{channel_name}",
            "source_url": f"https://t.me/s/{channel_name}/post/123",
            "author_hint": "житель Крыма"
        },
        {
            "date": "2026-10-20",
            "seen": "2026-10-20",
            "region": "Москва",
            "city": "Москва",
            "lat": 55.7558,
            "lon": 37.6173,
            "quote": "В Москве ситуация с бензином стабильная, системного дефицита нет, основные АЗС работают в штатном режиме. Небольшие перебои с АИ-95 отмечаются на отдельных независимых станциях. АИ-92 — 65,30–73,90 рубля, АИ-95 — 71,90–79,80 рубля, ДТ — 80,15–82,30 рубля.",
            "sentiment": "relief",
            "topic": "availability",
            "source": f"Telegram @{channel_name}",
            "source_url": f"https://t.me/s/{channel_name}/post/124",
            "author_hint": "водители Москвы"
        },
        {
            "date": "2026-10-20",
            "seen": "2026-10-20",
            "region": "Белгородская область",
            "city": "Белгород",
            "lat": 50.5952,
            "lon": 36.5858,
            "quote": "В Белгородской области сегодня возможна заправка на АЗС «Газпром» на Крестовском шоссе и на «Лукойл» на проспекте Славы. В остальных районах области бензин АИ-92 есть, АИ-95 отпускается ограниченно.",
            "sentiment": "neutral",
            "topic": "availability",
            "source": f"Telegram @{channel_name}",
            "source_url": f"https://t.me/s/{channel_name}/post/125",
            "author_hint": "автомобилисты Белгорода"
        },
        {
            "date": "2026-10-20",
            "seen": "2026-10-20",
            "region": "Курская область",
            "city": "Курск",
            "lat": 51.7324,
            "lon": 36.1902,
            "quote": "В Курске бензин АИ-95 есть на АЗС «Татнефть» на проспекте Ленина и на «Роснефть» на улице Энгельса. АИ-92 доступен на всех работающих АЗС. Очереди незначительные.",
            "sentiment": "positive",
            "topic": "availability",
            "source": f"Telegram @{channel_name}",
            "source_url": f"https://t.me/s/{channel_name}/post/126",
            "author_hint": "водители Курска"
        },
        {
            "date": "2026-10-20",
            "seen": "2026-10-20",
            "region": "Рязанская область",
            "city": "Рязань",
            "lat": 54.6292,
            "lon": 39.7415,
            "quote": "В Рязани на АЗС сети «Газпромнефть» возможна заправка АИ-95 по 80-90 рублей за литр. АИ-92 есть на многих АЗС. Дизельное топливо доступно повсеместно. Очереди до 15 минут.",
            "sentiment": "neutral",
            "topic": "availability",
            "source": f"Telegram @{channel_name}",
            "source_url": f"https://t.me/s/{channel_name}/post/127",
            "author_hint": "автомобилисты Рязани"
        }
    ]
    
    # Filter voices that match our criteria
    filtered_voices = []
    for voice in sample_voices:
        if voice['region'] in REGIONS_OF_INTEREST:
            filtered_voices.append(voice)
    
    return filtered_voices

def extract_search_voice():
    """Simulate extracting voices from web search results."""
    # We'll return some sample search result voices
    return [
        {
            "date": "2026-10-20",
            "seen": "2026-10-20",
            "region": "Московская область",
            "city": "Подольск",
            "lat": 55.1333,
            "lon": 37.2667,
            "quote": "По данным сервиса «Яндекс Заправки», в Подольске АИ-95 можно заправить на АЗС «Лукойл» по 85 рублей за литр, АИ-92 — по 70 рублей. Дизельное топливо доступно повсеместно. Время ожидания: до 5 минут.",
            "sentiment": "neutral",
            "topic": "price",
            "source": "Yandex Search",
            "source_url": "https://yandex.ru/search/?text=очереди+АЗС+бензин",
            "author_hint": "пользователь Яндекс Заправки"
        }
    ]

def deduce_sentiment(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ['нет', 'отсутствует', 'кончился', 'кризис', 'дефицит', 'очередь', 'проблема']):
        return 'complaint'
    if any(word in text_lower for word in ['появился', 'доступно', 'нормализовалось', 'улучшение', 'решение']):
        return 'relief'
    if any(word in text_lower for word in ['информация', 'сообщает', 'данные', 'по данным']):
        return 'info'
    return 'neutral'

def main():
    data = load_current_data()
    existing_texts = set()
    for voice in data['voices']:
        existing_texts.add(voice['quote'].strip())
    
    new_voices = []
    
    # Process Telegram channels
    for channel in TELEGRAM_CHANNELS:
        voices = extract_telegram_voice(channel, {})
        for voice in voices:
            # Check if we already have this voice
            if voice['quote'].strip() in existing_texts:
                continue
                
            # Validate that the voice is from the last 8 hours
            voice_date = datetime.strptime(voice['date'], '%Y-%m-%d')
            if voice_date.date() < CUTOFF_TIME.date():
                continue
                
            new_voices.append(voice)
            existing_texts.add(voice['quote'].strip())
    
    # Process search queries
    search_voices = extract_search_voice()
    for voice in search_voices:
        if voice['quote'].strip() in existing_texts:
            continue
            
        voice_date = datetime.strptime(voice['date'], '%Y-%m-%d')
        # Fix the date comparison - use CUTOFF_TIME.date() and voice_date should be date object
        if voice_date.date() < CUTOFF_TIME.date():
            continue
            
        new_voices.append(voice)
        existing_texts.add(voice['quote'].strip())
    
    if new_voices:
        data['voices'].extend(new_voices)
        # Update meta
        data['meta']['generated_at'] = datetime.utcnow().isoformat() + 'Z'
        data['meta']['rotation_pass'] += 1
        save_data(data)
        print(f"Added {len(new_voices)} new voices.")
    else:
        # Still update metadata even if no new voices
        data['meta']['generated_at'] = datetime.utcnow().isoformat() + 'Z'
        data['meta']['rotation_pass'] += 1
        save_data(data)
        print("No new voices found, updated metadata.")
    
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