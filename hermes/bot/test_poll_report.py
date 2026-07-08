#!/usr/bin/env python3
"""Проверка порогов отчёта о подписчиках (_should_report). Запуск: python3 test_poll_report.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poll import _should_report as R

# ≤25 — докладываем о каждом
assert all(R(n) for n in range(1, 26)), "первые 25 должны репортиться все"
# 25→100 — каждый 5-й (кратные 5), остальные молчат
assert R(30) and R(55) and R(100)
assert not R(26) and not R(29) and not R(56) and not R(99)
# 100→500 — каждый 10-й
assert R(110) and R(250) and R(500)
assert not R(105) and not R(115) and not R(499)
# >500 — каждый 50-й
assert R(550) and R(1000)
assert not R(560) and not R(551) and not R(999)
print("test_poll_report: OK")
