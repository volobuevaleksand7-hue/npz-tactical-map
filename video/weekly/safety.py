"""Правила формулировок недельного обзора (10.10.2026, решение владельца).

1) Никаких упоминаний погибших/раненых/пострадавших людей — ни в озвучке, ни на экране, ни в описании.
   Остаётся факт удара, объект и ущерб инфраструктуре. Фильтр scrub() режет такие обороты из ЛЮБОГО текста
   (Haiku, шаблон, поле detail), а audit_weekly.py роняет выпуск, если стоп-слова всё же прошли.
2) Удары и остановки в Крыму остаются в обзоре, нейтрально: «Крым (по данным открытых источников)».
"""
import re

# русские основы; короткие — с границей слева, чтобы не цеплять середину слов
CASUALTY_RU = re.compile(
    r"погиб|погибш|смерт|гибел|скончал|жертв|пострада|травм|ожог|реанимац|госпитал|"
    r"(?<![а-яё])(?:ранен|ранил|ранен\w*|убит|убийств|труп)", re.I)
CASUALTY_EN = re.compile(
    r"\b(?:killed|kills?|dead|deaths?|died|dies|dying|fatalit\w*|wounded|injur\w*|casualt\w*|victims?|"
    r"hospitali[sz]\w*|corpses?|bodies|lives lost|fatally)\b", re.I)
CASUALTY_ANY = re.compile(CASUALTY_RU.pattern + "|" + CASUALTY_EN.pattern, re.I)

CRIMEA_RX = re.compile(r"Крым|Севастопол|Феодоси|Керч|Симферопол|Ялт|Евпатори|Балаклав", re.I)
CRIMEA_NOTE = "по данным открытых источников"


def has_casualty(text):
    return bool(CASUALTY_ANY.search(text or ""))


def is_crimea(s):
    return bool(CRIMEA_RX.search(str(s.get("region") or "") + " " + str(s.get("city") or "")))


def scrub(text, head=False):
    """Вырезает из текста обороты про людей. head=True — формат «Город: …» (город сохраняется).
    Возвращает очищенный текст либо None, если осмысленного остатка нет (вызывающий берёт нейтральный запасной)."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return None
    prefix = ""
    if head:
        m = re.match(r"^([^:]{1,60}):\s*(.*)$", t)
        if m:
            prefix, t = m.group(1), m.group(2)
    sents = []
    for sent in re.split(r"(?<=[.!?])\s+", t):
        sent = sent.strip().rstrip(".!? ")
        if not sent:
            continue
        keep = []
        for c in re.split(r",\s*|;\s*", sent):
            c = c.strip()
            if not c:
                continue
            if CASUALTY_RU.search(c):
                parts = re.split(r"\s+и\s+", c)
                good = [p for p in parts if not CASUALTY_RU.search(p)]
                if len(parts) > 1 and good and len(good[0]) >= 20 and not CASUALTY_RU.search(parts[0]):
                    c = " и ".join(good)
                else:
                    continue
            keep.append(c)
        if keep:
            sents.append(", ".join(keep))
    body = ". ".join(sents)
    if len(body.split()) < 3:
        return None
    body = body[:1].upper() + body[1:] if not prefix else body
    return (f"{prefix}: {body}." if prefix else body + ".")
