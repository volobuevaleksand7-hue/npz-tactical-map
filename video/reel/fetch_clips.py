#!/usr/bin/env python3
"""Кадры очевидцев к ударам дня: скачивание + автовыбор 3–5 с + приведение к 9:16.

  python3 video/reel/fetch_clips.py <YYYY-MM-DD>        # для ударов, выбранных select_strikes()
  python3 video/reel/fetch_clips.py --url <url> <city> <date>   # отладка одного источника

Источники (без аккаунтов, только публичные страницы):
  1. source_url = t.me/<канал>/<id> -> embed-страница t.me/<канал>/<id>?embed=1 отдаёт <video src=…mp4>;
  2. нет видео в самом посте -> соседние посты того же канала (id-3..id+8) и поиск по каналу
     t.me/s/<канал>?q=<город>, только посты той же даты (±1 день) с упоминанием города;
  3. нет видео — фото из поста (медленный наезд, 3 с);
  4. source_url — новостной сайт -> yt-dlp (если там встроено видео).
Кэш — video/reel/cache/ (в git не идёт). Только stdlib + ffmpeg/ffprobe/yt-dlp.
Звук исходника вырезается: в ролике только музыка и эффекты.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REEL = Path(__file__).resolve().parent
CACHE = REEL / "cache"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
# 10.10.2026: обновление YouTube от 01.10.2026 режет охват перезаливов чужого видео. Один чужой фрагмент
# <= 5 с (build_reel.FOREIGN_SEG_MAX), у нас 4 с; суммарная доля чужих кадров (<= 1/3 ролика) считается в build_reel.fit_budget.
SEG = 4.0          # длина отрезка, с
assert SEG <= 5.0, "чужой фрагмент не длиннее 5 с (см. build_reel.FOREIGN_SEG_MAX)"
# каналы с видео ударов: поиск по городу идёт и по ним, даже если source_url удара — новостной сайт
CHANNELS = [c for c in os.environ.get("REEL_CHANNELS", "exilenova_plus,supernova_plus,astrapress,mash,tvrain,ostorozhno_novosti,shot_shot").split(",") if c]
ATTACK_RX = re.compile(r"взрыв|вибух|пожар|пожеж|бпла|беспилот|дрон|атак|удар|нпз|нефт|нафт|склад|пво|горит|палає|"
                       r"прилёт|приліт|обстрел|ракет|вирв|воронк|наслідк|последств|уражен|поражен|танкер|разлив", re.I)
# оккупированные/чужие территории — рилс про удары по России, такие кадры не берём
OCC_RX = re.compile(r"окуп|крим|крым|севастоп|донец|донеч|мелітоп|мелитоп|херсон|запоріж|запорож|луганс|"
                    r"маріупол|мариупол|волноваx|волноваха|бердянськ|бердянск|мост", re.I)
W, H = 1080, 1920


def log(*a):
    print("fetch:", *a, file=sys.stderr)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url, dest: Path):
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(get(url, timeout=120))
    tmp.rename(dest)
    return dest


# ───────────────────────────── Telegram ─────────────────────────────

TG_RX = re.compile(r"https?://t\.me/(?:s/)?([A-Za-z0-9_]{4,})/(\d+)")
TG_CHAN_RX = re.compile(r"https?://t\.me/(?:s/)?([A-Za-z0-9_]{4,})/?(?:\?.*)?$")


def _text(block):
    m = re.search(r'js-message_text[^>]*>(.*?)</div>', block, re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""


def _media(block):
    vids = re.findall(r'<video[^>]*src="([^"]+)"', block)
    photos = re.findall(r"message_photo_wrap[^>]*background-image:url\('([^']+)'\)", block)
    when = (re.findall(r'datetime="([^"]+)"', block) or [""])[0]   # ISO с часовым поясом
    return [html.unescape(v) for v in vids], [html.unescape(p) for p in photos], when


def tg_post(chan, pid):
    try:
        page = get(f"https://t.me/{chan}/{pid}?embed=1&mode=tme").decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — сеть/404: просто нет медиа
        log(f"t.me/{chan}/{pid}: {e}")
        return None
    vids, photos, when = _media(page)
    return {"url": f"https://t.me/{chan}/{pid}", "videos": vids, "photos": photos,
            "date": when, "text": _text(page)}


def tg_search(chan, q):
    try:
        page = get(f"https://t.me/s/{chan}?q={urllib.parse.quote(q)}").decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        log(f"t.me/s/{chan}?q={q}: {e}")
        return []
    out = []
    for block in page.split('class="tgme_widget_message_wrap')[1:]:
        m = re.search(r'data-post="([^"/]+)/(\d+)"', block)
        if not m:
            continue
        vids, photos, when = _media(block)
        out.append({"url": f"https://t.me/{m.group(1)}/{m.group(2)}", "videos": vids, "photos": photos,
                    "date": when, "text": _text(block)})
    return out


def city_stem(city):
    c = re.sub(r"\s+(район|область|округ)$", "", str(city or "").strip(), flags=re.I)
    c = c.split()[0] if c else ""
    return c[:-1].lower() if len(c) > 5 else c.lower()  # «Самар», «Волгогра»: ловит падежи


def date_ok(when, day):
    """Пост про удар даты D: от 00:00 МСК D до 12:00 МСК D+1 (ночные удары, утренние досъёмки).
    Шире нельзя: «±1 день» цеплял вчерашнюю атаку на тот же город (Калуга, 04.10)."""
    if not when:
        return True
    try:
        t = datetime.fromisoformat(when).astimezone(timezone(timedelta(hours=3))).replace(tzinfo=None)
    except ValueError:
        return when[:10] == day
    d0 = datetime.fromisoformat(day)
    return d0 <= t < d0 + timedelta(hours=36)


def channel_posts(chan, pages=8):
    """Свежие посты канала (t.me/s/<канал>, листание ?before=) — для кадров «хроники дня»."""
    out, before = [], None
    for _ in range(pages):
        try:
            page = get(f"https://t.me/s/{chan}" + (f"?before={before}" if before else "")).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            log(f"t.me/s/{chan}: {e}")
            break
        ids = []
        for block in page.split('class="tgme_widget_message_wrap')[1:]:
            m = re.search(r'data-post="([^"/]+)/(\d+)"', block)
            if not m:
                continue
            ids.append(int(m.group(2)))
            vids, photos, when = _media(block)
            out.append({"url": f"https://t.me/{m.group(1)}/{m.group(2)}", "videos": vids, "photos": photos,
                        "date": when, "text": _text(block)})
        if not ids:
            break
        before = min(ids)
    return out


_UA2RU = str.maketrans({"ё": "е", "і": "и", "ї": "и", "є": "е", "ґ": "г", "ы": "и", "э": "е",
                        "ь": None, "ъ": None, "'": None, "’": None, "ʼ": None})
# Слова-родовые: по ним пост не опознать («завод», «область»). Опознаём по именам собственным.
_GENERIC = re.compile(r"^(нефтеперерабат|нефтехим|нефтебаз|нефтеналив|нефтян|завод|станц|линейн|производств|"
                      r"диспетчер|логистич|распредел|фулфилмент|центр|склад|терминал|област|район|республик|"
                      r"край|округ|акватор|жил|здан|топлив|хранилищ|энерго|подстанц|тэц|грэс|нпз|лпдс|нпс|"
                      r"танкер|порт|товар|крупногабарит|маркетплейс|компан|предприят|объект|"
                      r"январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр)")


def norm(s):
    """Русский и украинский к одному виду: «Сочі»→«сочи», «Московський»→«московскии»."""
    return str(s or "").lower().translate(_UA2RU)


def strike_keys(strike):
    """{основа: вес}. Имя объекта из target (Володарская, Московский, Ozon) — 2,
    город — 2, если это не область целиком (тогда 1: «Московская область» слишком широко)."""
    keys = {}

    def add(word, w):
        word = norm(re.sub(r"[^\w-]", "", word))
        if len(word) < 4 or _GENERIC.match(word):
            return
        stem = word[:max(5, len(word) - 4)] if len(word) > 5 else word
        keys[stem] = max(keys.get(stem, 0), w)

    city = str(strike.get("city") or "")
    wide = bool(re.search(r"област|край|республик|округ", city, re.I))
    for w in re.findall(r"[А-ЯЁA-Z][\w-]+", re.sub(r"\(.*?\)", "", city)):
        add(w, 1 if wide else 2)
    target = str(strike.get("target") or "")
    for w in re.findall(r"[А-ЯЁA-Z][\w-]+", target) + re.findall(r"«([^»]+)»", target):
        for part in str(w).split():
            add(part, 2)
    return keys


_FEED = {}


def channel_feed(chan):
    if chan not in _FEED:
        _FEED[chan] = channel_posts(chan, pages=int(os.environ.get("REEL_FEED_PAGES", "14")))
    return _FEED[chan]


def channel_match(strike, seen=()):
    """Посты каналов-хроник за окно удара с медиа, где названы город или объект.
    Лента канала целиком, а не поиск t.me/s?q=: поиск отдаёт 20 старых совпадений
    и не знает украинских форм («Московський НПЗ», «Сочі»), из-за этого 06–07.10
    кадры Капотни, Володарской и танкера у Сочи лежали в канале, а рилс шёл без них."""
    keys, day = strike_keys(strike), str(strike.get("date"))[:10]
    if not keys:
        return []
    tgt = norm(strike.get("target"))
    kinds = [k for k in ("нпз", "нефтебаз", "лпдс", "танкер", "склад", "подстанц", "тэц", "терминал", "порт")
             if k in tgt]
    scored = []
    for chan in CHANNELS:
        for p in channel_feed(chan):
            if p["url"] in seen or not (p["videos"] or p["photos"]) or not date_ok(p["date"], day):
                continue
            t = norm(p["text"])
            if OCC_RX.search(p["text"]) or not ATTACK_RX.search(p["text"]):
                continue
            score = sum(w for k, w in keys.items() if k in t)
            score += sum(1 for k in kinds if k in t)   # тот же тип объекта: «НПЗ», «танкер»
            if score >= 2:
                scored.append((score, len(p["videos"]), dict(p, _score=score)))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    if scored:
        log(f"{strike.get('city')}: в лентах {len(scored)} постов — " +
            ", ".join(f"{p['url'].rsplit('/', 2)[-2]}/{p['url'].rsplit('/', 1)[-1]}({sc})" for sc, _, p in scored[:4]))
    return [p for _, _, p in scored]


VERIFY_MODELS = [m for m in os.environ.get(
    "REEL_VERIFY_MODELS", "nvidia/nemotron-3.5-lightning:free,google/gemma-4-31b-it:free,nvidia/nemotron-3-super-120b-a12b:free").split(",") if m]
OR_KEY = Path(os.environ.get("OPENROUTER_KEY_FILE", "/root/.openrouter/api_key"))
VERIFY_PROMPT = """Ниже удар по объекту в России и посты Telegram-каналов с видео за те же сутки.
Отбери посты, где показан или описан ИМЕННО этот удар: то же место (город/объект), та же ночь.
Не подходят: другой город или объект, общая сводка «атака на область» без этого места, удары
по Украине, фронт, мемы, политика. Посты на украинском и русском равноправны.
Ответь только JSON: {"ok": [номера подходящих постов по убыванию уверенности]}.

Удар: {strike}

Посты:
{posts}"""


def _llm_json(prompt):
    """JSON-ответ модели: Haiku (claude CLI) → OpenRouter free (запас: free-модели почти всегда 429). None — никто не ответил."""
    for _ in range(2 if shutil.which("claude") else 0):   # Haiku изредка не отвечает — второй заход
        try:
            r = subprocess.run(["claude-run", "-p", prompt, "--model",
                                os.environ.get("REEL_LLM_MODEL", "claude-haiku-5-5"), "--effort", "high"],
                               capture_output=True, text=True, timeout=120)
            m = re.search(r"\{.*\}", r.stdout, re.S)
            if m:
                return json.loads(m.group(0)), "haiku"
            log(f"проверка постов: haiku без JSON: {r.stdout[-120:]!r} {r.stderr[-120:]!r}")
        except Exception as e:  # noqa: BLE001
            log(f"проверка постов: haiku: {e}")
    if OR_KEY.exists():
        key = OR_KEY.read_text().strip()
        for model in VERIFY_MODELS:
            body = json.dumps({"model": model, "temperature": 0,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                         {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    txt = json.load(r)["choices"][0]["message"]["content"] or ""
                m = re.search(r"\{.*\}", txt, re.S)
                if m:
                    return json.loads(m.group(0)), model
            except Exception as e:  # noqa: BLE001 — 429/таймаут: следующая модель
                log(f"проверка постов: {model}: {e}")
    return None, None


def verify_posts(strike, posts):
    """Отсеять посты, где удар не тот. Модель недоступна — оставить только сильные совпадения."""
    if not posts or os.environ.get("REEL_VERIFY", "1") == "0":
        return posts
    posts = posts[:8]
    desc = f"{strike.get('date')}, {strike.get('city')}, {strike.get('region') or ''} — {strike.get('target')}"
    listing = "\n".join(f"{i + 1}. [{p['date'][:16]}] {' '.join(p['text'].split())[:350]}"
                         for i, p in enumerate(posts))
    ans, model = _llm_json(VERIFY_PROMPT.replace("{strike}", desc).replace("{posts}", listing))
    if ans is None:
        strong = [p for p in posts if p.get("_score", 0) >= 4]   # объект + город/тип — иначе лучше без клипа
        log(f"{strike.get('city')}: проверка недоступна — беру {len(strong)} сильных из {len(posts)}")
        return strong
    keep = []
    for n in ans.get("ok", []):
        if isinstance(n, int) and 1 <= n <= len(posts) and posts[n - 1] not in keep:
            keep.append(posts[n - 1])
    log(f"{strike.get('city')}: {model} подтвердил {len(keep)} из {len(posts)}")
    return keep


def tg_candidates(strike):
    """Посты по удару: из source_url, затем ленты каналов-хроник, затем поиск города."""
    posts = _own_candidates(strike)
    if any(p["videos"] or p["photos"] for p in posts):
        return posts
    seen = {p["url"] for p in posts}
    matched = channel_match(strike, seen)
    seen |= {p["url"] for p in matched}   # отвергнутое моделью не вернётся через поиск по городу
    for p in verify_posts(strike, matched):
        posts.append(p)
        seen.add(p["url"])
    if any(p["videos"] for p in posts):
        return posts
    stem, day = city_stem(strike.get("city")), str(strike.get("date"))[:10]
    if not stem:
        return posts
    found = []
    for chan in CHANNELS:
        for p in tg_search(chan, stem):
            if p["url"] not in seen and stem in p["text"].lower() and ATTACK_RX.search(p["text"]) \
                    and date_ok(p["date"], day) and (p["videos"] or p["photos"]):
                found.append(dict(p, _score=2))   # без модели не берём: город в тексте ≠ удар по нему
                seen.add(p["url"])
    # поиск по городу ловит и «соседние» новости (пост про Москву, где Рязань в перечне) — та же проверка
    return posts + verify_posts(strike, found)


def _own_candidates(strike):
    """Посты с медиа по удару: сам пост, затем соседние/поиск с городом и датой."""
    src = str(strike.get("source_url") or "")
    m = TG_RX.match(src)
    stem, day = city_stem(strike.get("city")), str(strike.get("date"))[:10]
    if not m:
        # ссылка на канал целиком (t.me/s/<канал>) — только поиск поста с городом и датой;
        # «последнее видео канала» (так делал yt-dlp) — почти всегда чужой удар (инцидент 04.10)
        c = TG_CHAN_RX.match(src)
        if not (c and stem):
            return []
        return [p for p in tg_search(c.group(1), stem)
                if stem in p["text"].lower() and date_ok(p["date"], day) and (p["videos"] or p["photos"])]
    chan, pid = m.group(1), int(m.group(2))
    first = tg_post(chan, pid)
    posts = [first] if first else []
    near = []
    for k in list(range(1, 9)) + [-1, -2, -3]:
        p = tg_post(chan, pid + k)
        if p and (p["videos"] or p["photos"]) and stem and stem in p["text"].lower() and date_ok(p["date"], day):
            near.append(p)
    posts += near
    if stem:
        for p in tg_search(chan, stem):
            if p["url"] not in {x["url"] for x in posts} and stem in p["text"].lower() and date_ok(p["date"], day) \
                    and (p["videos"] or p["photos"]):
                posts.append(p)
    return posts


# ───────────────────────────── выбор отрезка ─────────────────────────────

def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    st = j["streams"][0]
    return int(st["width"]), int(st["height"]), float(j["format"].get("duration") or 0)


def activity(path, fps=5):
    """[(t, ydif, yavg)]: межкадровая разница и яркость по кадрам, ffmpeg signalstats."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf",
           f"fps={fps},scale=160:-2,signalstats,metadata=print:file=-", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    rows, cur = [], {}
    for line in out.splitlines():
        if line.startswith("frame:"):
            if cur:
                rows.append(cur)
            t = re.search(r"pts_time:([\d.]+)", line)
            cur = {"t": float(t.group(1)) if t else len(rows) / fps}
        else:
            m = re.match(r"lavfi\.signalstats\.(YDIF|YAVG|YMAX)=([\d.]+)", line)
            if m:
                cur[m.group(1)] = float(m.group(2))
    if cur:
        rows.append(cur)
    return rows


def windows(path, dur, seg=SEG, k=1):
    """Начала k самых «живых» непересекающихся отрезков: движение (медиана YDIF — одна склейка или
    рывок камеры не решают) + немного яркости (огонь/вспышки). Первые 0,3 с пропускаем (часто
    чёрный кадр/заставка)."""
    if dur <= seg + 0.4:
        return [0.0]
    rows = activity(path)
    if len(rows) < 4:
        return [round(max(0.0, (dur - seg) / 2), 2)]
    scored = []
    t = 0.3
    while t + seg <= dur - 0.1:
        win = [r for r in rows if t <= r["t"] < t + seg]
        if win:
            difs = sorted(r.get("YDIF", 0) for r in win)
            ydif = min(difs[len(difs) // 2], 30)
            yavg = sum(r.get("YAVG", 0) for r in win) / len(win)
            dark_pen = 8 if yavg < 18 else 0  # почти чёрный — не берём
            scored.append((ydif + 0.04 * yavg - dark_pen, round(t, 2)))
        t += 0.25
    out = []
    for _, t in sorted(scored, reverse=True):
        if all(abs(t - o) >= seg for o in out):
            out.append(t)
        if len(out) >= k:
            break
    return out or [0.3]


def best_window(path, dur, seg=SEG):
    return windows(path, dur, seg, 1)[0]


VISION_MODELS = [m for m in os.environ.get(
    "REEL_VISION_MODELS", "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free").split(",") if m]
VISION_PROMPT = ("Это сетка из {n} кадров (слева направо, сверху вниз, номера 1..{n}) из видео очевидцев "
                 "удара по объекту: {what}. Выбери кадр, где ЛУЧШЕ ВСЕГО и чётко видно пожар, дым, вспышку, "
                 "взрыв или разрушения, без перекрытия посторонним предметом. Не подходят: заставка или логотип "
                 "на весь кадр, размытое пятно, тёмный кадр без огня, люди (любые узнаваемые лица, крупные и средние планы), "
                 "пострадавшие, погибшие. Людей в кадре быть не должно: если во всех кадрах люди — ответ 0. "
                 'Ответь только JSON: {{"best": номер}} или {{"best": 0}}, если не подходит ни один.')


def _vision_pick(tile, n, what):
    """Номер лучшего кадра сетки (1..n), 0 — ни один, None — модель недоступна."""
    prompt = VISION_PROMPT.format(n=n, what=what)
    if shutil.which("claude"):
        try:
            r = subprocess.run(["claude-run", "-p", f"Открой изображение {tile} инструментом Read. " + prompt,
                                "--model", os.environ.get("REEL_LLM_MODEL", "claude-haiku-5-5"), "--effort", "high",
                                "--allowedTools", "Read"], capture_output=True, text=True, timeout=180)
            m = re.search(r'"best"\s*:\s*(\d+)', r.stdout)
            if m:
                return int(m.group(1)), "haiku"
        except Exception as e:  # noqa: BLE001
            log(f"выбор кадра: haiku: {e}")
    if OR_KEY.exists():
        import base64
        key = OR_KEY.read_text().strip()
        img = "data:image/jpeg;base64," + base64.b64encode(Path(tile).read_bytes()).decode()
        for model in VISION_MODELS:
            body = json.dumps({"model": model, "temperature": 0, "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": img}}]}]}).encode()
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body,
                                         {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    txt = json.load(r)["choices"][0]["message"]["content"] or ""
                m = re.search(r'"best"\s*:\s*(\d+)', txt)
                if m:
                    return int(m.group(1)), model
            except Exception as e:  # noqa: BLE001
                log(f"выбор кадра: {model}: {e}")
    return None, None


def pick_window(cands, seg, what, work: Path):
    """cands: [(raw, dur, payload)] — лучшие видео. Режем каждое на 3 окна-кандидата, кадры из
    середины окон кладём в одну сетку и один раз спрашиваем модель со зрением, где виден удар.
    -> (raw, start, payload) | None (модель видела и ничего не выбрала). Без модели — эвристика."""
    opts = []
    for raw, dur, payload in cands[:3]:
        s = min(seg, dur - 0.2)
        for t in windows(raw, dur, s, 3):
            opts.append((raw, t, s, payload))
    if os.environ.get("REEL_VISION", "1") == "0" or len(opts) < 2:
        raw, t, s, payload = opts[0]
        return raw, t, s, payload
    frames = []
    for i, (raw, t, s, _) in enumerate(opts):
        fr = work / f"vis-{i}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t + s / 2:.2f}", "-i", str(raw),
                        "-frames:v", "1", "-vf", "scale=360:360:force_original_aspect_ratio=decrease,"
                        "pad=360:360:(ow-iw)/2:(oh-ih)/2", str(fr)], check=False)
        if fr.exists():
            frames.append((fr, i))
    if len(frames) < 2:
        raw, t, s, payload = opts[0]
        return raw, t, s, payload
    cols = 3 if len(frames) > 4 else 2
    rows = -(-len(frames) // cols)
    tile = work / "vis-tile.jpg"
    inputs = sum((["-i", str(fr)] for fr, _ in frames), [])
    lay = "|".join(f"{(j % cols) * 360}_{(j // cols) * 360}" for j in range(len(frames)))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex",
                    f"xstack=inputs={len(frames)}:layout={lay}:fill=black", str(tile)], check=False)
    if not tile.exists():
        raw, t, s, payload = opts[0]
        return raw, t, s, payload
    n, model = _vision_pick(tile, len(frames), what)
    if n is None:
        log("выбор кадра: модели недоступны — беру эвристику")
        raw, t, s, payload = opts[0]
        return raw, t, s, payload
    log(f"выбор кадра: {model} → {n} из {len(frames)}")
    if not 1 <= n <= len(frames):
        return None
    raw, t, s, payload = opts[frames[n - 1][1]]
    return raw, t, s, payload


def to_vertical(src, start, seg, dest: Path):
    """9:16 без звука: горизонталь — увеличенный центр поверх размытого фона (кадр заполнен),
    вертикаль — cover-кроп. Края с логотипами каналов частично срезаются."""
    w, h, _ = probe(src)
    dl = delogo_filter(src, w, h)
    if h >= w * 1.4:   # вертикальное видео
        fc = f"[0:v]{dl}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v]"
        vf = None
    else:
        fg_w = int(W * 1.5) // 2 * 2  # чуть больше ширины кадра — режем края (там часто логотипы)
        fc = (f"[0:v]{dl}split=2[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:2,eq=brightness=-0.12[bg];"
              f"[b]scale={fg_w}:-2,crop={W}:ih[fg];"
              f"[bg][fg]overlay=0:(H-h)/2-60,setsar=1[v]")
        vf = None
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(seg), "-i", str(src)]
    if fc:
        cmd += ["-filter_complex", fc, "-map", "[v]"]
    else:
        cmd += ["-vf", vf]
    cmd += ["-an", "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(dest)]
    subprocess.run(cmd, check=True, timeout=300)
    return dest


# водяной знак канала-источника: центральный логотип (доли кадра x0,y0,x1,y1); фильтр delogo заменяет
# область интерполяцией соседних пикселей. Бледная диагональная надпись по всему кадру остаётся.
WATERMARKS = {"exilenova": (0.345, 0.468, 0.652, 0.53)}


def delogo_filter(src, w, h):
    """Префикс цепочки ffmpeg для источников с известным знаком: delogo по точным границам логотипа
    (интерполяция соседних пикселей) + лёгкое размытие заплатки, чтобы сгладить полосы. Бледная
    диагональная надпись по всему кадру остаётся. Иначе — пусто."""
    if os.environ.get("REEL_DELOGO", "1") == "0":
        return ""
    for key, (x0, y0, x1, y1) in WATERMARKS.items():
        if key in str(src).lower():
            x, y = max(int(w * x0), 1), max(int(h * y0), 1)
            bw, bh = min(int(w * (x1 - x0)), w - x - 2), min(int(h * (y1 - y0)), h - y - 2)
            return (f"delogo=x={x}:y={y}:w={bw}:h={bh},split=2[wm0][wm1];"
                    f"[wm1]crop={bw + 24}:{bh + 24}:{max(x - 12, 0)}:{max(y - 12, 0)},gblur=sigma=9[wmb];"
                    f"[wm0][wmb]overlay={max(x - 12, 0)}:{max(y - 12, 0)},")
    return ""


def photo_clip(img, seg, dest: Path):
    """Фото -> 9:16 ролик с медленным наездом (размытый фон + фото по ширине)."""
    fr = int(seg * 30)
    fc = (f"[0:v]split=2[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:2,eq=brightness=-0.12[bg];"
          f"[b]scale={int(W*1.2)}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-60,"
          f"zoompan=z='1+0.10*on/{fr}':d={fr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,setsar=1[v]")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(img),
                    "-filter_complex", fc, "-map", "[v]", "-frames:v", str(fr), "-an", "-c:v", "libx264",
                    "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)],
                   check=True, timeout=300)
    return dest


def ytdlp(url, dest_dir: Path):
    if not shutil.which("yt-dlp"):
        return None
    tpl = str(dest_dir / "ytdlp.%(ext)s")
    r = subprocess.run(["yt-dlp", "-q", "--no-playlist", "--max-filesize", "80M", "-f", "mp4/best[ext=mp4]/best",
                        "-o", tpl, url], capture_output=True, text=True, timeout=180)
    files = sorted(dest_dir.glob("ytdlp.*"))
    if r.returncode or not files:
        log(f"yt-dlp: нет видео ({url[:70]})")
        return None
    return files[0]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "x"


YT_HINTS = CACHE / "yt-hints.json"


def yt_hint_clip(strike, d: Path, final: Path, seg=SEG):
    """Кадры с YouTube-хроники (agents/yt-watch.py, 10.10.2026): ролик вышел в окне даты удара, город —
    в заголовке/субтитрах. Качаем ~40 с вокруг упоминания, кадр выбирает та же проверка, что для Telegram.
    Без звука (to_vertical -an): голос чужого канала не берём; источник — ссылка на ролик с таймкодом."""
    try:
        hints = json.loads(YT_HINTS.read_text())
    except (OSError, ValueError):
        return None
    st, day = city_stem(strike.get("city")), str(strike.get("date", ""))[:10]
    what = f"{strike.get('target') or ''}, {strike.get('city') or ''}"
    for h in sorted(hints.values(), key=lambda h: h.get("start") is None):
        if not st or h.get("stem") != st or not date_ok(h.get("published"), day):
            continue
        start = int(h.get("start") or 0)
        lo = max(0, start - 3)
        for f in d.glob(f"yt-{h['video']}-{lo}.*"):
            raw = f
            break
        else:
            ytd = shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")   # venv (см. daily.sh)
            if not os.access(ytd, os.X_OK):
                return None
            r = subprocess.run([ytd, "-q", "--no-playlist", "-f", "bv*[height<=720][ext=mp4]/b[height<=720]/best",
                                "--download-sections", f"*{lo}-{lo + 45}", "--force-keyframes-at-cuts",
                                "-o", str(d / f"yt-{h['video']}-{lo}.%(ext)s"), h["url"]],
                               capture_output=True, text=True, timeout=300)
            files = sorted(d.glob(f"yt-{h['video']}-{lo}.*"))
            if r.returncode or not files:
                log(f"youtube {h['url']}: фрагмент не скачался {r.stderr[-150:]!r}")
                continue
            raw = files[0]
        try:
            w, hh, dur = probe(raw)
            # 45 с ролика — три куска по 15 с: pick_window берёт по 3 окна с куска, итого 9 кадров
            # (одно 45-секундное видео давало 3 окна, и в них попадали заставка и чужой сюжет)
            parts = []
            for off in range(0, int(dur) - 3, 15):
                part = d / f"{raw.stem}-p{off}.mp4"
                if not part.exists():
                    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(off), "-t", "15", "-i", str(raw),
                                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(part)],
                                   check=True, timeout=180)
                parts.append((part, probe(part)[2], off))
            pick = pick_window([p for p in parts if p[1] >= seg], seg, what, d)
            if not pick:
                log(f"youtube {h['url']}: в кадрах удара не видно")
                continue
            part, s0, s, off = pick
            to_vertical(part, s0, s, final)
            s0 += off
        except Exception as e:  # noqa: BLE001
            log(f"youtube {h['url']}: не годится ({e})")
            continue
        return {"file": final.name, "kind": "video", "src": f"{h['url']}&t={lo + int(s0)}s", "start": s0,
                "dur": round(s, 2), "orig": f"{w}x{hh}"}
    return None


def fetch_for(strike, out_dir: Path, seg=SEG):
    """-> {"file", "kind": video|photo, "src": url_поста, "start"} или None."""
    key = slug(str(strike.get("source_url") or "") + "-" + str(strike.get("city") or ""))
    d = CACHE / key
    d.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"clip-{key}.mp4"
    meta = d / "pick.json"
    if meta.exists() and final.exists():
        return json.loads(meta.read_text())
    posts = tg_candidates(strike)
    res = None
    # все видео-кандидаты: качество = короткая сторона кадра; «кружки» 384×384 и огрызки <2 с —
    # в конец очереди (фото того же поста смотрится лучше «кружка»)
    vids = []
    for rank, p in enumerate(posts):
        for i, v in enumerate(p["videos"][:3]):
            try:
                raw = download(v, d / f"{slug(p['url'])}-{i}.mp4")
                w, h, dur = probe(raw)
            except Exception as e:  # noqa: BLE001
                log(f"{p['url']}: видео не скачалось ({e})")
                continue
            if dur >= 1.5:
                # сначала годность, потом релевантность поста (порядок после проверки), потом качество
                vids.append((min(w, h) >= 400 and dur >= 2.5, -rank, min(w, h), raw, p, w, h, dur))
    vids.sort(key=lambda x: x[:3], reverse=True)
    has_photo = any(p["photos"] for p in posts)
    good = [(raw, dur, (p, w, h)) for ok, _, _, raw, p, w, h, dur in vids if ok or not has_photo]
    if good:
        what = f"{strike.get('target') or ''}, {strike.get('city') or ''}"
        try:
            pick = pick_window(good, seg, what, d)
            if pick:
                raw, st, s, (p, w, h) = pick
                to_vertical(raw, st, s, final)
                res = {"file": final.name, "kind": "video", "src": p["url"], "start": st, "dur": round(s, 2),
                       "orig": f"{w}x{h}"}
            else:
                vids = []  # модель смотрела кадры — удара не видно; «кружок» в конце тоже не нужен
        except Exception as e:  # noqa: BLE001
            log(f"видео не годится ({e})")
    if not res:
        src = str(strike.get("source_url") or "")
        if src and "t.me/" not in src:   # Telegram — только через пост/поиск выше
            raw = ytdlp(src, d)
            if raw:
                try:
                    w, h, dur = probe(raw)
                    s = min(seg, dur - 0.2)
                    to_vertical(raw, best_window(raw, dur, s), s, final)
                    res = {"file": final.name, "kind": "video", "src": src, "dur": round(s, 2), "orig": f"{w}x{h}"}
                except Exception as e:  # noqa: BLE001
                    log(f"yt-dlp-файл не годится: {e}")
    if not res:   # YouTube-хроника (Ukraine365 и др.) — раньше фото: живые кадры лучше статики
        res = yt_hint_clip(strike, d, final, seg)
    if not res:
        for p in posts:
            if p["photos"]:
                try:
                    img = download(p["photos"][0], d / f"{slug(p['url'])}.jpg")
                    photo_clip(img, 3.0, final)
                    res = {"file": final.name, "kind": "photo", "src": p["url"], "dur": 3.0}
                    break
                except Exception as e:  # noqa: BLE001
                    log(f"{p['url']}: фото не годится ({e})")
    if not res and vids:  # остался только «кружок»/короткое видео — лучше, чем ничего
        _, _, _, raw, p, w, h, dur = vids[0]
        s = min(seg, dur - 0.2)
        to_vertical(raw, best_window(raw, dur, s), s, final)
        res = {"file": final.name, "kind": "video", "src": p["url"], "dur": round(s, 2), "orig": f"{w}x{h}"}
    if res:
        meta.write_text(json.dumps(res, ensure_ascii=False))
        log(f"{strike.get('city')}: {res['kind']} из {res['src']}")
    else:
        log(f"{strike.get('city')}: кадров нет — будет только табличка")
    return res


def day_broll(date, used_src, n=3, seg=3.2, out_dir: Path = None):
    """Кадры дня без привязки к городу: свежие видео-посты каналов за сутки про атаки/пожары,
    не из оккупированных территорий, не повторяющие уже взятые. -> [{"file","src","dur","orig"}]."""
    out_dir = out_dir or CACHE
    cands = []
    for chan in CHANNELS:
        for p in channel_posts(chan):
            if p["videos"] and p["url"] not in used_src and ATTACK_RX.search(p["text"]) \
                    and not OCC_RX.search(p["text"]) and date_ok(p["date"], date):
                cands.append(p)
    res = []
    for p in cands:
        if len(res) >= n:
            break
        d = CACHE / "broll"
        d.mkdir(parents=True, exist_ok=True)
        try:
            raw = download(p["videos"][0], d / f"{slug(p['url'])}.mp4")
            w, h, dur = probe(raw)
            if dur < 2.5 or min(w, h) < 400:
                continue
            sg = min(seg, dur - 0.2)
            final = out_dir / f"broll-{slug(p['url'])}.mp4"
            to_vertical(raw, best_window(raw, dur, sg), sg, final)
            res.append({"file": final.name, "kind": "video", "src": p["url"], "dur": round(sg, 2), "orig": f"{w}x{h}"})
        except Exception as e:  # noqa: BLE001
            log(f"{p['url']}: хроника — видео не годится ({e})")
    log(f"хроника дня: {len(res)} из {len(cands)} кандидатов")
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--url"] and len(a) == 4:
        out = CACHE / "debug"
        out.mkdir(parents=True, exist_ok=True)
        print(json.dumps(fetch_for({"source_url": a[1], "city": a[2], "date": a[3]}, out), ensure_ascii=False))
    elif len(a) == 1:
        sys.path.insert(0, str(REEL))
        from build_reel import select_strikes  # noqa: E402
        out = CACHE / a[0]
        out.mkdir(parents=True, exist_ok=True)
        for s in select_strikes(a[0])[0]:
            print(json.dumps({"city": s.get("city"), "clip": fetch_for(s, out)}, ensure_ascii=False))
    else:
        sys.exit(__doc__)
