#!/usr/bin/env python3
"""Проверка озвучки слухом whisper: расшифровываем готовые mp3 и сверяем с текстом, который подавали в голос.

Ловит заменённые/проглоченные слова и «слова, прочитанные как другие» (Озон -> Азон). Ударение на гласной не видит.
Ничего не блокирует: пишет отчёт video/out/voice-check/<kind>-<date>.json и копит счётчик подозрительных слов в
video/reel/voice-lexicon.json (поле suspects). Исправления произношения живут в поле fix и применяются в speakable().

  voice_check.py run <метка> <items.json>   (из build_reel; запускать python-ом из /root/voice-venv)
  python3 voice_check.py fix "слово" "как произнести"                            (добавить исправление навсегда)
  python3 voice_check.py report                                                  (топ подозрительных слов)

Модель — faster-whisper small (int8) из venv /root/voice-venv; нет модели — молча пропускаем.
"""
import difflib, json, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LEX = HERE / "voice-lexicon.json"
OUT = ROOT / "video" / "out" / "voice-check"
MODEL_DIR = "/root/.cache/fw"
VENV_SITE = "/root/voice-venv/lib"
KEEP_DAYS = 14


def load_lex():
    try:
        d = json.loads(LEX.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("fix", {})        # {слово: как произнести}, применяется навсегда
    d.setdefault("suspects", {})   # {слово: {n: сколько раз, heard: {как услышано: раз}}}
    return d


def save_lex(d):
    LEX.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def apply_fixes(text):
    """Вызывается из speakable(): подставляет выученные произношения."""
    for w, say in load_lex()["fix"].items():
        text = re.sub(r"\b" + re.escape(w) + r"\b", say, text, flags=re.I)
    return text


def norm_words(t):
    t = re.sub(r"[^\w\s-]", " ", str(t).lower().replace("ё", "е"))
    return [w for w in t.split() if not w.isdigit()]


def _model():
    import glob
    for p in glob.glob(VENV_SITE + "/python3*/site-packages"):
        if p not in sys.path:
            sys.path.insert(0, p)
    from faster_whisper import WhisperModel
    return WhisperModel("small", device="cpu", compute_type="int8", download_root=MODEL_DIR, cpu_threads=2)


def heard(model, mp3):
    segs, _ = model.transcribe(str(mp3), language="ru", beam_size=1, word_timestamps=True, vad_filter=False)
    words = []
    for s in segs:
        for w in (s.words or []):
            words.append((w.word, w.probability))
    return words


def check(items, label):
    """items: [(ожидаемый текст, путь к mp3)]. Возвращает отчёт; ошибки не пробрасывает."""
    t0 = time.time()
    try:
        model = _model()
    except Exception as e:
        return {"skipped": f"whisper недоступен: {e}"}
    lex = load_lex()
    rep = {"label": label, "lines": [], "bad_words": 0, "total_words": 0}
    for text, mp3 in items:
        try:
            hw = heard(model, mp3)
        except Exception as e:
            rep["lines"].append({"text": text, "error": str(e)[:120]})
            continue
        exp = norm_words(text)
        got = [norm_words(w)[0] for w, _ in hw if norm_words(w)]
        prob = {i: p for i, (w, p) in enumerate([(w, p) for w, p in hw if norm_words(w)])}
        sm = difflib.SequenceMatcher(None, exp, got, autojunk=False)
        bad, weak = [], []
        for op, a0, a1, b0, b1 in sm.get_opcodes():
            if op == "equal":
                weak += [exp[a0 + k] for k in range(a1 - a0) if prob.get(b0 + k, 1) < 0.5]
            elif a1 > a0:
                for w in exp[a0:a1]:
                    bad.append({"expected": w, "heard": " ".join(got[b0:b1])})
        for b in bad:
            s = lex["suspects"].setdefault(b["expected"], {"n": 0, "heard": {}})
            s["n"] += 1
            s["heard"][b["heard"]] = s["heard"].get(b["heard"], 0) + 1
        rep["bad_words"] += len(bad)
        rep["total_words"] += len(exp)
        rep["lines"].append({"text": text, "bad": bad, "weak": weak})
    rep["share"] = round(rep["bad_words"] / max(1, rep["total_words"]), 3)
    rep["seconds"] = round(time.time() - t0, 1)
    save_lex(lex)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{label}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for f in OUT.glob("*.json"):
        if time.time() - f.stat().st_mtime > KEEP_DAYS * 86400:
            f.unlink()
    return rep


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["fix"] and len(a) == 3:
        d = load_lex(); d["fix"][a[1].lower()] = a[2]; d["suspects"].pop(a[1].lower(), None); save_lex(d); print("ok")
    elif a[:1] == ["run"] and len(a) == 3:   # run <метка> <items.json: [[текст, mp3], ...]>
        r = check(json.loads(Path(a[2]).read_text(encoding="utf-8")), a[1])
        print(json.dumps({k: r.get(k) for k in ("skipped", "bad_words", "total_words", "share", "seconds")}, ensure_ascii=False))
    elif a[:1] == ["report"]:
        for w, s in sorted(load_lex()["suspects"].items(), key=lambda x: -x[1]["n"])[:30]:
            print(s["n"], w, s["heard"])
    else:
        print(__doc__)
