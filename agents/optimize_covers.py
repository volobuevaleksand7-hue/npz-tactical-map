#!/usr/bin/env python3
"""Сжатие обложек/статичных PNG — режет Fast Data Transfer на Vercel.

Обложки cover-*.png рождались 1-2 МБ (photo 1536×1024) и грузились в карточку 290px
и в og:image при каждом просмотре карт. Здесь: resize ≤1200px + адаптивная палитра 256
с дизерингом (скрывает бандинг) + PNG optimize → ~×8 (2 МБ → ~270 КБ), БЕЗ смены .png
(og/новости/карточка ссылаются по имени). Идемпотентно: уже маленькие/узкие пропускаем.

Использование:
  python3 agents/optimize_covers.py            # прогнать все assets/cover-* + analytics-* + og-image
  from optimize_covers import optimize_cover; optimize_cover(path)   # один файл (хук в caption_cover)
"""
import os
import sys
import glob

MAX_DIM = 1200          # og:image с запасом; карточка 290px и новости всё равно downscale
COLORS = 256            # палитра PNG
SKIP_BYTES = 420 * 1024  # уже оптимизирован → не трогаем (идемпотентность)


def optimize_cover(path, max_dim=MAX_DIM, colors=COLORS):
    """Ужать один PNG на месте. True — если переписали, False — если пропустили."""
    try:
        from PIL import Image
    except Exception:
        return False
    if not os.path.isfile(path):
        return False
    try:
        im = Image.open(path)
        w, h = im.size
        # идемпотентность: оптимизированный файл уже в режиме палитры (P) и в лимите → пропускаем.
        # Иначе повторный прогон (каждая генерация обложек) плодил бы git-diff и лишний CPU.
        if im.mode in ("P", "PA") and max(w, h) <= max_dim:
            return False
        if os.path.getsize(path) <= SKIP_BYTES and max(w, h) <= max_dim:
            return False
        im = im.convert("RGB")
        if max(w, h) > max_dim:
            im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        # адаптивная палитра + Флойд-Стейнберг (дизеринг прячет бандинг на небе/градиентах)
        pal = im.convert("P", palette=Image.ADAPTIVE, colors=colors, dither=Image.FLOYDSTEINBERG)
        tmp = path + ".opt.tmp"
        pal.save(tmp, "PNG", optimize=True)
        # берём результат ТОЛЬКО если он реально меньше (иначе оставляем оригинал)
        if os.path.getsize(tmp) < os.path.getsize(path):
            os.replace(tmp, path)
            return True
        os.remove(tmp)
        return False
    except Exception as e:
        print("optimize_covers: %s -> %s" % (path, e))
        return False


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = []
    for pat in ("assets/cover-*.png", "assets/analytics-*.png", "og-image.png"):
        targets += glob.glob(os.path.join(root, pat))
    total_before = total_after = 0
    changed = 0
    for p in sorted(targets):
        before = os.path.getsize(p)
        total_before += before
        if optimize_cover(p):
            changed += 1
        after = os.path.getsize(p)
        total_after += after
        if before != after:
            print("  %-40s %6.0f -> %5.0f KB" % (os.path.basename(p), before / 1024, after / 1024))
    print("optimize_covers: %d/%d сжато, всего %.1f -> %.1f МБ" %
          (changed, len(targets), total_before / 1048576, total_after / 1048576))


if __name__ == "__main__":
    sys.exit(main())
