#!/usr/bin/env python3
"""Пост чистится ПЕРЕД отправкой, а не только на git-commit.

Санитайзер правит data/strikes.json в pre-commit — то есть уже после того, как
молния ушла в канал. Так 01.08 в ленту попали «Bashneft-UNPZ» и «по информации SBU».
Запуск: python3 test_molniya_neutrality.py
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_CHANNEL_MIRRORS", "")

import radar_publish as RP


def rendered(strike):
    """Текст молнии, как он уйдёт в канал."""
    import render as R
    return R.render_molniya(RP.strike_to_molniya_event(strike))


latin = {"date": "2026-08-01", "city": "Уфа", "region": "Республика Башкортостан",
         "target": "нефтеперерабатывающий завод Bashneft-UNPZ",
         "detail": "По информации SBU, атакован в ходе операции", "confidence": "reported"}
text = rendered(latin)
assert "Bashneft-UNPZ" not in text and "Башнефть-УНПЗ" in text, text
assert "SBU" not in text and "СБУ" in text, text

# исходную запись не портим: чистится копия, оригинал остаётся у вызывающего
assert latin["target"] == "нефтеперерабатывающий завод Bashneft-UNPZ"

# оценка стороны уходит, атрибуция остаётся — читатель должен видеть, кто заявил
claim = {"date": "2026-08-01", "city": "Мариуполь", "region": "ДНР", "target": "порт",
         "detail": "Генштаб ВСУ подтвердил успешный удар по порту", "confidence": "reported"}
text = rendered(claim)
assert "успешн" not in text.lower(), text
assert "Генштаб ВСУ" in text, "атрибуцию вырезать нельзя: " + text

# 🔴 бренды и суда латиницей — норма русской прессы, транслит их изуродует
keep = {"date": "2026-08-01", "city": "Пенза", "region": "Пензенская область",
        "target": "логистический центр Wildberries",
        "detail": "Танкер Nordic Zenith рядом не пострадал", "confidence": "reported"}
text = rendered(keep)
assert "Wildberries" in text and "Nordic Zenith" in text, text

print("test_molniya_neutrality: ok")
