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
    """Вес для выбора лида дня. confirmed важнее reported; при равенстве max() берёт первый."""
    conf = 1 if str(s.get("confidence", "")).lower() == "confirmed" else 0
    return (CLS_WEIGHT.get(classify(s), 0), conf)


# Подпись под классом — общая для обоих путей, чтобы Codex и PIL не расходились в словах.
EVENT_LABEL = {
    "sea": "удар по судам теневого флота",
    "refinery": "удар по НПЗ",
    "grid": "удар по энергетике",
    "city": "атака дронов",
}


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
    print("selfcheck OK: sea вперёд refinery, приоритет НПЗ>море>энергетика>город, confirmed весомее")
    return 0


if __name__ == "__main__":
    sys.exit(selfcheck() if "--selfcheck" in sys.argv else 0)
