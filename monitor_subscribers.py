#!/usr/bin/env python3
"""Мониторинг новых подписчиков на бота @NpzFuel_Bot и канал @NPZmap"""
import json
import os
import sys
import urllib.request
from datetime import datetime

BOT_DIR = os.path.expanduser("~/.npz-bot")
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "subscribers_state.json")

def load_token():
    return open(os.path.join(BOT_DIR, "token")).read().strip()

def api_url(token, method):
    return f"https://api.telegram.org/bot{token}/{method}"

def get_chat_members(token, chat_id):
    """Получить количество участников чата/канала"""
    try:
        url = api_url(token, f"getChatMemberCount?chat_id={chat_id}")
        r = urllib.request.urlopen(url, timeout=10)
        data = json.loads(r.read().decode())
        if data.get("ok"):
            return data["result"]
    except Exception as e:
        print(f"Ошибка getChatMemberCount для {chat_id}: {e}")
    return None

def get_bot_subscribers():
    """Получить список подписчиков бота из файла"""
    try:
        with open(SUBS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("subscribers", {})
    except Exception:
        return {}

def load_previous_state():
    """Загрузить предыдущее состояние"""
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"bot_subscribers": {}, "channel_members": {}}

def save_current_state(state):
    """Сохранить текущее состояние"""
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def main():
    token = load_token()
    state = load_previous_state()
    
    # 1. Проверяем подписчиков бота
    current_subs = get_bot_subscribers()
    previous_subs = state.get("bot_subscribers", {})
    
    new_bot_subs = []
    for chat_id, info in current_subs.items():
        if chat_id not in previous_subs and info.get("status") == "active":
            new_bot_subs.append({
                "id": chat_id,
                "name": info.get("name", "Unknown"),
                "since": info.get("since", ""),
                "src": info.get("src", "")
            })
    
    # 2. Проверяем участников канала
    channel_id = "-1004491068477"  # @NPZmap
    current_channel_members = get_chat_members(token, channel_id)
    previous_channel_members = state.get("channel_members", {}).get("count", 0)
    
    new_channel_members = None
    if current_channel_members and current_channel_members > previous_channel_members:
        new_channel_members = {
            "previous": previous_channel_members,
            "current": current_channel_members,
            "delta": current_channel_members - previous_channel_members
        }
    
    # 3. Формируем отчет
    report = []
    
    if new_bot_subs:
        report.append("🆕 **Новые подписчики бота @NpzFuel_Bot:**")
        for sub in new_bot_subs:
            report.append(f"• {sub['name']} (ID: {sub['id']})")
            report.append(f"  Источник: {sub['src']}, Дата: {sub['since'][:10]}")
        report.append("")
    
    if new_channel_members:
        report.append("📈 **Новые подписчики канала @NPZmap:**")
        report.append(f"• Было: {new_channel_members['previous']} → Стало: {new_channel_members['current']}")
        report.append(f"• Прирост: +{new_channel_members['delta']}")
        report.append("")
    
    if report:
        print("\n".join(report))
    else:
        # Тихий выход - ничего не отправляем
        pass
    
    # 4. Сохраняем текущее состояние
    new_state = {
        "bot_subscribers": current_subs,
        "channel_members": {
            "count": current_channel_members or previous_channel_members,
            "last_check": datetime.now().isoformat()
        },
        "last_check": datetime.now().isoformat()
    }
    save_current_state(new_state)

if __name__ == "__main__":
    main()
