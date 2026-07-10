#!/usr/bin/env python3
"""Генерация обложки сводки через OpenRouter (альтернатива Codex image_gen, который «out of credits»,
и Gemini image, у которого free-tier квота = 0).

OpenRouter платный → обходит обнулённые free-tier квоты. Модель по умолчанию — image-out
google/gemini-2.5-flash-image (nano-banana) через OpenRouter (можно сменить --model).

Ключ (в порядке приоритета): env OPENROUTER_API_KEY → ~/.openrouter/api_key.

  python3 gen-cover-openrouter.py --date 2026-07-09 --city "Тверь" --event "удар по нефтебазе" \
      --out /path/assets/cover-2026-07-09.png
  # img2img по референсу (сохранить композицию, но переосветлить в дневную палитру):
  python3 gen-cover-openrouter.py ... --ref /path/old-cover.png
  # без подписи (сырой файл): --no-caption

Пайплайн: OpenRouter → сырой PNG → caption_cover.py (амбер-кикер + город + событие + дата).
"""
import sys, os, json, base64, pathlib, subprocess, argparse, urllib.request, datetime

HERE = pathlib.Path(__file__).resolve().parent
CAPTION = HERE.parent.parent  # .../skills/npz-map-refresh ; caption ищем в repo agents/
API = "https://openrouter.ai/api/v1/chat/completions"
RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def rus_date(iso):
    # полную дату С ГОДОМ: caption_cover.py печатает date_rus как есть (единый контракт callers)
    y, m, d = map(int, iso.split("-"))
    return f"{d} {RU_MONTHS[m - 1]} {y}"


def load_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k.strip()
    f = pathlib.Path.home() / ".openrouter" / "api_key"
    if f.exists():
        return f.read_text().strip()
    sys.exit("НЕТ ключа OpenRouter: положи в ~/.openrouter/api_key или env OPENROUTER_API_KEY")


def build_prompt(city, event):
    scene = "на дальнем плане столб дыма над промышленным объектом" if event else "городская панорама"
    if "нпз" in event.lower() or "нефтеб" in event.lower() or "завод" in event.lower():
        scene = "на дальнем плане нефтеперерабатывающий завод/нефтебаза, лёгкий дым на горизонте"
    return (f"Photorealistic daytime documentary news photograph of the city of {city}, Russia. {scene}. "
            f"Bright clear daylight or golden hour, calm photojournalistic style, wide city skyline, "
            f"16:9 horizontal composition. NOT dark, NOT night, NOT dramatic fire. NO text, NO letters, NO logos.")


def openrouter_image(key, prompt, model, ref_path=None):
    content = [{"type": "text", "text": prompt}]
    if ref_path and pathlib.Path(ref_path).exists():
        b = base64.b64encode(pathlib.Path(ref_path).read_bytes()).decode()
        content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}})
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://npz-tactical-map.vercel.app",
        "X-Title": "npz-tactical-map covers",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    msg = d["choices"][0]["message"]
    imgs = msg.get("images") or []
    if not imgs:
        # некоторые модели кладут data-URI в content
        raise RuntimeError("нет image в ответе OpenRouter: " + json.dumps(d)[:300])
    url = imgs[0]["image_url"]["url"]
    b64 = url.split(",", 1)[1]
    return base64.b64decode(b64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--city", required=True)
    ap.add_argument("--event", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", default=None)
    ap.add_argument("--model", default="google/gemini-2.5-flash-image")
    ap.add_argument("--no-caption", action="store_true")
    a = ap.parse_args()

    key = load_key()
    prompt = build_prompt(a.city, a.event)
    print(f"[openrouter] {a.model} → {a.city} / {a.event}")
    raw = openrouter_image(key, prompt, a.model, a.ref)
    out = pathlib.Path(a.out)
    tmp = out.with_suffix(".raw.png")
    tmp.write_bytes(raw)
    print(f"[openrouter] сырой: {tmp} ({len(raw)} bytes)")

    if a.no_caption:
        tmp.replace(out)
    else:
        cap = None
        for c in (CAPTION / "agents" / "caption_cover.py",
                  pathlib.Path.home() / "Documents/npz-tactical-map/agents/caption_cover.py",
                  pathlib.Path("/root/npz-tactical-map/agents/caption_cover.py")):  # VPS repo path
            if c.exists():
                cap = c; break
        if not cap:
            sys.exit("caption_cover.py не найден — используй --no-caption или укажи repo")
        subprocess.run([sys.executable, str(cap), str(tmp), str(out),
                        a.city, a.event or "сводка", rus_date(a.date)], check=True)
        tmp.unlink(missing_ok=True)
    print(f"✅ обложка: {out}")


if __name__ == "__main__":
    main()
