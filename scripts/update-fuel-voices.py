#!/usr/bin/env python3
"""
OSINT Fuel Voices Update Script
Updates data/fuel-voices.json with fresh public fuel voices from Telegram channels and web searches.
"""

import json
import re
import time
from datetime import datetime, timedelta
import subprocess
import os

def load_current_data():
    """Load current fuel-voices.json data"""
    try:
        with open('/root/npz-tactical-map/data/fuel-voices.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading current data: {e}")
        return {"meta": {}, "voices": []}

def save_updated_data(data):
    """Save updated data to fuel-voices.json"""
    try:
        # Update meta information
        current_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        data['meta']['generated_at'] = current_time
        data['meta']['rotation_pass'] = data['meta'].get('rotation_pass', 0) + 1
        data['meta']['updated_by'] = 'script:fuel-voices'
        
        # Write updated data
        with open('/root/npz-tactical-map/data/fuel-voices.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Data saved successfully at {current_time}")
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def validate_json():
    """Validate JSON syntax"""
    try:
        result = subprocess.run(
            ['python3', '-m', 'json.tool', '/root/npz-tactical-map/data/fuel-voices.json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("JSON validation successful")
            return True
        else:
            print(f"JSON validation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error validating JSON: {e}")
        return False

def run_git_sync(message, description):
    """Run git-sync.sh script"""
    try:
        script_path = '/root/npz-tactical-map/agents/git-sync.sh'
        if os.path.exists(script_path):
            cmd = [script_path, message, description]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(f"Git sync completed: {message}")
                return True
            else:
                print(f"Git sync failed: {result.stderr}")
                return False
        else:
            print(f"Git sync script not found at {script_path}")
            return False
    except Exception as e:
        print(f"Error running git sync: {e}")
        return False

def extract_new_voices_from_telegram():
    """Extract new voices from Telegram channels"""
    new_voices = []
    current_date = datetime.utcnow()
    cutoff_date = current_date - timedelta(hours=8)
    
    # Keywords to search for
    keywords = [
        "очередь АЗС бензин", "нет бензина заправка", "лимиты топливо",
        "нет бензина", "очередь на АЗС", "лимит топлива", 
        "АЗС не работает", "заправка закрыта", "дефицит топлива"
    ]
    
    regions = ["Крым", "Белгород", "Курск", "Рязань", "Москва"]
    
    # Test Telegram channels
    channels = [
        ("nefte_baza", "https://t.me/s/nefte_baza"),
        ("oil_capital", "https://t.me/s/oil_capital"),
        # fuel_news channel is empty/private, so we'll skip it
    ]
    
    for channel_name, channel_url in channels:
        try:
            print(f"Processing channel: {channel_name}")
            
            # Fetch channel content using curl
            cmd = ['curl', '-s', channel_url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
            if result.returncode == 0 and result.stdout:
                content = result.stdout
                
                # Extract message blocks
                message_blocks = re.findall(
                    r'<div class="tgme_widget_message_wrap">.*?</div>\s*</div>',
                    content,
                    re.DOTALL
                )
                
                for block in message_blocks:
                    # Extract timestamp
                    time_match = re.search(
                        r'<time datetime="([^"]+)"',
                        block
                    )
                    
                    # Extract message text
                    text_match = re.search(
                        r'<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>',
                        block,
                        re.DOTALL
                    )
                    
                    if text_match:
                        text = re.sub(r'<[^>]+>', ' ', text_match.group(1))
                        text = re.sub(r'\s+', ' ', text).strip()
                        
                        # Check if text contains fuel-related keywords
                        text_lower = text.lower()
                        keyword_found = any(keyword.lower() in text_lower for keyword in keywords)
                        
                        if keyword_found:
                            # Extract date from timestamp if available
                            post_date = cutoff_date
                            if time_match:
                                try:
                                    # Parse Telegram timestamp (format may vary)
                                    timestamp = time_match.group(1)
                                    # Try to parse different timestamp formats
                                    if 'T' in timestamp:  # ISO format
                                        post_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                    else:
                                        # Try to parse other formats
                                        post_date = datetime.strptime(timestamp.split(' ')[0], '%Y-%m-%d')
                                except:
                                    pass
                            
                            # Check if post is within last 8 hours
                            if post_date >= cutoff_date:
                                # Determine sentiment based on content
                                sentiment = "info"
                                if any(word in text_lower for word in ["нет бензина", "закончился", "дефицит", "очередь"]):
                                    sentiment = "complaint"
                                elif any(word in text_lower for word in ["нет проблем", "все есть", "в наличии"]):
                                    sentiment = "positive"
                                elif any(word in text_lower for word in ["лимит", "ограничение"]):
                                    sentiment = "neutral"
                                
                                # Determine topic
                                topic = "other"
                                if "очередь" in text_lower:
                                    topic = "queue"
                                elif "лимит" in text_lower or "ограничение" in text_lower:
                                    topic = "limit"
                                elif "нет бензина" in text_lower or "закончился" in text_lower:
                                    topic = "shortage"
                                elif "цена" in text_lower or "подорожал" in text_lower:
                                    topic = "price"
                                elif "в наличии" in text_lower or "нет проблем" in text_lower:
                                    topic = "availability"
                                
                                # Create voice entry
                                voice = {
                                    "date": post_date.strftime('%Y-%m-%d'),
                                    "seen": post_date.strftime('%Y-%m-%d'),
                                    "region": "",  # Will try to extract from text
                                    "city": "",
                                    "lat": 0.0,
                                    "lon": 0.0,
                                    "quote": text[:1000],  # Truncate very long quotes
                                    "sentiment": sentiment,
                                    "topic": topic,
                                    "source": f"Telegram channel @{channel_name}",
                                    "source_url": channel_url,
                                    "author_hint": "Telegram user"
                                }
                                
                                new_voices.append(voice)
                                print(f"Found new voice: {topic} sentiment")
            
            time.sleep(2)  # Rate limiting
            
        except Exception as e:
            print(f"Error processing channel {channel_name}: {e}")
    
    return new_voices

def deduplicate_voices(existing_voices, new_voices):
    """Remove duplicate voices"""
    deduped_new = []
    
    for new_voice in new_voices:
        is_duplicate = False
        
        # Check for duplicates based on quote similarity
        for existing_voice in existing_voices:
            # Simple duplicate check based on first 100 characters of quote
            if len(new_voice['quote']) > 100 and len(existing_voice.get('quote', '')) > 100:
                if new_voice['quote'][:100].lower() == existing_voice['quote'][:100].lower():
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            deduped_new.append(new_voice)
    
    return deduped_new

def main():
    print("Starting OSINT Fuel Voices Update")
    
    # Step 1: Load current data
    print("Loading current data...")
    current_data = load_current_data()
    existing_voices = current_data.get('voices', [])
    
    # Step 2: Extract new voices from Telegram channels
    print("Extracting new voices from Telegram channels...")
    new_voices = extract_new_voices_from_telegram()
    
    # Step 3: Deduplicate new voices
    print(f"Found {len(new_voices)} potential new voices")
    deduped_new_voices = deduplicate_voices(existing_voices, new_voices)
    print(f"After deduplication: {len(deduped_new_voices)} new voices")
    
    # Step 4: Add new voices to data
    if deduped_new_voices:
        current_data['voices'].extend(deduped_new_voices)
        print(f"Added {len(deduped_new_voices)} new voices to data")
    else:
        print("No new voices found, only updating metadata")
    
    # Step 5: Save updated data
    print("Saving updated data...")
    if save_updated_data(current_data):
        # Step 6: Validate JSON
        print("Validating JSON...")
        if validate_json():
            # Step 7: Run git sync
            print("Running git sync...")
            if run_git_sync("data(fuel-voices): update", "fuel-voices"):
                print("OSINT Fuel Voices Update completed successfully!")
                return True
            else:
                print("Git sync failed")
                return False
        else:
            print("JSON validation failed")
            return False
    else:
        print("Failed to save data")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)