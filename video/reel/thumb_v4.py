#!/usr/bin/env python3
"""Обложка YouTube/Shorts V4 (утверждено Сергеем 23.10.2026, «берем!»): жёлтая шапка с сигнальной лентой,
КРАСНЫЕ буквы с чёрной обводкой, всегда «СРОЧНО» + число ударов, карта сайта крупно и светло, плашка места.

  render(params, build_dir) -> html     # статичная страница-композиция HyperFrames 1080x1920
  params = {"count": "3 УДАРА", "obj": "ПО НПЗ", "place": [["САЛАВАТ", "y"], ["БАШКОРТОСТАН", "w"]],
            "date": "22 ОКТЯБРЯ 2026 · ЗА СУТКИ", "urgent": "СРОЧНО", "brand": "ТОПЛИВНЫЙ ФРОНТ РФ",
            "disc": "ОЦЕНКА · OSINT", "pts": [[x, y], ...]}   # pts — координаты ударов на assets/map.jpg (3240x5760), главный первым

Все размеры текста считаются здесь по метрикам Rubik-800 (PIL), а не скриптом на странице: снимок не зависит от
порядка загрузки шрифтов, а английская версия (en_pass.py) перерисовывается тем же кодом с переведёнными строками.
"""
import html
import json
from pathlib import Path

MW, MH = 3240, 5760          # размер assets/map.jpg
W, H = 1080, 1920
PLATE_Y = 1390
_FONT_CACHE = {}


def _width(font_path, text, size=100):
    from PIL import ImageFont
    f = _FONT_CACHE.get((font_path, size)) or _FONT_CACHE.setdefault((font_path, size), ImageFont.truetype(str(font_path), size))
    return f.getlength(text)


def fit(font_path, text, width, mx):
    """Размер шрифта, при котором строка занимает width (но не больше mx)."""
    return min(100.0 * width / max(_width(font_path, text), 1.0), mx)


def place_map(pts):
    """-> (left, top, scale, [(x, y, marker_scale) на холсте])."""
    cx0, cy0 = 540.0, 1000.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if len(pts) == 1:
        sc = 0.9
        cx, cy = pts[0]
    else:
        bw, bh = max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1)
        sc = min(1.0, max(0.38, min(720.0 / bw, 480.0 / bh)))
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        cy0 = 1060.0   # группа ударов ниже центра: верхние отметки не прячутся под ленту
        if bw * sc > 760 or bh * sc > 520:   # не помещаются все — держим главный удар по центру
            cx, cy = pts[0]
    left = min(0.0, max(W - MW * sc, cx0 - cx * sc))
    top = min(380.0, max(H - MH * sc, cy0 - cy * sc))   # верхний край карты может уйти под шапку (она закрывает y<~740)
    mks = []
    for i, (x, y) in enumerate(pts):
        px, py = left + x * sc, top + y * sc
        if 80 <= px <= 1000 and 560 <= py <= 1380:
            mks.append((px, py, 1.0 if len(pts) == 1 else (0.8 if i == 0 else 0.62)))
    return left, top, sc, mks


CSS = """
@font-face{font-family:Rubik;font-weight:400;src:url(assets/fonts/rubik-400.ttf)}
@font-face{font-family:Rubik;font-weight:600;src:url(assets/fonts/rubik-600.ttf)}
@font-face{font-family:Rubik;font-weight:800;src:url(assets/fonts/rubik-800.ttf)}
@font-face{font-family:JBMono;font-weight:600;src:url(assets/fonts/jbmono-600.ttf)}
:root{--red:#e3140c;--red2:#ff2a1a;--yel:#ffd400;--blk:#0a0a0a}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1920px;background:#000;overflow:hidden}
#root{position:relative;width:1080px;height:1920px;overflow:hidden;font-family:Rubik,sans-serif;font-weight:800;color:#fff;background:#111}
.mapwrap{position:absolute;inset:0;overflow:hidden}
.map{position:absolute;background:url(assets/map.jpg) 0 0/100% 100% no-repeat;filter:saturate(1.15) contrast(1.08)}
.vig{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0) 62%,rgba(0,0,0,.55) 88%,rgba(0,0,0,.85) 100%);z-index:3}
.mk{position:absolute;width:0;height:0;z-index:6}
.mk>*{position:absolute;border-radius:50%;transform:translate(-50%,-50%);left:0;top:0}
.mk .r{border:7px solid var(--red2);box-shadow:0 0 30px 6px rgba(255,42,26,.85),inset 0 0 30px 4px rgba(255,42,26,.6)}
.mk .glow{background:radial-gradient(circle,rgba(255,212,0,.95) 0,rgba(255,90,20,.75) 28%,rgba(255,30,10,.35) 55%,rgba(255,30,10,0) 72%)}
.mk .burst{border-radius:0;background:radial-gradient(circle,#fff 0,var(--yel) 22%,var(--red2) 60%,rgba(255,42,26,0) 100%);clip-path:polygon(50% 0,58% 36%,85% 15%,64% 42%,100% 50%,64% 58%,85% 85%,58% 64%,50% 100%,42% 64%,15% 85%,36% 58%,0 50%,36% 42%,15% 15%,42% 36%)}
.mk .core{background:radial-gradient(circle,#fff 0,#fff 35%,var(--yel) 60%,var(--red2) 100%);box-shadow:0 0 24px 8px rgba(255,212,0,.9),0 0 60px 20px rgba(255,42,26,.8)}
.panel{position:absolute;left:0;top:0;width:1080px;background:var(--yel);z-index:10;
  background-image:radial-gradient(rgba(0,0,0,.08) 2.5px,transparent 3px);background-size:22px 22px}
.tape{position:absolute;left:-60px;width:1240px;height:46px;z-index:11;transform:rotate(-3.4deg);
  background:repeating-linear-gradient(-45deg,#0a0a0a 0 26px,var(--yel) 26px 52px);border-block:6px solid #0a0a0a;box-shadow:0 12px 30px rgba(0,0,0,.5)}
.brand{position:absolute;left:54px;top:92px;display:flex;align-items:center;gap:14px;background:var(--blk);padding:12px 24px 12px 18px;border-radius:40px;border:3px solid #fff;font-size:30px;letter-spacing:1.5px;line-height:1;z-index:20;white-space:nowrap}
.brand i{width:22px;height:22px;border-radius:50%;background:var(--red2);box-shadow:0 0 0 5px rgba(255,42,26,.35),0 0 18px 4px var(--red2)}
.urgent{position:absolute;left:54px;top:190px;z-index:12;background:#0a0a0a;color:var(--yel);border-radius:14px;padding:12px 34px 14px 24px;font-size:72px;line-height:1;white-space:nowrap;display:flex;align-items:center;gap:14px;letter-spacing:2px}
.urgent .dot{width:26px;height:26px;border-radius:50%;background:var(--red2);box-shadow:0 0 0 6px rgba(255,42,26,.4),0 0 22px 6px var(--red2)}
.hl{position:absolute;left:54px;width:960px;z-index:12}
.fit{display:block;white-space:nowrap}
.hl .fit{color:var(--red);line-height:.92;paint-order:stroke fill;-webkit-text-stroke:12px #0a0a0a;text-shadow:7px 8px 0 #0a0a0a}
.plate{position:absolute;left:54px;width:880px;z-index:12;background:#0a0a0a;border:6px solid var(--yel);padding:16px 30px 20px;box-shadow:10px 10px 0 rgba(0,0,0,.6)}
.plate .fit{color:var(--yel);line-height:.95}.plate .fit.w{color:#fff}
.foot{position:absolute;left:60px;width:960px;z-index:12;display:flex;flex-wrap:wrap;gap:12px 20px;align-items:center;white-space:nowrap}
.foot .date{font-family:JBMono,monospace;font-weight:600;font-size:34px;letter-spacing:2px;line-height:1;background:#0a0a0a;color:#fff;padding:10px 16px;border-radius:6px}
.foot .disc{font-family:JBMono,monospace;font-weight:600;font-size:25px;letter-spacing:2px;line-height:1;background:var(--yel);color:#000;padding:10px 14px;border-radius:6px}
"""

MK = ('<div class="mk" style="left:{x:.0f}px;top:{y:.0f}px;transform:scale({s})"><div class="glow" style="width:760px;height:760px"></div>'
      '<div class="r" style="width:360px;height:360px;opacity:.7"></div><div class="r" style="width:200px;height:200px"></div>'
      '<div class="burst" style="width:230px;height:230px"></div><div class="core" style="width:46px;height:46px"></div></div>')


def render(p, font_path, lang="ru"):
    e = lambda s: html.escape(s, quote=False)
    left, top, sc, mks = place_map(p["pts"])
    s1 = fit(font_path, p["count"], 940, 360)
    s2 = fit(font_path, p["obj"], 940, 230)
    hl_top = 300
    hl_bottom = hl_top + s1 * 0.92 + 6 + s2 * 0.92
    ph = round(hl_bottom + 70)
    plate_lines, ph_plate = [], 0.0
    for i, (tx, c) in enumerate(p["place"]):
        s = fit(font_path, tx, 880 - 12 - 60, 120 if i == 0 else 60)
        plate_lines.append(f'<div class="fit {c}" style="font-size:{s:.1f}px">{e(tx)}</div>')
        ph_plate += s * 0.95
    plate_bottom = PLATE_Y + 6 + 16 + ph_plate + 20 + 6
    foot_top = round(plate_bottom + 30)
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=1080, height=1920">
<script src="assets/gsap.min.js"></script>
<style>{CSS}</style></head><body>
<div id="root" data-composition-id="thumb" data-start="0" data-duration="2" data-width="1080" data-height="1920">
  <div class="mapwrap"><div class="map" style="width:{MW * sc:.0f}px;height:{MH * sc:.0f}px;left:{left:.0f}px;top:{top:.0f}px"></div></div>
  <div class="vig"></div>
  {"".join(MK.format(x=x, y=y, s=s) for x, y, s in mks)}
  <div class="panel" style="height:{ph}px;clip-path:polygon(0 0,100% 0,100% calc(100% - 64px),0 100%)"></div>
  <div class="tape" style="top:{ph - 55}px"></div>
  <div class="brand"><i></i><span>{e(p["brand"])}</span></div>
  <div class="urgent"><span class="dot"></span><span>{e(p["urgent"])}</span></div>
  <div class="hl" style="top:{hl_top}px"><div class="fit" style="font-size:{s1:.1f}px">{e(p["count"])}</div><div class="fit" style="font-size:{s2:.1f}px;margin-top:6px">{e(p["obj"])}</div></div>
  <div class="plate" style="top:{PLATE_Y}px">{"".join(plate_lines)}</div>
  <div class="foot" style="top:{foot_top}px"><span class="date">{e(p["date"])}</span><span class="disc">{e(p["disc"])}</span></div>
</div>
<script>window.__timelines=window.__timelines||{{}};window.__timelines["thumb"]=gsap.timeline({{paused:true}});</script>
</body></html>
"""


def strings(p):
    """Все видимые строки обложки (для перевода en_pass.py), по порядку."""
    out = [p["brand"], p["urgent"], p["count"], p["obj"]] + [t for t, _ in p["place"]] + [p["date"], p["disc"]]
    return list(dict.fromkeys(out))


def translate(p, mapping):
    q = json.loads(json.dumps(p))
    for k in ("brand", "urgent", "count", "obj", "date", "disc"):
        q[k] = mapping.get(q[k], q[k])
    q["place"] = [[mapping.get(t, t), c] for t, c in q["place"]]
    return q
