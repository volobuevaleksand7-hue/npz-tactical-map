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
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date as _date, timedelta
from pathlib import Path

REEL = Path(__file__).resolve().parent
CACHE = REEL / "cache"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
SEG = 4.0          # длина отрезка, с
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


def _text(block):
    m = re.search(r'js-message_text[^>]*>(.*?)</div>', block, re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""


def _media(block):
    vids = re.findall(r'<video[^>]*src="([^"]+)"', block)
    photos = re.findall(r"message_photo_wrap[^>]*background-image:url\('([^']+)'\)", block)
    when = (re.findall(r'datetime="([^"]+)"', block) or [""])[0][:10]
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
    if not when:
        return True
    d0 = _date.fromisoformat(day)
    return when in {(d0 + timedelta(days=k)).isoformat() for k in (-1, 0, 1)}


def tg_candidates(strike):
    """Посты с медиа по удару: сам пост, затем соседние/поиск с городом и датой."""
    src = str(strike.get("source_url") or "")
    m = TG_RX.match(src)
    if not m:
        return []
    chan, pid = m.group(1), int(m.group(2))
    stem, day = city_stem(strike.get("city")), str(strike.get("date"))[:10]
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


def best_window(path, dur, seg=SEG):
    """Начало самого «живого» отрезка: максимум движения (YDIF) + немного яркости (огонь/вспышки).
    Первые 0,3 с пропускаем (часто чёрный кадр/заставка)."""
    if dur <= seg + 0.4:
        return 0.0
    rows = activity(path)
    if len(rows) < 4:
        return max(0.0, (dur - seg) / 2)
    best, best_t = -1, 0.3
    t = 0.3
    while t + seg <= dur - 0.1:
        win = [r for r in rows if t <= r["t"] < t + seg]
        if win:
            ydif = sum(r.get("YDIF", 0) for r in win) / len(win)
            yavg = sum(r.get("YAVG", 0) for r in win) / len(win)
            dark_pen = 8 if yavg < 18 else 0  # почти чёрный — не берём
            score = ydif + 0.04 * yavg - dark_pen
            if score > best:
                best, best_t = score, t
        t += 0.25
    return round(best_t, 2)


def to_vertical(src, start, seg, dest: Path):
    """9:16 без звука: горизонталь — увеличенный центр поверх размытого фона (кадр заполнен),
    вертикаль — cover-кроп. Края с логотипами каналов частично срезаются."""
    w, h, _ = probe(src)
    if h >= w * 1.4:   # вертикальное видео
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
        fc = None
    else:
        fg_w = int(W * 1.5) // 2 * 2  # чуть больше ширины кадра — режем края (там часто логотипы)
        fc = (f"[0:v]split=2[a][b];"
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
    for p in posts:
        for i, v in enumerate(p["videos"][:3]):
            try:
                raw = download(v, d / f"{slug(p['url'])}-{i}.mp4")
                w, h, dur = probe(raw)
            except Exception as e:  # noqa: BLE001
                log(f"{p['url']}: видео не скачалось ({e})")
                continue
            if dur >= 1.5:
                vids.append((min(w, h) >= 400 and dur >= 2.5, min(w, h), -len(vids), raw, p, w, h, dur))
    vids.sort(key=lambda x: x[:3], reverse=True)
    has_photo = any(p["photos"] for p in posts)
    for good, _, _, raw, p, w, h, dur in vids:
        if not good and has_photo:
            break
        try:
            s = min(seg, dur - 0.2)
            st = best_window(raw, dur, s)
            to_vertical(raw, st, s, final)
            res = {"file": final.name, "kind": "video", "src": p["url"], "start": st, "dur": round(s, 2),
                   "orig": f"{w}x{h}"}
            break
        except Exception as e:  # noqa: BLE001
            log(f"{p['url']}: видео не годится ({e})")
    if not res:
        src = str(strike.get("source_url") or "")
        if src and not TG_RX.match(src):
            raw = ytdlp(src, d)
            if raw:
                try:
                    w, h, dur = probe(raw)
                    s = min(seg, dur - 0.2)
                    to_vertical(raw, best_window(raw, dur, s), s, final)
                    res = {"file": final.name, "kind": "video", "src": src, "dur": round(s, 2), "orig": f"{w}x{h}"}
                except Exception as e:  # noqa: BLE001
                    log(f"yt-dlp-файл не годится: {e}")
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
