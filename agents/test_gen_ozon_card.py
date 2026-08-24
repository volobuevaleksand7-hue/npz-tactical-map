#!/usr/bin/env python3
"""Проверка: SVG-карточка Ozon не расходится с data/warehouses.json."""
import importlib.util
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def module(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "agents", path))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
def main():
    card = module("gen-ozon-card.py", "gen_ozon_card")
    page = module("gen-warehouses-page.py", "gen_warehouses_page")
    doc = page.load_data()
    ozon = [w for w in doc["warehouses"] if w["operator"] == "ozon"]
    hit = [w for w in ozon if w["status"] == "hit"]
    ok = [w for w in ozon if w["status"] == "ok"]
    html = card.build()
    assert 'data-ozon-card="warehouses"' in html
    assert str(len(ozon)) in html and str(len(hit)) in html and str(len(ok)) in html
    assert doc["meta"]["generated_at"][:10] in html
    for warehouse in ozon:
        assert warehouse["name"] in html, warehouse["name"]
    for warehouse in hit:
        assert warehouse["date"] in html, warehouse["name"]
        assert all(word in html for word in warehouse.get("note", "").split()), warehouse["name"]
    print("test_gen_ozon_card OK")
if __name__ == "__main__":
    main()
