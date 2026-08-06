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
    # Оценка воюющей стороны, выданная за установленный факт. Правим ТОЧНЫЕ обороты,
    # а не глагол вообще: замена «подтвердил» -> «сообщил» в общем виде даёт «сообщил
    # удар» — русский ломается, а мы получаем нечитаемый пост вместо ненейтрального.
    (r"(?i)подтвердил(о|а|и)?\s+успешн\w*\s+удар\w*", r"заявил\1 об ударе"),
    (r"(?i)подтвердил(о|а|и)?\s+успешн\w*\s+поражени\w*", r"заявил\1 о поражении"),
    (r"(?i)подтвердил(о|а|и)?\s+поражени\w*", r"заявил\1 о поражении"),
    (r"(?i)\bуспешн\w*\s+(удар|поражени|атак|операци)", r"\1"),
]

# --- латиница в русской ленте: ЧИНИМ переводом, а не выбрасыванием -----------
# 01.08 в канал ушло «нефтеперерабатывающий завод Bashneft-UNPZ» и «по информации
# SBU» — это транслит из англоязычного источника, в русской ленте читается как
# чужой текст. Правим ТОЧЕЧНЫМ словарём, а не общим транслитератором:
# 🔴 названия судов (Nordic Zenith, NELSA, Banda) и бренды (Wildberries, Ozon, DNS)
# латиницей пишут и в русской прессе — их трогать нельзя, транслит их изуродует.
LATIN_FIX = [
    # У «Башнефти» ровно три уфимских завода — список полный, гадать не нужно.
    (r"(?i)\bBashneft[- ]?Ufaneftekhim\b", "Башнефть-Уфанефтехим"),
    (r"(?i)\bBashneft[- ]?Ufaneftehim\b", "Башнефть-Уфанефтехим"),
    (r"(?i)\bUfaneftekhim\b", "Уфанефтехим"),
    (r"(?i)\bBashneft-UNPZ\b", "Башнефть-УНПЗ"),
    (r"(?i)\bBashneft-Novoil\b", "Башнефть-Новойл"),
    # (?<!/) — не трогать URL-слаг /npz/taif-nk (censor работает на сыром HTML,
    # без strip_markup; без лукбихайнда правило калечило href в ссылку 404).
    (r"(?i)(?<!/)\bTAIF-NK\b", "ТАИФ-НК"),
    (r"(?i)\bELOU-AVT\b", "ЭЛОУ-АВТ"),
    (r"(?i)\bAzovnefteprodukt\b", "Азовнефтепродукт"),
    (r"(?i)\bForte\s+Invest\b", "Форте Инвест"),
    (r"(?i)\bYug\s+Rusi\s+oil\s+terminal\b", "нефтяной терминал «Юг Руси»"),
    (r"(?i)\bGidrostal\w*konstruktsiya\b", "Гидростальконструкция"),
    (r"(?i)\bShahed\b", "Шахед"),
    (r"\bSBU\b", "СБУ"),
    (r"\bHUR\b", "ГУР"),
    (r"\bFSB\b", "ФСБ"),
]

# --- «событие» о том, что события не было --------------------------------------
# 04.08 в канал ушли молнии «Новых ударов по нефтегазовой инфраструктуре не
# зафиксировано за последний час» с пустыми полями: «📍 — , — 🎯 — ~ —». Сборщик
# оформил отчёт «за час ничего» как удар, классификатор увидел слово «нефтегазовой»
# и выдал TIER-1. Молния — это событие; отсутствие события молнией быть не может.
NO_EVENT = re.compile(
    r"(?i)(не\s+зафиксирован|не\s+отмечен|не\s+зарегистрирован|ударов\s+нет|"
    r"новых\s+ударов\s+не|отч[её]т\s+за\s+последний\s+час|без\s+изменений|"
    r"ничего\s+не\s+произошло|обстановка\s+спокойн)")

_EMPTY = {"", "-", "—", "–", "none", "null", "n/a", "нет данных", "неизвестно"}


def _blank(v):
    return str(v or "").strip().lower() in _EMPTY


VALID_CONF = {"confirmed", "reported", "rumored"}

JET_WORDS = ["су-3", "су-5", "миг-", "истребител", "льотчик", "лётчик", "самолёт", "самолет"]
FUEL_WORDS = ["нпз", "нефт", "топлив", "нефтебаз", "терминал", "азс", "гпз", "энергет",
              "подстанц", "тэц", "тэс", "грэс", "нпс", "нефтехим"]

# Служебные секции HTML, где совпадение — не текст статьи, а разметка/данные.
_HTML_DROP = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_HTML_TAG = re.compile(r"(?s)<[^>]+>")

# 🔴 05.08: scrub_text() чинил "TAIF-NK" внутри href="/npz/taif-nk" (URL, не проза) —
# ссылка сломалась (кириллица в слаге), а последующий пробельный клинап той же функции
# (\s+ перед пунктуацией, включая ".") прошёлся по <style> и съел пробел в CSS-селекторах
# вида ".status-card .val" -> ".status-card.val" (другой селектор, вёрстка отваливается).
# И то и другое — не текст статьи: <style>/<script> и href/src защищаем от всего пайплайна
# (SCRUB/LATIN_FIX и клинап), как text_reasons уже защищает их через strip_markup.
_PROTECT = re.compile(r'(?is)<(script|style)\b.*?</\1>|\bhref="[^"]*"|\bsrc="[^"]*"')


def strip_markup(s):
    """HTML -> видимый текст. Диагноз ставим по тексту, а не по атрибутам тегов."""
    s = _HTML_DROP.sub(" ", s)
    s = _HTML_TAG.sub(" ", s)
    return re.sub(r"\s+", " ", s)


def _scrub_plain(s):
    """SCRUB+LATIN_FIX и пробельный клинап, БЕЗ учёта защищённых секций."""
    n = 0
    for pat, rep in SCRUB + LATIN_FIX:
        s, k = re.subn(pat, rep, s)
        n += k
    if n:
        # схлопываем пробелы, появившиеся на месте вырезанного слова, но НЕ трогаем
        # переводы строк — в HTML и постах они значимы
        s = re.sub(r"[ \t]{2,}", " ", s)
        s = re.sub(r"[ \t]+([,.;:!?»)])", r"\1", s)
    return s, n


def scrub_text(s):
    """Вырезает оценочные эпитеты и чинит латиницу. Возвращает (текст, сколько правок).

    <style>/<script>-содержимое и значения href=/src= пропускаются без изменений —
    это разметка/URL, а не текст статьи (см. _PROTECT)."""
    if not isinstance(s, str) or not s:
        return s, 0
    out = []
    total = 0
    pos = 0
    for m in _PROTECT.finditer(s):
        fixed, k = _scrub_plain(s[pos:m.start()])
        out.append(fixed)
        total += k
        out.append(m.group(0))  # <style>/<script>/href=".."/src=".." — без изменений
        pos = m.end()
    fixed, k = _scrub_plain(s[pos:])
    out.append(fixed)
    total += k
    return "".join(out), total


# Латиница, которую МОЖНО оставлять: бренды и суда так пишет и русская пресса,
# служебные аббревиатуры — тоже. Всё остальное латиницей в русской ленте — сигнал,
# что словарь LATIN_FIX отстал от данных.
LATIN_OK = re.compile(
    r"(?i)^(wildberries|ozon|dns|nasa|firms|utc|osint|isw|reuters|bbc|the|moscow|times|"
    r"exilenova|plus|noelreports|noel|reports|radarrussiia|media|fpv|fp|cdu|avt|elou|"
    r"nordic|zenith|nelsa|banda|louise|asia|nissos|ios|blue|matilda|suezmax|zao)$")


def latin_leftovers(s):
    """Латинские слова, которых нет ни в словаре перевода, ни в списке допустимых.

    Словарь всегда отстаёт от данных: 05.08 в канал ушло «Bashneft-Ufaneftekhim» —
    вариант, которого в LATIN_FIX не было. Пусть следующий такой случай виден в
    логе публикации, а не только глазами в ленте.
    """
    fixed, _ = scrub_text(str(s or ""))
    return sorted({w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", fixed)
                   if not LATIN_OK.match(w)})


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
    # Отчёт «за час ничего не произошло» — не событие и молнией быть не может.
    if NO_EVENT.search(str(x.get("title", "")) + " " + str(x.get("target", ""))):
        return "no-event"
    # Пустая карточка: рендер даёт «📍 — , — 🎯 —» и заглушку описания.
    if _blank(x.get("city")) and _blank(x.get("target")) and _blank(x.get("title")):
        return "empty-alert"
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

    # 🔴 05.08 регресс: правка эпитета В ОДНОМ месте файла не должна портить <style>/
    # href в ДРУГИХ местах — раньше пробельный клинап съедал пробел в CSS-селекторах
    # (".a .b" -> ".a.b") и LATIN_FIX переписывал URL-слаг на кириллицу, ломая ссылку.
    html = ('<a href="/npz/taif-nk">ТАИФ-НК</a>'
            '<style>.status-card .val{color:red}</style>'
            '<p>варварский удар по НПЗ</p>')
    fixed, n = scrub_text(html)
    assert n == 1, (fixed, n)
    assert 'href="/npz/taif-nk"' in fixed, "URL в href испорчен: " + fixed
    assert '.status-card .val{color:red}' in fixed, "пробел в CSS-селекторе съеден: " + fixed
    assert "варварский" not in fixed and "удар по НПЗ" in fixed

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
        # 🔴 отчёт «за час ничего» — не событие; 04.08 такие уходили молнией в канал
        ({"city": "", "target": "", "confidence": "reported",
          "title": "Новых ударов по нефтегазовой инфраструктуре не зафиксировано за последний час"}, "no-event"),
        ({"city": "Москва", "target": "нефтебаза", "confidence": "reported",
          "title": "Отчет за последний час"}, "no-event"),
        ({"city": "", "target": "", "title": "", "confidence": "reported"}, "empty-alert"),
        ({"city": "—", "target": "—", "title": "—", "confidence": "reported"}, "empty-alert"),
        # обычная запись со словом «зафиксирован» в утвердительном смысле — пропускаем
        ({"city": "Рязань", "target": "НПЗ", "confidence": "reported",
          "title": "Зафиксирован пожар на установке"}, None),
        (good, None),
    ]
    for x, exp in cases:
        got = reason_bad(x)
        assert got == exp, "reason_bad(%s) = %r, ожидалось %r" % (x, got, exp)

    r = {"city": "Севастополь", "detail": "Удар по оккупированному порту", "confidence": "reported"}
    assert scrub_record(r) and r["detail"] == "Удар по порту"

    # латиница из англоязычного источника чинится переводом (пост 01.08 в канале)
    s, _ = scrub_text("нефтеперерабатывающий завод Bashneft-UNPZ")
    assert s == "нефтеперерабатывающий завод Башнефть-УНПЗ", s
    assert scrub_text("По информации SBU, атакован завод")[0] == "По информации СБУ, атакован завод"
    # 05.08 этот вариант проскочил в канал — теперь переводится, как и два других завода
    s, _ = scrub_text("Bashneft-Ufaneftekhim нефтеперерабатывающий завод")
    assert s == "Башнефть-Уфанефтехим нефтеперерабатывающий завод", s
    # сторож отставания словаря: незнакомая латиница видна, знакомая — нет
    assert latin_leftovers("удар по Kirishinefteorgsintez") == ["Kirishinefteorgsintez"]
    assert latin_leftovers("склад Wildberries, танкер Nordic Zenith") == []
    assert latin_leftovers("завод Bashneft-Ufaneftekhim") == [], "переведённое не должно всплывать"
    assert scrub_text("TAIF-NK нефтеперерабатывающий завод")[0] == "ТАИФ-НК нефтеперерабатывающий завод"
    # 🔴 суда и бренды латиницей — норма русской прессы, транслит их изуродует
    for keep in ("Танкер Nordic Zenith", "склад Wildberries", "морской терминал NELSA",
                 "склад Ozon", "магазин DNS", "данные NASA FIRMS"):
        assert scrub_text(keep)[1] == 0, keep

    # оценка стороны режется, атрибуция остаётся: читатель должен видеть, кто заявил
    s, _ = scrub_text("Генштаб ВСУ подтвердил успешный удар по порту")
    assert s == "Генштаб ВСУ заявил об ударе по порту", s
    s, _ = scrub_text("СБУ подтвердила поражение объекта")
    assert s == "СБУ заявила о поражении объекта", s
    assert scrub_text("По данным СБУ, поражены 5 резервуаров")[1] == 0, "атрибуцию не трогаем"
    assert scrub_text("Губернатор подтвердил пожар")[1] == 0, "не воюющая сторона — не трогаем"
    print("neutrality demo OK")


if __name__ == "__main__":
    demo()
