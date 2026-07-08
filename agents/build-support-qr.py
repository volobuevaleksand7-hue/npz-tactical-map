#!/usr/bin/env python3
"""Генерирует QR-код кошелька для скрытой страницы /support.
Использование:  python agents/build-support-qr.py <address> [out.png]
QR — тёмные модули на белом фоне, читается в обеих темах сайта.
"""
import sys, qrcode

addr = sys.argv[1] if len(sys.argv) > 1 else "USDT_ADDRESS_PLACEHOLDER"
out = sys.argv[2] if len(sys.argv) > 2 else "assets/support-usdt-qr.png"

qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
qr.add_data(addr)
qr.make(fit=True)
qr.make_image(fill_color="#111111", back_color="white").save(out)
print(f"wrote {out}  ({addr[:12]}…)" if len(addr) > 12 else f"wrote {out} ({addr})")
