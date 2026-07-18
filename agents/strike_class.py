#!/usr/bin/env python3
"""strike_class.py — классификация удара для ОБЛОЖКИ. Единственный источник истины.

ЗАЧЕМ ЭТОТ ФАЙЛ. Копий было две — в `hermes/scripts/build-covers.py` (путь Codex) и
в `agents/caption_cover.py` (PIL-фолбэк, штатный бэкстоп по CLAUDE.md, когда Codex
недоступен). В caption_cover висел комментарий «правишь один список — синхронизируй
второй». Не сработало: 15.07 в build-covers добавили класс `sea`, вторую копию не
тронули, и за два дня они разъехались — PIL-фолбэк подписывал удар по танкерам как
«удар по НПЗ» (REF ловит «нефт» в «морская НЕФТетранспортная»). Ручная синхронизация
двух списков — не контракт, а надежда; поэтому список один и импортируется обоими.

НЕ ТРОГАЕТ заголовок сводки: у `agents/gen-news.py` своя классификация с другой
семантикой (бонус за свежесть, infra_label, более широкий REF: «нефтепрод», «нпс»).
Объединять её сюда — менять заголовки 60+ страниц ради красоты. Не в этот раз.

Проверка: python3 agents/strike_class.py --selfcheck
"""
import sys

# Порядок проверки важен: SEA раньше REF, иначе «морская нефтетранспортная
# инфраструктура» ловится на «нефт» и уезжает в refinery.
SEA = ("танкер", "судно", "судов", "теневого флота", "паром", "буксир", "газовоз", "акватори")
REF = ("нпз", "нефт", "терминал", "переработ", "нефтебаз", "нефтехим", "гпз", "перекачк")
GRID = ("тэц", "тэс", "грэс", "подстанц", "энергет", "электро", "водоснаб")

# Обложка дня ведёт самым важным ударом: НПЗ > море > энергетика > прочее.
CLS_WEIGHT = {"refinery": 3, "sea": 2, "grid": 1, "city": 0}


def classify(s):
    """refinery | sea | grid | city — по target+title удара."""
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    if any(k in t for k in SEA):
        return "sea"
    if any(k in t for k in REF):
        return "refinery"
    if any(k in t for k in GRID):
        return "grid"
    return "city"


def lead_score(s):
    """Вес для выбора лида дня. Массовая гибель людей > класс цели > confirmed.

    Удар по гражданскому объекту с погибшими — главная новость дня, а не пожар
    на нефтебазе без жертв (Котовск 18.07: склад Wildberries, 7 погибших, вёл бы
    день, но classify=city проигрывал Ногинской нефтебазе). Порог 5 = «массовые
    жертвы»; ниже — не смещаем редакционный фокус карты с топливной инфраструктуры.
    ponytail: порог 5 — калибровочная ручка, правь если фокус поедет.
    """
    try:
        cas = int(s.get("casualties") or 0)
    except (TypeError, ValueError):
        cas = 0
    mass = 1 if cas >= 5 else 0
    conf = 1 if str(s.get("confidence", "")).lower() == "confirmed" else 0
    return (mass, CLS_WEIGHT.get(classify(s), 0), conf)


# Подпись под классом — общая для обоих путей, чтобы Codex и PIL не расходились в словах.
EVENT_LABEL = {
    "sea": "удар по судам теневого флота",
    "refinery": "удар по НПЗ",
    "grid": "удар по энергетике",
    "city": "атака дронов",
}

# Класс refinery сгребает и заводы, и склады (REF ловит «нефтебаз», «терминал»),
# а плоский EVENT_LABEL подписывал их всех «удар по НПЗ». Это нарушение редполитики
# §3 «нефтебаза ≠ НПЗ» и просто враньё: обложка 17.07 гласила «Керчь — удар по НПЗ»,
# хотя цель — нефтебаза, а НПЗ в Керчи нет (сама сводка при этом писала «удар по
# нефтебазе» — у gen-news.py для заголовков есть infra_label с этим же правилом).
PLANT = ("нпз", "нефтеперераб", "переработ", "нефтехим", "гпз")
DEPOT = ("нефтебаз", "нефтехран", "резервуарн", "терминал", "нпс", "перекачк")


def event_label(s):
    """Подпись под обложку с уточнением: удар по нефтебазе ≠ удар по НПЗ.

    Только для подписи — classify/lead_score не трогаем: для выбора лида и сцены
    склад и завод равнозначны (оба — топливная инфраструктура).
    """
    k = classify(s)
    if k == "refinery":
        t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
        if any(x in t for x in PLANT):       # завод назван явно — он и есть лид
            return "удар по НПЗ"
        if any(x in t for x in DEPOT):
            return "удар по нефтебазе"
        return "удар по топливной инфраструктуре"
    return EVENT_LABEL[k]


def selfcheck():
    sea = {"target": "20 судов «теневого флота» (17 нефтяных танкеров) — морская нефтетранспортная инфраструктура"}
    npz = {"target": "Афипский НПЗ — нефтеперерабатывающий завод", "confidence": "confirmed"}
    grid = {"target": "Балаклавская ТЭС (тепловая электростанция)"}
    city = {"target": "промзона"}

    assert classify(sea) == "sea", classify(sea)          # регресс 15.07: ловилось на «нефт»
    assert classify(npz) == "refinery", classify(npz)
    assert classify(grid) == "grid", classify(grid)
    assert classify(city) == "city", classify(city)
    # приоритет лида: НПЗ > море > энергетика > прочее
    assert lead_score(npz) > lead_score(sea) > lead_score(grid) > lead_score(city)
    # confirmed весомее при том же классе
    assert lead_score({"target": "НПЗ", "confidence": "confirmed"}) > lead_score({"target": "НПЗ"})
    # массовые жертвы (>=5) ведут день поверх класса цели: склад Wildberries с
    # 7 погибшими важнее нефтебазы без жертв (Котовск 18.07)
    assert lead_score({"target": "логистический центр Wildberries", "casualties": 7}) \
        > lead_score({"target": "нефтебаза", "confidence": "confirmed"})
    # единичные жертвы фокус карты не смещают — топл. инфраструктура всё ещё лид
    assert lead_score({"target": "жилой дом", "casualties": 2}) < lead_score({"target": "НПЗ"})

    # подпись: нефтебаза ≠ НПЗ (редполитика §3). Регресс 17.07: обложка подписала
    # удар по нефтебазе в Керчи как «удар по НПЗ», хотя НПЗ в Керчи нет.
    kerch = {"target": "Железнодорожная станция, нефтебаза Керчь, электроподстанция ПС «Керченская»"}
    assert classify(kerch) == "refinery", classify(kerch)          # для лида — та же весовая категория
    assert event_label(kerch) == "удар по нефтебазе", event_label(kerch)
    assert event_label(npz) == "удар по НПЗ", event_label(npz)
    assert event_label(sea) == "удар по судам теневого флота"
    assert event_label(grid) == "удар по энергетике"
    # не завод и не склад (НПС) — обобщаем, а не называем наугад нефтебазой
    assert event_label({"target": "нефтеперекачивающая станция"}) == "удар по топливной инфраструктуре"
    print("selfcheck OK: sea вперёд refinery, приоритет НПЗ>море>энергетика>город, "
          "confirmed весомее, нефтебаза≠НПЗ в подписи")
    return 0


if __name__ == "__main__":
    sys.exit(selfcheck() if "--selfcheck" in sys.argv else 0)
