#!/usr/bin/env python3
"""Пустой почасовой радар-отчёт («не зафиксировано») подавляется по умолчанию,
реальная молния (МОЛНИЯ) — никогда. Это главный инвариант правки 2026-08-01:
шум режем, реальные алерты не трогаем. Запуск: python3 test_send_to_channel_filter.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import send_to_channel as S

EMPTY = "За последний час новых ударов по нефтегазовой инфраструктуре не зафиксировано."
EMPTY_VARIANT = "За последние два часа новых атак не зафиксировано, обстановка спокойная."
MOLNIYA = "🚨 <b>МОЛНИЯ · Удар по Афипскому НПЗ</b>\n\nПодтверждено, пожар на установке."
CRIMEA_INCIDENT = "🔥 УДАРЫ / ИНЦИДЕНТЫ — КРЫМ\n01.08.2026 10:00 МСК\n📍 Объект: склад в Симферополе"

assert S.is_empty_radar_report(EMPTY) is True, "пустой отчёт не распознан"
assert S.is_empty_radar_report(EMPTY_VARIANT) is True, "вариант пустого отчёта не распознан"
assert S.is_empty_radar_report(MOLNIYA) is False, "🔴 молния помечена как пустая — реальный алерт был бы подавлен"
assert S.is_empty_radar_report(CRIMEA_INCIDENT) is False, "реальный инцидент (crimea_watch) помечен как пустой"
assert S.is_empty_radar_report("") is False
assert S.is_empty_radar_report(None) is False

print("test_send_to_channel_filter: ok")
