#!/usr/bin/env python3
"""
content_guard.py — нейтральность на этапе ПУБЛИКАЦИИ (Telegram + сайт).

Санитайзер agents/sanitize-strikes.py вырезает мусор из data/strikes.json в
pre-commit хуке — но это происходит на git-commit, ПОЗЖЕ отправки молнии в
канал. Этот модуль даёт тот же фильтр как импортируемую функцию, чтобы звать
его ПЕРЕД публикацией/рендером (strike_pipeline, radar_publish, broadcast,
editorial_digest, gen-news).

22.07: словарь переехал в agents/neutrality.py. Раньше в шапке этого файла
стояло «логика должна совпадать с sanitize-strikes.py — меняешь одно, поправь
второе»; предсказуемо не поправили, и копии разъехались (одна знала «русня»,
другая «русн»). Теперь копия одна, здесь только адаптер.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "agents"))
import neutrality  # noqa: E402

UA_CHARS = neutrality.UA_CHARS
UA_MARK = neutrality.UA_MARK
VALID_CONF = neutrality.VALID_CONF
JET_WORDS = neutrality.JET_WORDS
FUEL_WORDS = neutrality.FUEL_WORDS

reason_bad = neutrality.reason_bad
is_clean = neutrality.is_clean
# Текст поста: эпитеты вырезаются молча, факт остаётся. Возвращает (текст, N правок).
scrub_text = neutrality.scrub_text
# Непочиняемое в тексте: [(причина, фрагмент)]. Пусто — публиковать можно.
text_reasons = neutrality.text_reasons


def demo():
    neutrality.demo()
    assert is_clean({"city": "Рязань", "target": "Рязанский НПЗ", "confidence": "reported"})
    assert not is_clean({"city": "X", "target": "Слава Україні", "confidence": "reported"})
    assert is_clean({"city": "X", "target": "склад Wildberries", "confidence": "reported"})
    assert scrub_text("Удар по оккупированному Севастополю")[0] == "Удар по Севастополю"
    print("content_guard demo OK")


if __name__ == "__main__":
    demo()
