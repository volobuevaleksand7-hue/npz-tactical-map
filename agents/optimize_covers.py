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
import subprocess
import sys
import glob

MAX_DIM = 1200          # og:image с запасом; карточка 290px и новости всё равно downscale
COLORS = 256            # палитра PNG
SKIP_BYTES = 420 * 1024  # уже оптимизирован → не трогаем (идемпотентность)

THUMB_DIM = 560          # карточка архива ~290px CSS → 560 хватает и на 2x
THUMB_Q = 72

FULL_WEBP_Q = 82         # полноразмерный .webp рядом с обложкой — для <img> (hero/карточки).
                         # og:image/twitter:image остаются .png (осознанно, надёжнее в TG/соцсетях).


def make_webp_full(path, quality=FULL_WEBP_Q):
    """Полноразмерный .webp рядом с cover-*.png/analytics-*.png через cwebp (CLI, установлен).

    Вызывается сразу после сохранения PNG (хук optimize_cover, единая точка для
    gen_cover_today.py/wave_cover.py/hermes/scripts/build-covers.py — все кладут
    финальный PNG через caption_cover.py, который зовёт optimize_cover). cwebp
    недоступен или упал → предупреждение в лог, генерация обложки НЕ падает.
    """
    webp_path = os.path.splitext(path)[0] + ".webp"
    if os.path.isfile(webp_path) and os.path.getmtime(webp_path) >= os.path.getmtime(path):
        return webp_path  # уже свежий — не дёргаем cwebp зря
    try:
        r = subprocess.run(["cwebp", "-quiet", "-q", str(quality), path, "-o", webp_path],
                            capture_output=True, timeout=30)
        if r.returncode != 0:
            print("make_webp_full: cwebp failed for %s: %s" %
                  (path, r.stderr.decode("utf-8", "replace")[:200]))
            return None
        return webp_path
    except FileNotFoundError:
        print("make_webp_full: cwebp not found on PATH, skipping webp conversion for", path)
        return None
    except Exception as e:
        print("make_webp_full: %s -> %s" % (path, e))
        return None


def make_thumb(path):
    """Мини-обложка для карточек архива: assets/thumb/<name>.webp (~25 КБ вместо ~340 КБ).

    На /news 69 карточек тянули полноразмерные cover-*.png в блок шириной 290px —
    ~23 МБ за один просмотр архива, главный источник Fast Data Transfer.
    Возвращает rel-путь тумбы или None.
    """
    try:
        from PIL import Image
    except Exception:
        return None
    if not os.path.isfile(path):
        return None
    root = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    tdir = os.path.join(root, "assets", "thumb")
    out = os.path.join(tdir, os.path.splitext(os.path.basename(path))[0] + ".webp")
    rel = os.path.relpath(out, root)
    if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        return rel
    try:
        os.makedirs(tdir, exist_ok=True)
        im = Image.open(path).convert("RGB")
        im.thumbnail((THUMB_DIM, THUMB_DIM), Image.LANCZOS)
        im.save(out, "WEBP", quality=THUMB_Q, method=6)
        return rel
    except Exception as e:
        print("make_thumb: %s -> %s" % (path, e))
        return None


def optimize_cover(path, max_dim=MAX_DIM, colors=COLORS):
    """Ужать один PNG на месте. True — если переписали, False — если пропустили.

    В конце (все ветки, включая ранние return) — make_webp_full: конвейер сам
    держит .webp свежим рядом с .png для КАЖДОЙ обложки, прошедшей через этот
    хук (caption_cover.py зовёт его после каждого сохранения)."""
    try:
        result = _optimize_cover_impl(path, max_dim, colors)
    finally:
        if os.path.isfile(path):
            make_webp_full(path)
    return result


def _optimize_cover_impl(path, max_dim, colors):
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
        if "/cover-" in p.replace(os.sep, "/"):
            make_thumb(p)
    print("optimize_covers: %d/%d сжато, всего %.1f -> %.1f МБ" %
          (changed, len(targets), total_before / 1048576, total_after / 1048576))


def _selfcheck():
    """assert-демо: make_webp_full не падает ни при доступном, ни при отсутствующем
    cwebp, и производит .webp когда конвертер реально есть."""
    import tempfile
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cover-selfcheck.png")
        Image.new("RGB", (8, 8), (200, 30, 20)).save(p, "PNG")
        out = make_webp_full(p)
        has_cwebp = subprocess.run(["which", "cwebp"], capture_output=True).returncode == 0
        if has_cwebp:
            assert out and os.path.isfile(out), "cwebp доступен, но .webp не создан"
        else:
            assert out is None, "cwebp недоступен — ожидался None, а не путь"
    print("OK make_webp_full selfcheck (cwebp %s)" % ("found" if has_cwebp else "missing, handled gracefully"))


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
