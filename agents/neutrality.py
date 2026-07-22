#!/usr/bin/env python3
"""
neutrality.py — ЕДИНЫЙ словарь нейтральности карты. Один источник правды.

До 22.07 одни и те же списки жили в двух копиях: agents/sanitize-strikes.py и
hermes/bot/content_guard.py — причём в шапке второго прямо написано «логика
должна совпадать... или вынеси в общий модуль». Они уже разъехались: одна копия
знала «русня», другая «русн». Здесь копия одна, оба модуля импортируют её.

Две операции, РАЗНЫЕ по жёсткости — не путать:

  scrub_text(s)   ЧИНИТ текст. Вырезает оценочный эпитет, факт оставляет.
                  Применяется всегда и молча: «удар по оккупированному
                  Севастополю» -> «удар по Севастополю». Событие реальное и по
                  теме, выбрасывать его нельзя (так архив и усыхал).

  text_reasons(s) ДИАГНОЗ. Что осталось непочиняемым: украинский язык, лозунг,
                  призыв. Это не эпитет вокруг факта, это сам текст — такое
                  не правится автоматом и не публикуется.

Запуск: python3 agents/neutrality.py   — assert-самопроверка.
"""
import re

# --- украинский язык -------------------------------------------------------
UA_CHARS = set("іїєґ")

# --- лозунги и партийная лексика ОБЕИХ сторон ------------------------------
# Объединение двух разъехавшихся копий + русскоязычные ярлыки, которых не знала
# ни одна из них (карта нейтральна к обеим сторонам, не только к одной).
#
# ДВА списка, и это не эстетика. Фразы ищутся подстрокой — они длинные и
# однозначные. Ярлыки-корни подстрокой искать НЕЛЬЗЯ: «русн» сидит внутри
# «ви-русн-ый», «орки» — внутри «под-борки», «сб-орки», «уб-орки». На первом же
# прогоне по репозиторию это дало 7 ложных срабатываний на живых страницах.
# Поэтому ярлык обязан начинать слово (lookbehind) и иметь явные окончания:
# «орки/орков» — да, «оркестр» — нет.
SLOGAN_PHRASES = [
    "Повітр", "Слава Україн", "Гарні новини", "терориста", "Далі буде",
    "відмінусували", "Дякуємо", "ворожий", "збитий в бою", "Твір на тему",
    "ЗСУ переможе", "доблестная ПВО", "наши доблестные", "возмездие настиг",
]
SLUR_RE = re.compile(
    r"(?i)(?<![а-яёa-z])(русн[яиюей]|орк[иаовм]\b|орками|кацап|москал|хохл|"
    r"укроп[ыа]?\b|бандеровц|нацик|хунт)")
SLOGANS = SLOGAN_PHRASES  # back-compat: старое имя, на него ссылались оба модуля
UA_MARK = SLOGAN_PHRASES


def slogan_hit(t):
    """Первый найденный лозунг/ярлык или None. Единая логика для текста и записи."""
    low = t.lower()
    for m in SLOGAN_PHRASES:
        if m.lower() in low:
            return m
    m = SLUR_RE.search(t)
    return m.group(0) if m else None

# --- призывы (к насилию, вступлению, сбору средств, выходу на улицы) -------
# Это не эпитет вокруг факта — это обращение к читателю. Нейтральный OSINT его
# не содержит вообще, поэтому чиним НЕ вырезанием, а отказом публиковать.
CALLS = [
    r"(?i)\b(бей|убива|жги|сожги|уничтожа|взрывай|режь)\w*\s+(их\b|русск|русн|росси|укра|кацап|москал|хохл|оккупант|окупант)",
    r"(?i)\b(смерть|смерті)\s+(врагам|ворог|оккупант|окупант|москал|кацап)",
    r"(?i)\bвступа[йи]\w*\s+(в\s+)?(ряды|всу|зсу|армию|легион)",
    r"(?i)\b(задонать|донать|донат[ья])\w*\s+(на\s+)?(дрон|fpv|фпв|зсу|всу)",
    r"(?i)\bпідтрима[йєи]\w*",
    r"(?i)\b(выходи|выходите|виходь)\w*\s+на\s+(улиц|протест|майдан)",
    r"(?i)\bбер[ии]\w*\s+в\s+руки\s+оруж",
    r"(?i)\bмсти(те)?\s+(за|им)\b",
]

# --- оценочные эпитеты: ЧИНИМ, а не выбрасываем ----------------------------
# Режем ЭПИТЕТ, а не запись: событие реальное и по теме. Через отказ публиковать
# такая запись удалилась бы целиком — это ровно тот усыхающий архив (11.07: 172→67).
SCRUB = [
    (r"(?i)\bвременно\s+оккупированн\w*\s+", ""),
    (r"(?i)\bв\s+оккупированном\s+", "в "),
    (r"(?i)\bв\s+аннексированном\s+", "в "),
    (r"(?i)\bоккупированн\w*\s+", ""),
    (r"(?i)\bаннексированн\w*\s+", ""),
    (r"(?i)\bоккупант\w*\s+", ""),
    (r"(?i)\bгероическ\w*\s+", ""),
    (r"(?i)\bварварск\w*\s+", ""),
    (r"(?i)\bтеррористическ\w*\s+(атак|удар|обстрел)", r"\1"),
    (r"(?i)\bбесчеловечн\w*\s+", ""),
    (r"(?i)\bкровав\w*\s+режим\w*\s*", ""),
]

VALID_CONF = {"confirmed", "reported", "rumored"}

JET_WORDS = ["су-3", "су-5", "миг-", "истребител", "льотчик", "лётчик", "самолёт", "самолет"]
FUEL_WORDS = ["нпз", "нефт", "топлив", "нефтебаз", "терминал", "азс", "гпз", "энергет",
              "подстанц", "тэц", "тэс", "грэс", "нпс", "нефтехим"]

# Служебные секции HTML, где совпадение — не текст статьи, а разметка/данные.
_HTML_DROP = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_HTML_TAG = re.compile(r"(?s)<[^>]+>")


def strip_markup(s):
    """HTML -> видимый текст. Диагноз ставим по тексту, а не по атрибутам тегов."""
    s = _HTML_DROP.sub(" ", s)
    s = _HTML_TAG.sub(" ", s)
    return re.sub(r"\s+", " ", s)


def scrub_text(s):
    """Вырезает оценочные эпитеты. Возвращает (текст, сколько правок)."""
    if not isinstance(s, str) or not s:
        return s, 0
    n = 0
    for pat, rep in SCRUB:
        s, k = re.subn(pat, rep, s)
        n += k
    if n:
        # схлопываем пробелы, появившиеся на месте вырезанного слова, но НЕ трогаем
        # переводы строк — в HTML и постах они значимы
        s = re.sub(r"[ \t]{2,}", " ", s)
        s = re.sub(r"[ \t]+([,.;:!?»)])", r"\1", s)
    return s, n


def text_reasons(s, markup=False):
    """Непочиняемые нарушения в свободном тексте. [] — текст публикуемый.

    markup=True — на входе HTML: диагноз ставим по видимому тексту.
    Возвращает список (причина, фрагмент) — фрагмент нужен, чтобы человек нашёл
    место, а не искал «где-то в файле на 300 строк».
    """
    if not isinstance(s, str) or not s:
        return []
    t = strip_markup(s) if markup else s
    out = []
    bad_chars = sorted(set(t) & UA_CHARS)
    if bad_chars:
        out.append(("UA-lang", "буквы " + "".join(bad_chars) + " | " + _around(t, bad_chars[0])))
    hit = slogan_hit(t)
    if hit:
        out.append(("slogan", _around(t, hit)))
    for pat in CALLS:
        hit = re.search(pat, t)
        if hit:
            out.append(("call-to-action", _around(t, hit.group(0))))
    return out


def _around(text, needle, width=60):
    i = text.lower().find(needle.lower())
    if i < 0:
        return needle
    a = max(0, i - width // 2)
    return ("…" if a else "") + text[a:i + len(needle) + width // 2].strip() + "…"


# --- уровень ЗАПИСИ (strikes.json и подобные) ------------------------------
SCRUB_FIELDS = ("detail", "target", "title", "city", "region")


def scrub_record(x):
    """Чистит текстовые поля записи на месте. True, если что-то изменилось."""
    changed = False
    for f in SCRUB_FIELDS:
        v = x.get(f)
        if not isinstance(v, str):
            continue
        new, n = scrub_text(v)
        new = new.strip()
        if n and new != v:
            x[f] = new
            changed = True
    return changed


def reason_bad(x):
    """Причина, по которой запись НЕ должна попасть на карту/в канал, иначе None."""
    import json
    blob = json.dumps(x, ensure_ascii=False)
    if any(c in blob for c in UA_CHARS):
        return "UA-lang"
    if slogan_hit(blob):
        return "propaganda"
    if any(re.search(p, blob) for p in CALLS):
        return "call-to-action"
    if x.get("confidence") not in VALID_CONF:
        return "bad-confidence:%s" % x.get("confidence")
    tgt = (str(x.get("target", "")) + " " + str(x.get("title", ""))).lower()
    if any(k in tgt for k in JET_WORDS) and not any(k in tgt for k in FUEL_WORDS):
        return "offtopic-aircraft"
    city = str(x.get("city", "")).strip().lower()
    if city in ("", "неизвестно") and "неуточ" in tgt:
        return "empty-alert"
    return None


def is_clean(x):
    return reason_bad(x) is None


def demo():
    """assert-самопроверка: эпитет чинится, лозунг/призыв/укр-язык — нет."""
    s, n = scrub_text("Удар по оккупированному Севастополю")
    assert s == "Удар по Севастополю" and n == 1, s
    s, n = scrub_text("варварский удар по НПЗ")
    assert s == "удар по НПЗ", s
    assert scrub_text("Удар по НПЗ в Рязани")[1] == 0

    assert text_reasons("Поражён Рязанский НПЗ") == []
    assert text_reasons("Слава Україні")            # лозунг + укр-язык
    assert "call-to-action" in {r for r, _ in text_reasons("бей их, пока не поздно")}
    # слур и призыв в одной фразе -> обе причины, порядок не важен
    assert {"slogan", "call-to-action"} <= {r for r, _ in text_reasons("бей русню")}
    assert text_reasons("Повітряні Сили відмінусували")
    # ярлык внутри обычного слова — НЕ нарушение (7 ложняков на первом прогоне)
    for w in ("подборки материалов", "вирусный контент", "уборки урожая",
              "сборки без бандлера", "симфонический оркестр"):
        assert text_reasons(w) == [], w
    assert slogan_hit("прилёт по кацапам") == "кацап"
    # разметка не должна давать ложных срабатываний
    assert text_reasons('<a href="https://pravda.com.ua/x">источник</a>', markup=True) == []
    assert text_reasons('<script>var s="орки";</script><p>Удар по НПЗ</p>', markup=True) == []

    good = {"date": "2026-07-08", "city": "Рязань", "target": "Рязанский НПЗ",
            "confidence": "reported", "title": "Удар по НПЗ"}
    cases = [
        ({"city": "X", "target": "Слава Україні", "confidence": "reported"}, "UA-lang"),
        ({"city": "X", "target": "прилёт по кацапам", "confidence": "reported"}, "propaganda"),
        ({"city": "X", "target": "НПЗ", "confidence": "reported", "detail": "бей русских"}, "call-to-action"),
        ({"city": "X", "target": "сбит Су-35", "confidence": "reported"}, "offtopic-aircraft"),
        ({"city": "X", "target": "сбит Су-35 у НПЗ", "confidence": "reported"}, None),
        ({"city": "X", "target": "склад Wildberries", "confidence": "reported"}, None),
        ({"city": "X", "target": "НПЗ горит", "confidence": "сообщено"}, "bad-confidence:сообщено"),
        ({"city": "Неизвестно", "target": "неуточнённый объект", "confidence": "reported"}, "empty-alert"),
        (good, None),
    ]
    for x, exp in cases:
        got = reason_bad(x)
        assert got == exp, "reason_bad(%s) = %r, ожидалось %r" % (x, got, exp)

    r = {"city": "Севастополь", "detail": "Удар по оккупированному порту", "confidence": "reported"}
    assert scrub_record(r) and r["detail"] == "Удар по порту"
    print("neutrality demo OK")


if __name__ == "__main__":
    demo()
