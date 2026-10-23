#!/usr/bin/env python3
"""Обложка V4 для уже вышедшего рилса из кэша сборки: cover_only.py <kind> <date>
(kind: reel | reel-evening | urgent). Берёт .build/<kind>-<date>/{ids.json,map-points.json}, пишет out/<kind>-<date>.jpg.
Ничего не заливает: на YouTube ставит upload.py."""
import json
import os
import sys
from pathlib import Path

kind, date = sys.argv[1], sys.argv[2]
VIDEO = Path(__file__).resolve().parents[1]
build = VIDEO / ".build" / f"{kind}-{date}"
ids = json.loads((build / "ids.json").read_text(encoding="utf-8"))

os.environ["REEL_KIND"] = kind
os.environ["REEL_ONLY"] = ",".join(ids)
os.environ["REEL_ALLOW_RUMORED"] = "1"   # id заданы явно: берём ровно удары этого выпуска
sys.path.insert(0, str(VIDEO / "reel"))
import build_reel as br  # noqa: E402

br.shown_ids = lambda: set()
sel, day = br.select_strikes(date)
mp = json.loads((build / "map-points.json").read_text(encoding="utf-8"))
P = {p["id"]: p for p in mp["points"]}
cities = []
for s in sel + day:
    c = str(s.get("city") or "").strip()
    if c and c not in cities and len(c) <= 16:
        cities.append(c)
tp = br.thumb_params(sel, day, cities, br.span_rus(date), P)
assert tp["pts"], "нет точек ударов"

import thumb_v4  # noqa: E402

thumb = build / "thumb"
thumb.mkdir(exist_ok=True)
(thumb / "params.json").write_text(json.dumps(tp, ensure_ascii=False, indent=1), encoding="utf-8")
(thumb / "index.html").write_text(thumb_v4.render(tp, build / "assets" / "fonts" / "rubik-800.ttf"), encoding="utf-8")
(thumb / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}), encoding="utf-8")
if not (thumb / "assets").exists():
    (thumb / "assets").symlink_to("../assets")
print(json.dumps({"kind": kind, "date": date, "n": len(day), "sel": len(sel), "count": tp["count"], "obj": tp["obj"],
                  "place": tp["place"], "disc": tp["disc"]}, ensure_ascii=False))
