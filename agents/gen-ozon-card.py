#!/usr/bin/env python3
"""SVG-инфографика крупных фулфилмент-центров Ozon для страницы кластера."""
import importlib.util
import os
from html import escape
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load_module(filename, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "agents", filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
# load_data остаётся единственной точкой чтения warehouses.json.
gwp = load_module("gen-warehouses-page.py", "gen_warehouses_page")
survivors = load_module("gen-survivors-page.py", "gen_survivors_page")
def lines(value, limit=42):
    words, result, row = str(value).split(), [], []
    for word in words:
        if len(" ".join(row + [word])) > limit and row:
            result.append(" ".join(row)); row = []
        row.append(word)
    return result + ([" ".join(row)] if row else []) or ["—"]
def svg_text(x, y, value, css_class):
    return '<text x="%d" y="%d" class="%s">%s</text>' % (x, y, css_class, escape(str(value)))
def panel(x, title, items, status, start_y):
    """Рисует колонку. Высота панели считается ПОСЛЕ раскладки элементов,
    иначе прямоугольник не знает, сколько в него влезло."""
    color = "ozon-hit" if status == "hit" else "ozon-ok"
    parts, y = [], start_y + 58
    for district, group in survivors.okrug_groups(items):
        parts.append(svg_text(x + 22, y + 15, "%s ФО · %d" % (district, len(group)), "ozon-district")); y += 31
        for warehouse in group:
            detail = lines(warehouse.get("note", "—")) if status == "hit" else [warehouse["region"]]
            height = 42 + (14 * len(detail) if status == "hit" else 0)
            parts.append('<rect x="%d" y="%d" width="446" height="%d" rx="8" class="ozon-item %s" />' % (x + 22, y, height, color))
            parts.append(svg_text(x + 34, y + 18, warehouse["name"], "ozon-name"))
            if status == "hit":
                parts.append(svg_text(x + 34, y + 35, warehouse["date"], "ozon-date"))
                parts.extend(svg_text(x + 108, y + 49 + 14 * i, note, "ozon-note") for i, note in enumerate(detail))
            else:
                parts.append(svg_text(x + 34, y + 34, warehouse["region"], "ozon-region"))
            y += height + 8
        y += 8
    panel_h = max(y - start_y, 90)
    head = ['<rect x="%d" y="%d" width="490" height="%d" rx="12" class="ozon-panel %s" />' % (x, start_y, panel_h, color),
            svg_text(x + 22, start_y + 30, "%s · %d" % (title, len(items)), "ozon-panel-title")]
    return "\n".join(head + parts), start_y + panel_h

def build():
    doc = gwp.load_data(); ozon = [w for w in doc["warehouses"] if w["operator"] == "ozon"]
    hit = [w for w in ozon if w["status"] == "hit"]; ok = [w for w in ozon if w["status"] == "ok"]
    hit_svg, hit_bottom = panel(24, "ПОРАЖЕНЫ", hit, "hit", 112); ok_svg, ok_bottom = panel(546, "БЕЗ СООБЩЕНИЙ ОБ УДАРЕ", ok, "ok", 112)
    height = max(hit_bottom, ok_bottom) + 16; updated = doc["meta"]["generated_at"][:10]
    return '''      <section class="ozon-card" data-ozon-card="warehouses" aria-labelledby="ozon-card-title">
        <div class="ozon-card-head"><div><p class="ozon-card-kicker">OZON · КРУПНЫЕ ФУЛФИЛМЕНТ-ЦЕНТРЫ</p><h2 id="ozon-card-title">Какие хабы Ozon отмечены в выборке проекта</h2></div><p>Актуально: <strong>%s</strong> · <strong>%d</strong> объектов</p></div>
        <div class="ozon-card-scroll"><svg class="ozon-card-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1060 %d" width="1060" height="%d" role="img" aria-label="%d объектов Ozon: %d поражены, %d без сообщений об ударе">
          <style>.ozon-bg{fill:var(--surface)}.ozon-panel{stroke:var(--line);stroke-width:1}.ozon-panel.ozon-hit{fill:color-mix(in srgb,var(--red) 7%%,var(--surface))}.ozon-panel.ozon-ok{fill:color-mix(in srgb,var(--teal) 7%%,var(--surface))}.ozon-panel-title,.ozon-district,.ozon-date{font-family:var(--mono)}.ozon-panel-title{font-size:14px;font-weight:800;fill:var(--ink)}.ozon-district{font-size:11px;font-weight:800;fill:var(--ink-dim)}.ozon-item{stroke:var(--line);stroke-width:1;fill:var(--surface)}.ozon-item.ozon-hit{stroke:var(--red)}.ozon-item.ozon-ok{stroke:var(--teal)}.ozon-name{font-family:var(--disp);font-size:14px;font-weight:800;fill:var(--ink)}.ozon-region,.ozon-note{font-family:var(--disp);font-size:11px;fill:var(--ink-dim)}.ozon-date{font-size:11px;font-weight:800;fill:var(--red)}</style>
          <rect class="ozon-bg" width="1060" height="%d" rx="12" /><text x="24" y="32" class="ozon-panel-title">%d КРУПНЫХ ОБЪЕКТОВ OZON</text><text x="24" y="56" class="ozon-region">Красным — подтверждённые поражения; нейтральным — объекты без сообщений об ударе.</text><text x="24" y="79" class="ozon-region">Для поражённых указаны дата и сведения из открытых данных проекта.</text>
%s
%s
        </svg></div><p class="ozon-card-caption">Выборка проекта: крупные фулфилмент-центры Ozon, сгруппированные по федеральным округам. «Без сообщений об ударе» не означает подтверждённую штатную работу.</p>
      </section>''' % (updated, len(ozon), height, height, len(ozon), len(hit), len(ok), height, len(ozon), hit_svg, ok_svg)
def demo():
    html, doc = build(), gwp.load_data(); ozon = [w for w in doc["warehouses"] if w["operator"] == "ozon"]
    assert str(len(ozon)) in html
    for warehouse in ozon: assert warehouse["name"] in html
    for warehouse in (w for w in ozon if w["status"] == "hit"): assert warehouse["date"] in html and all(word in html for word in warehouse["note"].split())
    print("gen-ozon-card demo OK")
if __name__ == "__main__": demo()
