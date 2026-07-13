#!/usr/bin/env python3
"""Сборщик итоговых сводок по завершённым волнам БПЛА.

Читает data/wave-events.json, находит волны с ended_at старше 1 часа,
для которых ещё нет сводки в data/wave-summaries.json. Пытается собрать
данные из новостных источников (Медуза, Лента.ру, РБК-Украина) через
парсинг заголовков и текстов, извлекает цифры (общее кол-во БПЛА, сбито,
пострадавшие, разрушения) и пишет итоговую сводку.

Идемпотентен: не перезаписывает уже собранные сводки.
Нейтральный OSINT-тон, только факты из открытых источников.
User-Agent: Mozilla/5.0.

Использование:
    python3 agents/collect-wave-summary.py              # все непокрытые волны
    python3 agents/collect-wave-summary.py --wave WID   # конкретная волна
    python3 agents/collect-wave-summary.py --dry-run    # без записи
"""

import gzip
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# constants
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
EVENTS_PATH = ROOT / "data" / "wave-events.json"
SUMMARIES_PATH = ROOT / "data" / "wave-summaries.json"

MSK = timezone(timedelta(hours=3))
USER_AGENT = "Mozilla/5.0"
TIMEOUT = 15
MIN_AGE_HOURS = 1  # волна должна быть завершена минимум час назад

# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────


def load_json(path: Path, default=None):
    """Безопасная загрузка JSON-файла."""
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data):
    """Атомарная запись JSON: tmp → rename."""
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(str(tmp), str(path))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s: str) -> datetime:
    """ISO-строка (с Z или +00:00) в datetime."""
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def age_hours(ended_iso: str) -> float:
    """Сколько часов прошло с момента ended_at."""
    ended = parse_iso(ended_iso)
    return (now_utc() - ended).total_seconds() / 3600


# ──────────────────────────────────────────────────────────────────────────────
# HTTP fetch
# ──────────────────────────────────────────────────────────────────────────────


def fetch_url(url: str, timeout: int = TIMEOUT) -> str | None:
    """GET-запрос с обработкой ошибок, gzip-декодированием, таймаутом."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # handle gzip
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            # detect encoding
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([\w-]+)", ct)
            if m:
                charset = m.group(1)
            return raw.decode(charset, errors="replace")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# source-specific fetchers
# ──────────────────────────────────────────────────────────────────────────────


def fetch_with_retry(urls: list[str], label: str) -> str | None:
    """Пробует список URL по очереди, возвращает первый успешный HTML."""
    for url in urls:
        html = fetch_url(url)
        if html and len(html) > 500:
            print(f"  [{label}] OK: {url} ({len(html)} байт)")
            return html
    print(f"  [{label}] все URL недоступны")
    return None


def fetch_meduza(date_str: str) -> str | None:
    """Пробует страницы новостей Медузы: RSS, новостная лента, поиск."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    urls = [
        "https://meduza.io/rss/news",
        "https://meduza.io/news",
        f"https://meduza.io/news/{dt.year}/{dt.month:02d}/{dt.day:02d}",
    ]
    return fetch_with_retry(urls, "Meduza")


def fetch_lenta(date_str: str) -> str | None:
    """Лента.ру: RSS и HTML-лента."""
    urls = [
        "https://lenta.ru/rss/news",
        "https://lenta.ru/parts/news/",
        "https://lenta.ru/",
    ]
    return fetch_with_retry(urls, "Lenta")


def fetch_rbc_ua() -> str | None:
    """РБК-Украина: русскоязычная лента."""
    urls = [
        "https://www.rbc.ua/rus/news",
        "https://www.rbc.ua/ukr/news",
    ]
    return fetch_with_retry(urls, "RBC-UA")


# ──────────────────────────────────────────────────────────────────────────────
# number extraction (regex-based)
# ──────────────────────────────────────────────────────────────────────────────


def extract_total_drones(text: str) -> int | None:
    """Извлекает общее количество БПЛА из текста."""
    patterns = [
        # "более 350 БПЛА", "свыше 350 беспилотников", "350 дронов"
        r"(?:более|свыше|около|всего|б[ыы]ло\s+)?(\d{2,4})\s*(?:БПЛА|беспилотник[ао]в|дронов|беспилотных\s+летательных\s+аппаратов)",
        # "атаковали N дронов", "N беспилотников атаковали"
        r"атаковали\s+(?:более\s+)?(\d{2,4})\s*(?:БПЛА|беспилотник[ао]в|дронов)",
        # "запустили N БПЛА", "направили N дронов"
        r"(?:запустили|направили|применили)\s+(?:более\s+)?(\d{2,4})\s*(?:БПЛА|беспилотник[ао]в|дронов)",
        # "N БПЛА [было] зафиксировано"
        r"(\d{2,4})\s*БПЛА\s+(?:было\s+)?зафиксировано",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def extract_shot_down(text: str) -> int | None:
    """Извлекает количество сбитых/уничтоженных БПЛА."""
    patterns = [
        # "сбито 342", "уничтожено 342", "перехвачено 342", "нейтрализовано 342"
        r"(?:сбито|уничтожено|перехвачено|ликвидировано|нейтрализовано|подавлено|уничтожены|сбиты|перехвачены)\s+(?:более\s+)?(\d{2,4})\s*(?:БПЛА|беспилотник[ао]в|дронов)?",
        # "342 сбито", "342 уничтожено", "342 БПЛА сбито"
        r"(\d{2,4})\s+(?:БПЛА\s+)?(?:было\s+)?(?:сбито|уничтожено|перехвачено|ликвидировано|нейтрализовано|подавлено)",
        # "ПВО уничтожила 342", "ПВО сбила 342", "средствами ПВО уничтожены 342"
        r"ПВО\s+(?:уничтожил[аи]|сбил[аи]|перехватил[аи]|нейтрализовал[аи])\s+(?:более\s+)?(\d{2,4})",
        # "силы ПВО ... 342 БПЛА"
        r"(?:силами|средствами)\s+ПВО\s+[^.]{0,40}?(\d{2,4})\s*(?:БПЛА|беспилотник[ао]в|дронов)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def extract_casualties(text: str) -> dict | None:
    """Извлекает данные о погибших/раненых (только для одной атаки, не всей войны)."""
    result = {}
    # dead: ищем в контексте "атаки", "волны", "дронов", "БПЛА", "Москвы", "Подмосковья"
    # но НЕ на RBC-UA (там общие цифры войны)
    dead_pat = r"(?:погиб(?:ло|ли|ших)|жертв(?:а|ами\s+стали)|убит[ыо])\s+(\d{1,2})|(\d{1,2})\s+(?:человека?\s+)?(?:погиб(?:ло|ли)|убит[ыо])"
    for m in re.finditer(dead_pat, text, re.IGNORECASE):
        val = int(m.group(1) or m.group(2))
        # Отсекаем большие числа (вероятно, агрегат всей войны с RBC)
        if val <= 20:
            result["dead"] = val
            break  # берём первое разумное

    # injured:
    inj_pat = r"(?:ранен[ыо]х?|пострадавш[иих]|пострадал[ио]|травмирован[ыо])\s+(\d{1,2})|(\d{1,2})\s+(?:человека?\s+)?(?:ранен[ыо]|пострадал[ио])"
    for m in re.finditer(inj_pat, text, re.IGNORECASE):
        val = int(m.group(1) or m.group(2))
        if val <= 50:
            result["injured"] = val
            break

    return result if result else None


def extract_strikes(text: str) -> list | None:
    """Извлекает данные о точечных ударах/разрушениях по городам."""
    strikes = []

    # Список известных городов/населённых пунктов (из region_list волн + окрестности Москвы)
    KNOWN_CITIES = {
        "Москва", "Истра", "Солнечногорск", "Можайск", "Владимир",
        "Домодедово", "Подольск", "Раменское", "Видное", "Люберцы",
        "Одинцово", "Красногорск", "Химки", "Мытищи", "Балашиха",
        "Коломна", "Ступино", "Кашира", "Серпухов", "Наро-Фоминск",
        "Дмитров", "Клин", "Волоколамск", "Руза", "Звенигород",
        "Тверь", "Рязань", "Тула", "Калуга", "Брянск", "Орёл",
        "Курск", "Белгород", "Воронеж", "Ростов-на-Дону", "Краснодар",
        "Севастополь", "Симферополь", "Керчь", "Джанкой",
        "Санкт-Петербург", "Пионерский", "Бабкино",
    }

    # Слова и фразы, которые гарантированно НЕ являются городами
    NON_CITY_BLACKLIST = {
        "многоквартирном", "многоквартирный", "частном", "жилом",
        "результате", "ходе", "итоге", "целом", "числе", "списке",
        "составе", "рамках", "связи", "случае", "отношении",
        "течение", "течении", "настоящее", "ближайшее",
        "пресс-служба", "пресс", "свою", "свой",
        "Федорищев",  # фамилия, часто в новостях
    }

    # Слова-маркеры, означающие что это НЕ город
    NON_CITY_SUFFIXES = (
        "области", "края", "района", "округа", "республики",
    )

    def _clean_city(raw: str) -> str | None:
        """Очищает название города от падежных окончаний и лишних слов."""
        # Убираем trailing words like "также", "уже", "ещё"
        raw = re.sub(r"\s+(?:также|уже|ещё|всего|лишь|только)$", "", raw, flags=re.IGNORECASE)
        # Блэклист не-городов
        if raw.lower() in NON_CITY_BLACKLIST:
            return None
        # Проверяем не регион ли это
        for sfx in NON_CITY_SUFFIXES:
            if raw.lower().endswith(" " + sfx) or raw.lower().endswith(sfx):
                return None
        # Нормализуем падеж (убираем окончания если известен город)
        for kc in KNOWN_CITIES:
            if raw.lower().startswith(kc.lower()[:4]) or kc.lower().startswith(raw.lower()[:4]):
                return kc
        # Если слово не в списке известных городов — пропускаем
        # (слишком много ложных срабатываний на случайных существительных)
        return None

    # Паттерн: "в Городе ... повреждены/разрушены/загорелись N домов/зданий"
    city_pat = re.compile(
        r"(?:в|города?|посёлке|селе|деревне|населённом\s+пункте)\s+"
        r"([А-ЯЁ][а-яё]+(?:[\s-]+[А-ЯЁ][а-яё]+)?(?:\s+(?:также|уже|ещё))?)\s"
        r"[^.]{0,200}?"
        r"(?:поврежден[ыо]|разрушен[ыо]|загорел[ио]сь|пострадал[ио]|"
        r"удар\s+(?:приш[ёе]лся|нан[её]сён)|атакован[ыо]|"
        r"обломк[иа]\s+(?:упали|рухнули|повредили)|"
        r"пожар\s+(?:возник|начался|произош[ёе]л)|"
        r"взрыв[ыо]?\s+(?:прогремел|произош[ёе]л|зафиксирован))",
        re.IGNORECASE,
    )

    for m in city_pat.finditer(text):
        city = _clean_city(m.group(1))
        if city is None:
            continue

        snippet = text[m.start():m.start() + 300]
        strike = {"city": city, "target": "не уточняется"}

        # Что именно повреждено
        tgt_m = re.search(
            r"(?:поврежден[ыо]|разрушен[ыо]|загорел[ио]сь|пострадал[ио])\s+"
            r"(?:(\d+)\s+)?"
            r"((?:частны[йе]\s+)?(?:жилы[йе]\s+)?"
            r"(?:многоквартирны[йе]\s+)?(?:многоэтажны[йе]\s+)?"
            r"(?:дом[ао]в?|здани[йя]|квартир[ы]?|строени[йя]|сооружени[йя]|объект[ао]в?))",
            snippet, re.IGNORECASE,
        )
        if tgt_m:
            if tgt_m.group(1):
                strike["destroyed"] = int(tgt_m.group(1))
            else:
                strike["destroyed"] = 1  # минимум 1 объект
            strike["target"] = tgt_m.group(2).strip()

        # dead/injured в сниппете
        dm = re.search(r"(\d{1,2})\s*(?:человека?\s+)?(?:погиб|убит|жертв)", snippet, re.IGNORECASE)
        if dm:
            strike["dead"] = int(dm.group(1))
        im = re.search(r"(\d{1,2})\s*(?:человека?\s+)?(?:ранен|пострадал|травмирован)", snippet, re.IGNORECASE)
        if im:
            strike["injured"] = int(im.group(1))

        # Дедубликация по городу
        if not any(s["city"].lower() == city.lower() for s in strikes):
            strikes.append(strike)

    return strikes if strikes else None


def extract_sources(text: str) -> list[str]:
    """Извлекает упомянутые источники."""
    known = [
        "Минобороны РФ", "Минобороны России",
        "Сергей Собянин", "Андрей Воробьёв",
        "МЧС", "МЧС России",
        "губернатор", "мэр",
        "ТАСС", "РИА Новости", "Интерфакс",
        "Baza", "Shot", "Mash",
    ]
    found = []
    text_lower = text.lower()
    for src in known:
        if src.lower() in text_lower:
            # нормализуем
            if src == "Минобороны России":
                src = "Минобороны РФ"
            if src in ("губернатор", "мэр"):
                continue  # слишком обще
            if src not in found:
                found.append(src)
    return found


# ──────────────────────────────────────────────────────────────────────────────
# main logic
# ──────────────────────────────────────────────────────────────────────────────


def build_empty_summary(wave_id: str) -> dict:
    """Шаблон пустой сводки (заполнится данными или вернётся как есть)."""
    return {
        "wave_id": wave_id,
        "total_drones": None,
        "shot_down": None,
        "reached_targets": None,
        "casualties": {"dead": 0, "injured": 0},
        "strikes": [],
        "sources": [],
        "summary_text": "",
        "collected_at": now_utc().isoformat(),
    }


def collect_summary(wave: dict) -> dict | None:
    """Собирает сводку по одной волне из новостных источников."""
    wave_id = wave["id"]
    date_str = wave.get("date", "")[:10]  # YYYY-MM-DD
    summary = build_empty_summary(wave_id)

    all_texts: list[str] = []
    sources_found: list[str] = []

    # 1) Медуза
    html = fetch_meduza(date_str)
    if html:
        # удаляем HTML-теги для текстового анализа
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 200:
            all_texts.append(text)
            sources_found.extend(extract_sources(text))

    # 2) Лента.ру
    html = fetch_lenta(date_str)
    if html:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 200:
            all_texts.append(text)
            sources_found.extend(extract_sources(text))

    # 3) РБК-Украина
    html = fetch_rbc_ua()
    if html:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 200:
            all_texts.append(text)
            # РБК-UA как источник добавляем явно
            if "РБК-Украина" not in sources_found:
                sources_found.append("РБК-Украина")

    if not all_texts:
        print(f"[{wave_id}] не удалось загрузить ни одного источника новостей")
        return None

    combined = "\n".join(all_texts)

    # ── извлечение цифр ──
    total = extract_total_drones(combined)
    shot = extract_shot_down(combined)
    cas = extract_casualties(combined)
    strikes = extract_strikes(combined)

    if total:
        summary["total_drones"] = total
    if shot:
        summary["shot_down"] = shot
    if total and shot:
        # долетело = всего - сбито
        reached = max(0, total - shot)
        if reached > 0:
            summary["reached_targets"] = reached
    elif total:
        # если не нашли сбито, но есть общее — не вычисляем reached
        pass

    if cas:
        summary["casualties"]["dead"] = cas.get("dead", 0)
        summary["casualties"]["injured"] = cas.get("injured", 0)

    if strikes:
        summary["strikes"] = strikes

    if sources_found:
        # дедубликация с сохранением порядка
        seen = set()
        uniq = []
        for s in sources_found:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        summary["sources"] = uniq

    # ── summary_text ──
    parts = []
    dt = datetime.strptime(date_str, "%Y-%m-%d") if date_str else None
    if dt:
        # определяем время суток для текста
        started = wave.get("started_at", "")
        if started:
            try:
                h = parse_iso(started).astimezone(MSK).hour
                if h < 6:
                    tod_phrase = "ночь"
                elif h < 12:
                    tod_phrase = "утро"
                elif h < 18:
                    tod_phrase = "день"
                else:
                    tod_phrase = "вечер"
            except Exception:
                tod_phrase = "ночь"
        else:
            tod_phrase = "ночь"

        next_day = dt + timedelta(days=1)
        ru_months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ]
        date_human = f"{next_day.day} {ru_months[next_day.month - 1]}"

        # Правильное склонение: "В ночь на 13 июля", "Утром 13 июля"
        if tod_phrase == "ночь":
            when = f"В ночь на {date_human}"
        elif tod_phrase == "утро":
            when = f"Утром {date_human}"
        elif tod_phrase == "день":
            when = f"Днём {date_human}"
        else:
            when = f"Вечером {date_human}"

        if total:
            parts.append(
            f"{when} Москву и Подмосковье атаковали "
                f"{'более ' if total >= 300 else ''}{total} БПЛА."
            )
        if shot:
            parts.append(f"Сбито {shot} беспилотников.")
        if total and shot and total > shot:
            parts.append(f"Долетели до целей {total - shot} БПЛА.")
        if cas and (cas.get("dead") or cas.get("injured")):
            cparts = []
            if cas.get("dead"):
                cparts.append(f"{cas['dead']} погиб{'ших' if cas['dead'] > 1 else 'ший'}")
            if cas.get("injured"):
                cparts.append(f"{cas['injured']} ранен{'ых' if cas['injured'] > 1 else 'ый'}")
            parts.append("Пострадавшие: " + ", ".join(cparts) + ".")
        if strikes:
            strike_parts = []
            for s in strikes:
                sp = f"{s['city']} — {s['target']}"
                if s.get("destroyed"):
                    sp += f" ({s['destroyed']} объектов)"
                if s.get("dead"):
                    sp += f", {s['dead']} погибших"
                if s.get("injured"):
                    sp += f", {s['injured']} раненых"
                strike_parts.append(sp)
            parts.append("Разрушения: " + "; ".join(strike_parts) + ".")
        if summary["sources"]:
            parts.append("Источники: " + ", ".join(summary["sources"]) + ".")

    summary["summary_text"] = " ".join(parts)

    return summary


def get_completed_waves(min_age_hours: float = MIN_AGE_HOURS) -> list[dict]:
    """Возвращает список завершённых волн (ended_at есть и старше N часов)."""
    events = load_json(EVENTS_PATH, default=[])
    if not isinstance(events, list):
        return []

    completed = []
    seen_ids = set()
    for ev in events:
        wid = ev.get("id", "")
        ended = ev.get("ended_at")
        if not ended:
            continue
        # берём последнюю (с самым поздним ended_at) для каждого id
        key = (wid, ended)
        if wid in seen_ids:
            # обновляем если этот экземпляр завершён позже
            for i, c in enumerate(completed):
                if c["id"] == wid and ended > c.get("ended_at", ""):
                    completed[i] = ev
            continue
        seen_ids.add(wid)
        if age_hours(ended) >= min_age_hours:
            completed.append(ev)

    return completed


def main():
    dry_run = "--dry-run" in sys.argv
    target_wave = None

    for arg in sys.argv[1:]:
        if arg.startswith("--wave="):
            target_wave = arg.split("=", 1)[1]
        elif arg == "--wave" and len(sys.argv) > sys.argv.index(arg) + 1:
            target_wave = sys.argv[sys.argv.index(arg) + 1]

    # ── загружаем существующие сводки ──
    summaries = load_json(SUMMARIES_PATH, default={})
    if not isinstance(summaries, dict):
        summaries = {}

    # ── выбираем волны для обработки ──
    if target_wave:
        # конкретная волна — берём из событий
        events = load_json(EVENTS_PATH, default=[])
        waves = []
        for ev in events:
            if ev.get("id") == target_wave and ev.get("ended_at"):
                waves.append(ev)
        if not waves:
            # даже если нет ended_at — форсируем для теста
            for ev in events:
                if ev.get("id") == target_wave:
                    waves.append(ev)
                    break
        if not waves:
            print(f"Волна {target_wave} не найдена в wave-events.json")
            return 1
    else:
        waves = get_completed_waves()

    if not waves:
        print("Нет завершённых волн для обработки.")
        return 0

    # ── обработка ──
    new_count = 0
    skip_count = 0

    for wave in waves:
        wave_id = wave["id"]
        if wave_id in summaries:
            print(f"[{wave_id}] сводка уже существует — пропускаем")
            skip_count += 1
            continue

        print(f"[{wave_id}] собираем сводку...")
        summary = collect_summary(wave)

        if summary is None:
            print(f"[{wave_id}] не удалось собрать данные — пропускаем")
            continue

        # проверяем, что хоть что-то собрали
        has_data = (
            summary.get("total_drones")
            or summary.get("shot_down")
            or summary.get("strikes")
            or summary.get("summary_text")
        )
        if not has_data:
            print(f"[{wave_id}] данные не извлечены — пропускаем")
            continue

        summaries[wave_id] = summary
        new_count += 1
        print(f"[{wave_id}] сводка готова: total={summary.get('total_drones')}, "
              f"shot_down={summary.get('shot_down')}, "
              f"strikes={len(summary.get('strikes', []))}")

    if dry_run:
        print(f"\n[dry-run] было бы записано: +{new_count} сводок, "
              f"пропущено: {skip_count}")
        if new_count:
            # показываем что получилось
            for wid, s in summaries.items():
                if s.get("summary_text"):
                    print(f"\n── {wid} ──")
                    print(s["summary_text"])
        return 0

    if new_count:
        save_json(SUMMARIES_PATH, summaries)
        print(f"\nЗаписано в {SUMMARIES_PATH}: +{new_count} новых сводок "
              f"(всего {len(summaries)}), пропущено: {skip_count}")
    else:
        print(f"\nНовых сводок нет (пропущено: {skip_count})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
