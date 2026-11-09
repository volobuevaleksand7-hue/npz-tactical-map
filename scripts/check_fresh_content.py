#!/usr/bin/env python3
import json
import datetime
import sys
import os
from pathlib import Path

def check_fresh_voices():
    # Load current data
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    current_time = datetime.datetime.now(datetime.timezone.utc)
    eight_hours_ago = current_time - datetime.timedelta(hours=8)
    
    print(f"Current time: {current_time}")
    print(f"Eight hours ago: {eight_hours_ago}")
    print(f"Generated at: {data['meta']['generated_at']}")
    
    # Check for entries that need to be updated
    voices = data['voices']
    
    # Count entries by date
    dates = {}
    for voice in voices:
        date = voice['date']
        if date not in dates:
            dates[date] = 0
        dates[date] += 1
    
    print(f"\nEntries by date:")
    for date, count in sorted(dates.items(), reverse=True):
        print(f"  {date}: {count}")
    
    # Check if there are entries from today that might need updating
    today = "2026-11-06"
    today_entries = [v for v in voices if v['date'] == today]
    print(f"\nEntries from {today}: {len(today_entries)}")
    
    for entry in today_entries:
        print(f"  - {entry.get('region', 'Unknown')}, {entry.get('city', 'Unknown')}: {entry.get('quote', '')[:100]}...")
    
    # Check if we need to update (based on generated_at)
    generated_at_str = data['meta']['generated_at']
    try:
        generated_at = datetime.datetime.fromisoformat(generated_at_str)
        hours_since_update = (current_time - generated_at).total_seconds() / 3600
        print(f"\nHours since last update: {hours_since_update:.2f}")
        
        if hours_since_update >= 8:
            print("Need to update with fresh content!")
            return True
        else:
            print("No need to update yet (less than 8 hours since last update)")
            return False
    except Exception as e:
        print(f"Error parsing generated_at: {e}")
        return False

if __name__ == "__main__":
    check_fresh_voices()