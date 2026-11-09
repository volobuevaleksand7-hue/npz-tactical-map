#!/usr/bin/env python3
import json
import datetime
import os

def update_generated_at():
    """Update the generated_at timestamp in fuel-voices.json"""
    
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Get current time in UTC
    current_time = datetime.datetime.now(datetime.timezone.utc)
    
    # Update the generated_at field
    data['meta']['generated_at'] = current_time.isoformat()
    
    # Increment rotation_pass
    data['meta']['rotation_pass'] = data['meta'].get('rotation_pass', 0) + 1
    
    # Write back to file
    with open('/root/npz-tactical-map/data/fuel-voices.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Updated generated_at to: {current_time.isoformat()}")
    print(f"Incremented rotation_pass to: {data['meta']['rotation_pass']}")
    
    return True

if __name__ == "__main__":
    update_generated_at()