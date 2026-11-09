#!/usr/bin/env python3
import json
import datetime
import os
from pathlib import Path

def search_for_fresh_content():
    """
    Simulate searching for fresh content from the sources mentioned in the task.
    Since we can't access Telegram channels directly, we'll create a script
    that demonstrates the search process and shows what kind of content we should look for.
    """
    print("Searching for fresh fuel voices from the last 8 hours...")
    
    # Sources mentioned in the task
    sources = [
        "t.me/s/nefte_baza",
        "t.me/s/oil_capital", 
        "t.me/s/fuel_news"
    ]
    
    regions = ["Крым", "Белгород", "Курск", "Рязань", "Москва"]
    
    search_queries = [
        "очереди АЗС бензин",
        "нет бензина заправка", 
        "лимиты топливо"
    ]
    
    print("Sources to check:")
    for source in sources:
        print(f"  - {source}")
    
    print("\nRegions to monitor:")
    for region in regions:
        print(f"  - {region}")
    
    print("\nSearch queries:")
    for query in search_queries:
        print(f"  - {query}")
    
    # Check if we have any recent content from the existing data
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    current_time = datetime.datetime.now(datetime.timezone.utc)
    eight_hours_ago = current_time - datetime.timedelta(hours=8)
    
    print(f"\nCurrent time: {current_time}")
    print(f"Searching for content after: {eight_hours_ago}")
    
    # Look for content that might be newer than our last update
    latest_entry_time = None
    for voice in data['voices']:
        # Try to parse seen date (assuming format YYYY-MM-DD)
        try:
            seen_date = datetime.datetime.strptime(voice['seen'], "%Y-%m-%d")
            if latest_entry_time is None or seen_date > latest_entry_time:
                latest_entry_time = seen_date
        except:
            pass
    
    if latest_entry_time:
        print(f"Latest entry seen date: {latest_entry_time}")
    
    print("\nNote: To actually get fresh content, we would need to:")
    print("1. Access the Telegram channels mentioned")
    print("2. Search social media for the specific queries")
    print("3. Monitor the specified regions for fuel updates")
    print("4. Collect new voices and add them to the dataset")
    
    return False  # No fresh content found without actual access

if __name__ == "__main__":
    search_for_fresh_content()