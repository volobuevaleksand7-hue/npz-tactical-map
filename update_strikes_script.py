import json
from datetime import datetime, timezone

# Читаем файл
with open('data/strikes.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Новые события
new_events = [
    {
        "date": "2026-07-10",
        "time": "утро",
        "city": "Москва",
        "region": "Москва",
        "lat": 55.61,
        "lon": 37.90,
        "type": "drone",
        "count": None,
        "target": "НПЗ 'Капотня' — нефтеперерабатывающий завод",
        "casualties": "Данных нет",
        "title": "Утро 10 июля: атака БПЛА по НПЗ 'Капотня' в Москве",
        "detail": "Утром 10 июля по состоянию на ~8:19 UTC зафиксирован пожар в районе нефтеперерабатывающего завода 'Капотня' в Москве. Детали атаки и масштаб повреждений уточняются.",
        "source_url": "https://t.me/exilenova_plus",
        "confidence": "reported"
    },
    {
        "date": "2026-07-10",
        "time": "утро",
        "city": "Нижнекамск",
        "region": "Республика Татарстан",
        "lat": 55.6369,
        "lon": 51.8253,
        "type": "drone",
        "count": None,
        "target": "Нижнекамскнефтехим — нефтехимический комплекс (НПЗ ТАНЕКО и производства СИБУРа)",
        "casualties": "Данных нет",
        "title": "Утро 10 июля: повторная атака БПЛА по Нижнекамскнефтехиму",
        "detail": "Утром 10 июля по состоянию на ~8:23 UTC зафиксирован пожар на нефтехимическом комплексе 'Нижнекамскнефтехим'. Это повторная атака на объект (предыдущая массированная атака была 8 июля).",
        "source_url": "https://t.me/exilenova_plus",
        "confidence": "reported"
    }
]

# Проверка дедуп (совпадают ли дата и город с существующими?)
existing_keys = set()
for event in data['strikes']:
    key = (event.get('date'), event.get('city'))
    existing_keys.add(key)

added = 0
for new_event in new_events:
    key = (new_event['date'], new_event['city'])
    if key not in existing_keys:
        data['strikes'].append(new_event)
        existing_keys.add(key)
        added += 1
        print(f"✓ Добавлено: {new_event['city']} ({new_event['date']})")
    else:
        print(f"✗ Дедуп: {new_event['city']} ({new_event['date']}) уже есть")

# Обновляем generated_at
data['updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

# Сохраняем
with open('data/strikes.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=1)

print(f"\nОбновлено: {added} новых событий добавлено")
print(f"Новое время: {data['updated']}")
print(f"Всего событий: {len(data['strikes'])}")
