import json
from datetime import datetime

# Read current file
with open('/root/npz-tactical-map/data/fuel-availability.json') as f:
    data = json.load(f)

# Current time
now = "2026-09-06T16:23:58Z"

# Prepare updates based on WebSearch results
updates = {
    "Воронежская область": {
        "level": "strained",
        "networks": [{"name": "Газпром нефть / Лукойл / Роснефть", "status": "open", "level": "strained",
                     "limit_l": 35, "note": "06.09 ротация: На 83 АЗС топливо, на 20 - лимиты, на 37 - нет. Лимит 30-40л. Ограничения сохраняются."}],
        "queues_hours": 0.5,
        "ai95_price_rub": 84.75,
        "source_urls": ["https://gdezapravka.ru/zapravki/voronezh", "https://voronezhnews.ru/"]
    },
    "Вологодская область": {
        "level": "strained",
        "networks": [{"name": "Газпромнефть/Лукойл/Роснефть", "status": "limited", "level": "strained",
                     "limit_l": 30, "note": "06.09 ротация: На 12 АЗС топливо, на 11 - лимиты, на 21 - нет. Дефицит пообещали ликвидировать к 10.09. Губернатор под контролем."}],
        "queues_hours": 0.5,
        "ai95_price_rub": 91.31,
        "source_urls": ["https://vologda-poisk.ru/news/na-zlobu-dnya/defitsit-benzina-v-vologodskoj-oblasti-poobeschali-likvidirovat-k-10-sentyabrya"]
    },
    "Луганская обл.": {
        "level": "critical",
        "networks": [{"name": "ЛНР", "status": "limited", "level": "critical",
                     "limit_l": 20, "note": "06.09 ротация: Талонная система. Критический дефицит. Цены >200₽. Талоны на чёрном рынке."}],
        "queues_hours": 2.0,
        "ai95_price_rub": 210.0,
        "source_urls": ["https://www.ostro.org/ru/news/"]
    },
    "Ставропольский край": {
        "level": "limited",
        "networks": [{"name": "Крупные сети", "status": "limited", "level": "limited",
                     "limit_l": 20, "note": "06.09 ротация: Лимит 20л. Туристический сезон обостряет. На курортах дефицит."}],
        "queues_hours": 1.5,
        "ai95_price_rub": 75.0,
        "source_urls": ["https://ircity.ru/text/transport/2026/09/02/76619405/"]
    },
    "Рязанская область": {
        "level": "critical",
        "networks": [{"name": "Роснефть/Лукойл/Газпром нефть", "status": "limited", "level": "critical",
                     "limit_l": 40, "note": "06.09 ротация: Вторая волна дефицита подтверждена. АИ-95 >100₽/л. Лимит 40л. Очереди."}],
        "queues_hours": 1.5,
        "ai95_price_rub": 100.0,
        "source_urls": ["https://ya62.ru/text/economics/2026/06/19/76487429/"]
    },
    "Липецкая область": {
        "level": "limited",
        "networks": [{"name": "Газпромнефть / Лукойл / Роснефть", "status": "limited", "level": "limited",
                     "limit_l": 30, "note": "06.09 ротация: Чет-нечет (с 13.08). Дефицит ~500т/день. Лимит 30л бензина, 60л дизель."}],
        "queues_hours": 0.5,
        "ai95_price_rub": 69.0,
        "source_urls": ["https://finance.mail.ru/article/v-lipeckoj-oblasti-vozvrashayut-prodazhu-benzina-po-nomeram-avto-69222367/"]
    },
    "Челябинская область": {
        "level": "critical",
        "networks": [{"name": "Лукойл/Газпромнефть", "status": "limited", "level": "critical",
                     "limit_l": 30, "note": "06.09 ротация: Вторая волна интенсивна. Множество АЗС пустые. Очереди 1-2 часа. Цены до 200₽ у частников."}],
        "queues_hours": 2.0,
        "ai95_price_rub": 75.0,
        "source_urls": ["https://chel.aif.ru/society/chelyabincy-zhaluyutsya-na-pereboi-s-toplivom-na-azs"]
    },
    "Свердловская область": {
        "level": "strained",
        "networks": [{"name": "Газпром нефть/Лукойл", "status": "limited", "level": "strained",
                     "limit_l": 40, "note": "06.09 ротация: Спекуляция топливом сторонних лиц. Очереди, люди ждут часами. На 285 АЗС отслеживается статус."}],
        "queues_hours": 1.5,
        "ai95_price_rub": 72.35,
        "source_urls": ["https://www.e1.ru/text/gorod/2026/09/06/76627385/"]
    },
    "Хабаровский край": {
        "level": "limited",
        "networks": [{"name": "ДВК / НПЗ-Хабаровск", "status": "limited", "level": "limited",
                     "limit_l": 30, "note": "06.09 ротация: Договорённости с производителями о поставках. 600 тонн топлива направляют. НПЗ на полную мощность."}],
        "queues_hours": 0.3,
        "ai95_price_rub": 75.69,
        "source_urls": ["https://hab.aif.ru/society/habarovskie-postavshchiki-topliva-dogovorilis-zakryvat-pereboi-na-mestah"]
    },
    "Ингушетия": {
        "level": "critical",
        "networks": [{"name": "Назрань (исключение)", "status": "limited", "level": "limited",
                     "limit_l": 20, "note": "06.09 ротация: Назрань дешево (~68₽ АИ-95). Остальное критично (140-200₽). Талонная система на части сетей."}],
        "queues_hours": 2.0,
        "ai95_price_rub": 150.0,
        "source_urls": ["https://ru.themoscowtimes.com/2026/06/27/azs-vingushetii-nachali-ostanavlivat-rabotu-ivvodit-taloni-natoplivo-a199351"]
    },
    "Новгородская область": {
        "level": "calm",
        "networks": [{"name": "Крупные сети", "status": "open", "level": "calm",
                     "limit_l": None, "note": "06.09 ротация: Цены 63-79₽. Без острого дефицита. Поставки достаточны."}],
        "queues_hours": 0.0,
        "ai95_price_rub": 70.0,
        "source_urls": ["https://tarif.novreg.ru/"]
    },
    "Донецкая область": {
        "level": "limited",
        "networks": [{"name": "ДНР", "status": "limited", "level": "limited",
                     "limit_l": 30, "note": "06.09 ротация: Лимит 20-30л. Топливо доступно с ограничениями. Цены высокие (~130₽). Дефицит из-за ударов."}],
        "queues_hours": 0.5,
        "ai95_price_rub": 130,
        "source_urls": ["https://www.ostro.org/ru/news/"]
    }
}

# Update regions with new data
for region_name, update_data in updates.items():
    for region in data['regions']:
        if region['region'] == region_name:
            region['updated'] = now
            region['level'] = update_data['level']
            region['networks'] = update_data['networks']
            region['queues_hours'] = update_data['queues_hours']
            region['ai95_price_rub'] = update_data['ai95_price_rub']
            region['source_urls'] = update_data['source_urls']
            break

# Add new policy events at the top
new_events = [
    {
        "date": "2026-09-06T16:23:58Z",
        "region": "Россия (федеральный мониторинг)",
        "type": "analysis",
        "description": "Тридцатая волна ротационного прохода: 12 самых старых регионов обновлены (Воронеж, Вологда, Луганская, Ставрополь, Рязань, Липецк, Челябинск, Свердловская, Хабаровск, Ингушетия, Новгородская, Донецкая). Волгоград: рекордные очереди 37 часов, места продают за 1500₽. Оренбург: чет-нечет 06.09 - чётные номера. Спекуляция топливом обостряет ситуацию в Екатеринбурге и других регионах."
    },
    {
        "date": "2026-09-06T16:23:58Z",
        "region": "Оренбургская область",
        "type": "market",
        "description": "На 06.09 на оренбургских АЗС чётные номера (последняя цифра 0,2,4,6,8). Лимит 15-30л АИ. На трассах до 200л ДТ. Система действует с конца августа."
    }
]

# Prepend new events
data['meta']['policy_events'] = new_events + data['meta']['policy_events'][:6]  # Keep top 8

# Update meta
data['meta']['generated_at'] = now
data['meta']['updated_by'] = "agent:fuel-availability"
data['meta']['last_rotation_pass'] = now

# Update rotation_pass note
data['meta']['rotation_pass'] = f"{now}: Тридцатая волна ротационного прохода. WebSearch (5 горячих тем) + 12 ротационных из самых старых регионов (updated ≤05.09 04:00). Основной результат: спекуляция усугубляет кризис, биржа стабилизируется."

print("JSON обновлен успешно!")
print(f"Обновлено регионов: {len(updates)}")
print(f"Новых событий: {len(new_events)}")

# Write back
with open('/root/npz-tactical-map/data/fuel-availability.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Файл записан!")
