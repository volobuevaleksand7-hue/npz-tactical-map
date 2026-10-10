#!/usr/bin/env python3
"""Загрузка ежедневного ролика на YouTube (YouTube Data API v3), только stdlib.

  python3 upload.py auth            — разовая авторизация (refresh-токен -> .secrets/token.json)
  python3 upload.py [YYYY-MM-DD]    — залить out/npz-<дата>.mp4 (без даты — все незалитые)
  python3 upload.py reel [YYYY-MM-DD] — то же для рилса out/reel-<дата>.mp4 (reel/render_reel.sh)
  python3 upload.py urgent YYYY-MM-DD — срочный рилс out/urgent-<дата>.mp4
  NPZ_YT_SECRETS=~/.config/npz-youtube-en python3 upload.py en-reel YYYY-MM-DD — английский канал

Секреты лежат вне репозитория, в ~/.config/npz-youtube/ (или $NPZ_YT_SECRETS), права 600:
  client_secret.json — OAuth-клиент «Desktop» из Google Cloud (проект npz-youtube);
  token.json         — refresh-токен, пишет `auth`.

Авторизация на сервере без браузера — через проброс порта с Мака:
  ssh -L 8765:127.0.0.1:8765 hermes-vps 'cd /root/npz-tactical-map/video && python3 upload.py auth'
ссылку из вывода открыть в браузере под аккаунтом канала, «Дополнительно → Перейти → Разрешить».

После успешной загрузки пишется маркер out/npz-<дата>.uploaded (id и ссылка) —
по нему cleanup.sh удаляет mp4, а повторный запуск дату пропускает.
Переменные: YT_PRIVACY (public|unlisted|private, по умолчанию public).
"""
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VIDEO = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(VIDEO, "out")
SECRETS = os.environ.get("NPZ_YT_SECRETS", os.path.expanduser("~/.config/npz-youtube"))
CLIENT = os.path.join(SECRETS, "client_secret.json")
TOKEN = os.path.join(SECRETS, "token.json")
# Англоязычный канал (Fuel Front, @NPZ-eng) — свой каталог секретов NPZ_YT_SECRETS=~/.config/npz-youtube-en
# и шире scope (NPZ_YT_SCOPE): с правом управления роликами, чтобы скрывать дубли без Studio.
SCOPE = os.environ.get("NPZ_YT_SCOPE", "https://www.googleapis.com/auth/youtube.upload")
PORT = int(os.environ.get("NPZ_YT_PORT", "8765"))  # второй порт — чтобы две авторизации ждали параллельно
VIDEOS_JSON = os.path.join(os.path.dirname(VIDEO), "data", "videos.json")  # реестр для сайта (gen-news.py)
KIND = "npz"  # префикс файлов в out/: npz (ежедневный ролик) | reel (рилс) | urgent (срочный рилс); en-* — английские
CATEGORY_NEWS = "25"  # News & Politics


def log(msg):
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] upload: {msg}", flush=True)


def client():
    with open(CLIENT) as f:
        data = json.load(f)
    return data.get("installed") or data["web"]


def write_private(path, obj):
    os.makedirs(SECRETS, mode=0o700, exist_ok=True)
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f)
    os.replace(path + ".tmp", path)


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload: {url} -> HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")


def auth():
    c = client()
    redirect = f"http://127.0.0.1:{PORT}"
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = c["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" not in q and "error" not in q:
                self.send_response(404); self.end_headers(); return
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Готово, окно можно закрыть.".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    print("Открой ссылку в браузере под аккаунтом канала:\n\n" + url + "\n", flush=True)
    while not got:
        srv.handle_request()
    if got.get("state") != state or "code" not in got:
        raise SystemExit(f"upload: авторизация не прошла: {got.get('error', 'state mismatch')}")
    tok = post_form(c["token_uri"], {
        "code": got["code"], "client_id": c["client_id"], "client_secret": c["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier,
    })
    if "refresh_token" not in tok:
        raise SystemExit("upload: Google не вернул refresh_token")
    write_private(TOKEN, {"refresh_token": tok["refresh_token"], "scope": tok.get("scope")})
    log(f"refresh-токен сохранён в {TOKEN}")


def access_token():
    c = client()
    with open(TOKEN) as f:
        rt = json.load(f)["refresh_token"]
    return post_form(c["token_uri"], {
        "client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": rt, "grant_type": "refresh_token",
    })["access_token"]


PHRASES = {
    "ru": ["удар по НПЗ", "атака беспилотников", "атака дронов", "Топливный фронт", "НПЗ России",
           "нефтебаза", "бензин", "OSINT"],
    "en": ["Russia refinery strike", "drone attack", "oil refinery", "Fuel Front", "Russian oil",
           "Ukraine drones", "OSINT"],
}


def video_tags(title, desc):
    """Скрытые теги ролика (snippet.tags, 10.10.2026). Раньше — только 3 хэштега описания. Теперь:
    хэштеги из заголовка и описания, поисковые фразы и города из строк «— Город: …».
    Вес в выдаче у тегов малый (YouTube: помогают с опечатками), основное — заголовок и описание;
    лимит API — 500 символов на все теги вместе."""
    tags = re.findall(r"#(\w+)", title + "\n" + desc)
    tags += PHRASES[lang()]
    for m in re.finditer(r"^—\s*(?!http)([^:\n]{2,40}):", desc, re.M):
        tags += [c.strip() for c in re.split(r",| and | и ", m.group(1)) if c.strip() and "http" not in c]
    out, size = [], 0
    for t in tags:
        if t.lower() in (x.lower() for x in out):
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if size + cost > 480:
            break
        out.append(t)
        size += cost
    return out


def meta(date):
    """Заголовок — первая строка out/npz-<дата>.txt, описание — остальное."""
    path = os.path.join(OUT, f"{KIND}-{date}.txt")
    with open(path, encoding="utf-8") as f:
        lines = f.read().strip().split("\n")
    clean = lambda s: s.replace("<", "‹").replace(">", "›")
    title = clean(lines[0].strip())[:100]
    desc = clean("\n".join(lines[1:]).strip())[:4900]
    tags = video_tags(title, desc)
    if lang() == "en" and re.search(r"[А-Яа-яЁё]", title + desc):
        raise SystemExit(f"upload: {path}: кириллица в заголовке/описании английского ролика — сначала reel/en_pass.py")
    return title, desc, tags


def upload(date, token):
    mp4 = os.path.join(OUT, f"{KIND}-{date}.mp4")
    size = os.path.getsize(mp4)
    title, desc, tags = meta(date)
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags,
                    "categoryId": CATEGORY_NEWS, "defaultLanguage": lang(), "defaultAudioLanguage": lang()},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"),
                   "selfDeclaredMadeForKids": False, "embeddable": True},
    }
    req = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            session = r.headers["Location"]
        with open(mp4, "rb") as f:
            put = urllib.request.Request(session, data=f.read(), method="PUT",
                                         headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
        with urllib.request.urlopen(put, timeout=600) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload: {date}: HTTP {e.code}: {e.read().decode(errors='replace')[:800]}")
    vid = res["id"]
    set_thumbnail(date, vid, token)
    privacy = res.get("status", {}).get("privacyStatus")
    url = f"https://youtu.be/{vid}"
    with open(os.path.join(OUT, f"{KIND}-{date}.uploaded"), "w") as f:
        f.write(f"{vid}\t{url}\t{privacy}\t{title}\n")
    log(f"{date}: залит {url} ({privacy})")
    if KIND in ("weekly", "en-weekly"):
        add_to_playlist(vid, token)
    if privacy == "public" and lang() == "ru":  # реестр сайта — только русский канал
        register(date, vid, title)
    return url


PLAYLIST_TITLES = {"weekly": "Неделя ударов", "en-weekly": "Weekly strike review"}


def add_to_playlist(vid, token):
    """Недельный обзор -> плейлист «Неделя ударов» / «Weekly strike review» (создаётся при первом обзоре).
    Нужен scope youtube (RU-токен с youtube.upload получит 403): ошибка не фатальна, ролик уже залит,
    а плейлист можно собрать вручную в Studio или после upload.py auth с NPZ_YT_SCOPE=https://www.googleapis.com/auth/youtube."""
    title = PLAYLIST_TITLES[KIND]
    cache = os.path.join(OUT, f"playlist-{KIND}.id")
    try:
        pid = open(cache).read().strip() if os.path.exists(cache) else ""
        if not pid:
            for it in api("GET", "playlists?part=snippet&mine=true&maxResults=50", token=token).get("items", []):
                if it["snippet"]["title"] == title:
                    pid = it["id"]
            if not pid:
                pid = api("POST", "playlists?part=snippet,status",
                          {"snippet": {"title": title, "defaultLanguage": lang()},
                           "status": {"privacyStatus": "public"}}, token=token)["id"]
            with open(cache, "w") as f:
                f.write(pid)
        api("POST", "playlistItems?part=snippet",
            {"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": vid}}}, token=token)
        log(f"{vid}: добавлен в плейлист «{title}»")
    except (SystemExit, OSError, KeyError) as e:
        log(f"{vid}: плейлист «{title}» не обновлён (не фатально): {e}")


def lang():
    return "en" if KIND.startswith("en-") else "ru"


def register(date, vid, title):
    """data/videos.json: {"videos": {дата: {"npz"|"reel": {"id", "title"}}}} — страница сводки
    /news/<дата>.html показывает по нему ссылки на ролики. Коммитит daily.sh через git-sync."""
    try:
        with open(VIDEOS_JSON, encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError):
        reg = {"videos": {}}
    reg.setdefault("videos", {}).setdefault(date, {})[KIND] = {"id": vid, "title": title}
    with open(VIDEOS_JSON + ".tmp", "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(VIDEOS_JSON + ".tmp", VIDEOS_JSON)


def set_thumbnail(date, vid, token):
    """Обложка = кадр-постер out/npz-<дата>.jpg. Не вышло (канал без права на свои обложки,
    нет файла) — ролик всё равно залит, YouTube возьмёт кадр сам."""
    jpg = os.path.join(OUT, f"{KIND}-{date}.jpg")
    if not os.path.exists(jpg):
        return
    with open(jpg, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
        data=data, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"})
    try:
        with urllib.request.urlopen(req, timeout=120):
            log(f"{date}: обложка поставлена")
    except urllib.error.HTTPError as e:
        log(f"{date}: обложка не поставлена: HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")


def api(method, path, body=None, token=None):
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token or access_token()}",
                                          "Content-Type": "application/json; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload: {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")


def whoami():
    """Какой канал за токеном — проверять перед правками (нужен scope youtube)."""
    for c in api("GET", "channels?part=snippet&mine=true").get("items", []):
        print(c["id"], c["snippet"]["title"], c["snippet"].get("customUrl", ""))


def privacy(vid, status):
    """Скрыть дубль: upload.py privacy <id> unlisted|private|public (scope youtube, не youtube.upload)."""
    tok = access_token()
    items = api("GET", f"videos?part=status&id={vid}", token=tok).get("items", [])
    if not items:
        raise SystemExit(f"upload: {vid} не найден на канале токена")
    st = items[0]["status"]
    st["privacyStatus"] = status
    st.pop("publishAt", None)
    res = api("PUT", "videos?part=status", {"id": vid, "status": st}, token=tok)
    log(f"{vid}: {res['status']['privacyStatus']}")


def main():
    global KIND
    args = sys.argv[1:]
    if args[:1] == ["auth"]:
        return auth()
    if args[:1] == ["whoami"]:
        return whoami()
    if args[:1] == ["privacy"] and len(args) == 3 and args[2] in ("unlisted", "private", "public"):
        return privacy(args[1], args[2])
    # urgent-<метка> — второй срочный за дату; reel-evening — вечерняя сводка; weekly — недельный обзор 16:9 (дата = последний день недели); en-* — англоязычный канал
    if re.fullmatch(r"(en-)?(reel(-evening)?|weekly|urgent(-[a-z0-9]+)?)", args[0] if args else ""):
        KIND, args = args[0], args[1:]
    if args:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[0]):
            raise SystemExit("upload: дата YYYY-MM-DD или 'auth'")
        dates = [args[0]]
    else:
        dates = sorted(m.group(1) for n in os.listdir(OUT)
                       if (m := re.fullmatch(KIND + r"-(\d{4}-\d{2}-\d{2})\.mp4", n)))
    dates = [d for d in dates if not os.path.exists(os.path.join(OUT, f"{KIND}-{d}.uploaded"))]
    if not dates:
        return log("нечего заливать")
    token = access_token()
    for d in dates[-3:]:  # квота API ~6 загрузок в сутки — хвост накопившегося не тащим разом
        upload(d, token)


if __name__ == "__main__":
    main()
