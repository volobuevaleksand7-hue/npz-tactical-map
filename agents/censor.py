#!/usr/bin/env python3
"""
censor.py — нейтральность на ВЫХОДЕ: статьи (*.html, *.md) и тексты постов.

До 22.07 фильтр стоял только на data/strikes.json. Статью или пост, написанные
агентом, не проверял никто: страница уезжала на сайт, пост — в канал.

Что делает:
  1. ЧИНИТ — вырезает оценочные эпитеты (neutrality.scrub_text) и перезаписывает
     файл. Молча, без вопросов: факт остаётся, ярлык уходит.
  2. ДИАГНОЗ — ищет непочиняемое (украинский язык, лозунг, призыв) и печатает
     файл + фрагмент. Такое автоправкой не лечится, поэтому exit 1.

Вызывается из .githooks/pre-commit по всем staged *.html/*.md — то есть ни одна
статья не уезжает на сайт непроверенной, кто бы её ни написал.

  python3 agents/censor.py FILE...            # починить + проверить
  python3 agents/censor.py --check FILE...    # только проверить, не писать
  python3 agents/censor.py --all              # пройти по всем статьям репозитория
  python3 agents/censor.py --selftest

exit 0 — чисто (или всё починено), exit 1 — остались непочиняемые нарушения.
"""
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import neutrality  # noqa: E402

# Не статьи: сгенерированный служебный HTML и чужие библиотеки.
SKIP_PARTS = ("/assets/vendor/", "/node_modules/", "/.git/", "/.vercel/")


def article_files():
    """Только ОПУБЛИКОВАННЫЕ страницы. docs/**.md сюда НЕ входят сознательно:
    это внутренние инженерные записки, и они законно цитируют ту самую лексику
    (словари фильтров, разборы инцидентов) — цензурить их значит цензурить
    собственную документацию."""
    out = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for pat in ("*.html", "*/*.html"):
        out += glob.glob(os.path.join(root, pat))
    return sorted(p for p in out if not any(s in p.replace(os.sep, "/") for s in SKIP_PARTS))


def process(path, fix=True):
    """Возвращает (сколько эпитетов вырезано, [(причина, фрагмент)...])."""
    try:
        src = io.open(path, encoding="utf-8").read()
    except (IOError, UnicodeDecodeError) as e:
        sys.stderr.write("censor: пропуск %s (%s)\n" % (path, e))
        return 0, []
    markup = path.lower().endswith((".html", ".htm"))
    fixed, n = neutrality.scrub_text(src)
    if n and fix:
        io.open(path, "w", encoding="utf-8").write(fixed)
    return n, neutrality.text_reasons(fixed if n else src, markup=markup)


def main(argv):
    fix = "--check" not in argv
    paths = [a for a in argv if not a.startswith("-")]
    if "--all" in argv:
        paths = article_files()
    if not paths:
        sys.stderr.write(__doc__)
        return 0
    scrubbed = 0
    violations = 0
    for p in paths:
        if not os.path.isfile(p):
            continue
        n, bad = process(p, fix=fix)
        if n:
            scrubbed += 1
            sys.stderr.write("censor: %s — вырезано эпитетов: %d%s\n"
                             % (p, n, "" if fix else " (не записано, --check)"))
        for reason, frag in bad:
            violations += 1
            sys.stderr.write("censor: НАРУШЕНИЕ %s | %s | %s\n" % (reason, p, frag))
    if violations:
        sys.stderr.write("censor: непочиняемых нарушений: %d — правь текст руками "
                         "(лозунг/призыв/укр-язык автоматом не нейтрализуется).\n" % violations)
        return 1
    if scrubbed:
        sys.stderr.write("censor: файлов почищено: %d\n" % scrubbed)
    return 0


def selftest():
    import tempfile
    d = tempfile.mkdtemp()
    ok = os.path.join(d, "ok.html")
    io.open(ok, "w", encoding="utf-8").write(
        '<html><body><p>Удар по оккупированному Севастополю</p>'
        '<a href="https://pravda.com.ua/a">источник</a></body></html>')
    n, bad = process(ok)
    assert n == 1 and bad == [], (n, bad)
    assert "оккупированн" not in io.open(ok, encoding="utf-8").read()

    bad_f = os.path.join(d, "bad.html")
    io.open(bad_f, "w", encoding="utf-8").write("<p>Слава Україні, бей русню</p>")
    n, bad = process(bad_f, fix=False)
    kinds = {r for r, _ in bad}
    assert "UA-lang" in kinds and "call-to-action" in kinds, bad

    # --check не трогает файл
    before = io.open(bad_f, encoding="utf-8").read()
    process(bad_f, fix=False)
    assert io.open(bad_f, encoding="utf-8").read() == before
    print("censor selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        neutrality.demo()
        selftest()
        sys.exit(0)
    sys.exit(main(sys.argv[1:]))
