"""Каскад озвучки роликов (10.10.2026).

Причина: с IP сервера Microsoft массово отдаёт NoAudioReceived для DmitryNeural, ретраи по ~4 мин на фразу
не помогали, аудит валил ролик («озвучено 0 из N реплик») и вечерний ролик 10.10 не вышел.

Порядок (ru/en): edge (основной голос) -> gemini (Gemini TTS, REST) -> edge2 (запасной голос edge-tts)
               -> piper (офлайн, /root/tts-models, работает без сети).
Внутри одного ролика голоса не смешиваем: если провайдер упал на любой фразе, ВЕСЬ ролик переозвучивается
следующим (фразы, уже лежащие в кэше этого провайдера, берутся с диска). Кэш: video/reel/cache/tts/,
ключ основного голоса прежний md5("{voice}|{rate}|{text}"); у остальных провайдеров провайдер в ключе.

Тест без боевого отказа: REEL_TTS_SKIP=edge,gemini (ids: edge, gemini, edge2, piper) — провайдер считается упавшим.
Ключ Gemini: env GEMINI_API_KEY, иначе строка из video/.env (и из основного дерева /root/npz-tactical-map/video/.env,
если код запущен из git worktree) или ~/.npz-agent.env. В лог ключ не пишется.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REEL = Path(__file__).resolve().parent
VIDEO = REEL.parent
CACHE = REEL / "cache" / "tts"
PIPER_DIR = Path(os.environ.get("REEL_PIPER_DIR", "/root/tts-models"))

# голоса запасных провайдеров по языкам
FALLBACK = {
    "ru": {"edge2": "ru-RU-SvetlanaNeural", "gemini": "Orus", "piper": "ru_RU-dmitri-medium",
           "gem_lang": "Russian", "gem_tempo": 1.15, "piper_len": 0.8},
    "en": {"edge2": "en-US-AndrewNeural", "gemini": "Orus", "piper": "en_US-ryan-medium",
           "gem_lang": "English", "gem_tempo": 1.05, "piper_len": 0.9},
}
# Gemini TTS: сначала актуальные 3.8 (Interactions API), потом старый generateContent
GEMINI_MODELS = [("interactions", "gemini-3.8-flash-tts"),
                 ("interactions", "gemini-3.8-flash-lite-tts"),
                 ("generate", "gemini-2.5-flash-preview-tts")]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def log(msg):
    print(f"tts: {msg}", file=sys.stderr, flush=True)


def _duration(p):
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True).stdout.strip()
    try:
        return float(d)
    except ValueError:
        return None


def _ok(p):
    return p.exists() and p.stat().st_size > 1000


def _gemini_key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    for f in (VIDEO / ".env", Path("/root/npz-tactical-map/video/.env"), Path.home() / ".npz-agent.env"):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*(?:export\s+)?GEMINI_API_KEY\s*=\s*(.*)", line)
                if m and m.group(1).strip().strip("\"'"):
                    return m.group(1).strip().strip("\"'")
        except OSError:
            pass
    return ""


# ───────────── провайдеры: каждый пишет mp3 в out, True/False ─────────────

def _edge(voice, rate, text, out):
    # 10.10: ретраи сокращены с ~4 мин до ~30 с на фразу — дальше работает каскад, а не ожидание
    exe = shutil.which("edge-tts") or str(Path.home() / ".local/bin/edge-tts")
    if not Path(exe).exists():
        return False
    for attempt, pause in enumerate((0, 3, 8)):
        if attempt:
            time.sleep(pause)
        out.unlink(missing_ok=True)
        try:
            subprocess.run([exe, "--voice", voice, f"--rate={rate}", "--text", text, "--write-media", str(out)],
                           capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            continue
        if _ok(out):
            return True
    return False


def _pcm_to_mp3(raw, out, tempo):
    # Gemini отдаёт wav (RIFF) либо сырой PCM s16le 24 кГц моно
    src = out.with_suffix(".gem.in")
    src.write_bytes(raw)
    fmt = [] if raw[:4] == b"RIFF" else ["-f", "s16le", "-ar", "24000", "-ac", "1"]
    af = f"atempo={tempo}" if abs(tempo - 1.0) > 0.01 else "anull"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *fmt, "-i", str(src), "-af", af, "-ac", "1", "-ar", "24000",
                        "-c:a", "libmp3lame", "-b:a", "64k", str(out)], capture_output=True)
    src.unlink(missing_ok=True)
    return r.returncode == 0 and _ok(out)


def _post(url, body, key):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def _find_audio(o):
    """Достаёт base64-аудио из ответа (Interactions: steps[].content[].data; generateContent: inlineData.data)."""
    if isinstance(o, dict):
        if o.get("type") == "audio" and isinstance(o.get("data"), str):
            return o["data"]
        if isinstance(o.get("inlineData"), dict) and o["inlineData"].get("data"):
            return o["inlineData"]["data"]
        if isinstance(o.get("output_audio"), dict) and o["output_audio"].get("data"):
            return o["output_audio"]["data"]
        for v in o.values():
            r = _find_audio(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_audio(v)
            if r:
                return r
    return None


def _gemini(lang, text, out):
    key = _gemini_key()
    if not key:
        log("gemini: нет GEMINI_API_KEY (env / video/.env / ~/.npz-agent.env)")
        return False
    cfg = FALLBACK[lang]
    style = (f"Read in {cfg['gem_lang']} as a calm, confident news announcer, "
             "slightly faster than normal pace, no extra words")
    for kind, model in GEMINI_MODELS:
        for attempt in range(2):
            try:
                if kind == "interactions":
                    resp = _post(f"{GEMINI_BASE}/interactions", {
                        "model": model,
                        "input": [{"type": "user_input", "content": [{
                            "type": "text", "text": text,
                            "annotations": [{"type": "speech_metadata", "style": style}]}]}],
                        "response_format": {"type": "audio"},
                        "generation_config": {"speech_config": [{"voice": cfg["gemini"]}]}}, key)
                else:
                    resp = _post(f"{GEMINI_BASE}/models/{model}:generateContent", {
                        "contents": [{"parts": [{"text": f"{style}: {text}"}]}],
                        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": cfg["gemini"]}}}}}, key)
                b64 = _find_audio(resp)
                if b64 and _pcm_to_mp3(base64.b64decode(b64), out, cfg["gem_tempo"]):
                    return True
                log(f"gemini {model}: ответ без аудио")
                break
            except urllib.error.HTTPError as e:
                log(f"gemini {model}: HTTP {e.code}")
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(4)
                    continue
                break   # 400/403/404 — пробуем следующую модель
            except Exception as e:   # сеть, таймаут, не-JSON
                log(f"gemini {model}: {type(e).__name__}")
                if attempt == 0:
                    time.sleep(2)
                    continue
                break
    return False


def _piper(lang, text, out):
    cfg = FALLBACK[lang]
    model = PIPER_DIR / f"{cfg['piper']}.onnx"
    py = PIPER_DIR / "venv" / "bin" / "python"
    if not (model.exists() and py.exists()):
        log("piper: не установлен (/root/tts-models)")
        return False
    wav = out.with_suffix(".piper.wav")
    try:
        subprocess.run([str(py), "-m", "piper", "-m", str(model), "--length-scale", str(cfg["piper_len"]),
                        "--output_file", str(wav)], input=text.encode(), capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False
    if not _ok(wav):
        return False
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "24000",
                        "-c:a", "libmp3lame", "-b:a", "64k", str(out)], capture_output=True)
    wav.unlink(missing_ok=True)
    return r.returncode == 0 and _ok(out)


# ───────────── каскад ─────────────

def _chain(lang, voice, rate):
    cfg = FALLBACK[lang]
    # (id, ярлык для лога, ключ кэша, функция синтеза(text,out))
    # edge/edge2 — прежний формат ключа "{voice}|{rate}|{text}", чтобы не терять накопленный кэш
    return [
        ("edge", f"edge-tts {voice}", lambda t: f"{voice}|{rate}|{t}", lambda t, o: _edge(voice, rate, t, o)),
        ("gemini", "gemini", lambda t: f"gemini|{cfg['gemini']}|{cfg['gem_tempo']}|{t}",
         lambda t, o: _gemini(lang, t, o)),
        ("edge2", f"edge-tts {cfg['edge2']}", lambda t: f"{cfg['edge2']}|{rate}|{t}",
         lambda t, o: _edge(cfg["edge2"], rate, t, o)),
        ("piper", "piper (офлайн)", lambda t: f"piper|{cfg['piper']}|{cfg['piper_len']}|{t}",
         lambda t, o: _piper(lang, t, o)),
    ]


def synth_all(items, lang, voice, rate):
    """items: [(text, out_path)]. Озвучивает ВСЕ реплики одним провайдером.
    Возвращает (провайдер, [длительности]) либо (None, None), если не вышло ни у кого."""
    skip = {x for x in os.environ.get("REEL_TTS_SKIP", "").split(",") if x}
    failed = []
    for pid, label, keyf, fn in _chain(lang, voice, rate):
        if pid in skip:
            log(f"{label}: пропуск по REEL_TTS_SKIP (тест отказа)")
            failed.append(label)
            continue
        durs, bad = [], None
        for text, out in items:
            cached = CACHE / (hashlib.md5(keyf(text).encode()).hexdigest() + ".mp3")
            if _ok(cached):
                shutil.copy2(cached, out)
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                if not fn(text, out):
                    bad = text
                    break
                CACHE.mkdir(parents=True, exist_ok=True)
                tmp = cached.with_suffix(f".{os.getpid()}.tmp")
                shutil.copy2(out, tmp)
                os.replace(tmp, cached)   # атомарно: параллельная сборка не увидит полфайла
            d = _duration(out)
            if not d:
                bad = text
                break
            durs.append(d)
        if bad is None:
            note = f" ({', '.join(failed)} недоступен)" if failed else ""
            log(f"build_reel: голос — {label}{note}")
            return pid, durs
        log(f"{label}: сбой на фразе {bad[:40]!r} — переозвучиваю ролик следующим провайдером")
        failed.append(label)
    log("ВСЕ провайдеры озвучки недоступны — ролик без голоса")
    return None, None
