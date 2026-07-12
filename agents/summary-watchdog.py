#!/usr/bin/env python3
"""Сторож-генератор дневной сводки /news.

Не просто следит, а САМ ЧИНИТ. Ставится в cron на VPS на 8:15 и 20:15 МСК
(после плановых сводок 08:00/20:00). Проверяет живой /news и, если сводки за
сегодня нет / обложка-заглушка, — сам дособерёт и запушит (деплой автоматом):

  1. решает, есть ли вообще события за сегодня (data/strikes.json + fuel-voices.json).
     Нет событий → тихий день, это НЕ провал, ничего не делаем;
  2. есть события, но карточки/обложки на живом сайте нет → САМОЛЕЧЕНИЕ:
     build-covers.py (Codex — есть и на VPS) → gen-news.py → git-sync push;
  3. успех → короткий пинг «досгенерил автоматически» + закрывает инцидент;
  4. собрать НЕ смог (нет данных совсем / push упал) → ГРОМКИЙ пинг + OPEN-инцидент
     в docs/agents/incidents.md (страховка).

Почему генератор, а не «позови Гермеса»: инцидент-инбокс сам не исполняется —
запущенные рутины (сборщики по слоям) не читают incidents.md, а полной сессии
Гермеса по HERMES.md §0 в кроне нет. 12.07 сторож поймал провал в 08:15, но
чинить было некому → сводка не вышла. Теперь чинит сам.

Токен: env NPZ_BOT_TOKEN -> ~/.npz-bot/token. Чат: env NPZ_OWNER_CHAT -> 609952529.
Запуск:  python3 agents/summary-watchdog.py            # проверка + самолечение
         python3 agents/summary-watchdog.py --dry-run  # проверка без правок/push
         python3 agents/summary-watchdog.py --test / --selfcheck
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

NEWS_URL = "https://npz-tactical-map.vercel.app/news"
MSK = timezone(timedelta(hours=3))
OWNER_DEFAULT = "609952529"
ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "agents" / "logs" / "summary-watchdog.log"
INCIDENTS = ROOT / "docs" / "agents" / "incidents.md"
MARKER = "<!-- INCIDENTS BELOW (newest first) -->"


def now_msk() -> str:
    return datetime.now(MSK).strftime("%Y-%m-%d %H:%M МСК")


def today() -> str:
    return datetime.now(MSK).strftime("%Y-%m-%d")


def fetch(url: str) -> str:
    bust = f"{url}?wd={int(datetime.now(timezone.utc).timestamp())}"
    req = urllib.request.Request(bust, headers={
        "User-Agent": "npz-summary-watchdog/2", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def log(msg: str) -> None:
    line = f"[{now_msk()}] {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---- Telegram ---------------------------------------------------------------
def tg_send(text: str) -> bool:
    token = os.environ.get("NPZ_BOT_TOKEN", "").strip()
    if not token:
        p = Path.home() / ".npz-bot" / "token"
        token = p.read_text().strip() if p.exists() else ""
    if not token:
        log("НЕТ токена бота — пинг не отправлен")
        return False
    chat = os.environ.get("NPZ_OWNER_CHAT", OWNER_DEFAULT).strip()
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return json.load(r).get("ok", False)
    except Exception as e:  # noqa: BLE001
        log(f"ошибка отправки TG: {e}")
        return False


# ---- Проверка ---------------------------------------------------------------
def check(day: str, html: str):
    """-> список kind'ов проблем ([] = всё ок)."""
    if f"news/{day}" not in html:
        return ["card-missing"]           # нет карточки — обложку проверять незачем
    if f"cover-{day}.png" not in html:
        return ["cover-fallback"]
    return []


def incident_body(kind: str, day: str) -> str:
    if kind == "card-missing":
        return (f"На живом /news НЕТ карточки-сводки за {day}.\n"
                "Что сделать:\n"
                f"- если в data/strikes.json уже есть удары за {day} → "
                "`python3 agents/gen-news.py` + git-sync + деплой;\n"
                f"- если ударов за {day} нет → прогони сборщик strikes "
                "(agents/update-prompt-strikes.md) за эту дату, затем gen-news;\n"
                f"- проверь {NEWS_URL}")
    return (f"Карточка за {day} на месте, но обложка = заглушка og-image. "
            "Обычно самолечение чинит само (Codex работает и на VPS, и на Маке); "
            "если висит — вероятно кончились image-кредиты Codex-воркспейса.\n"
            "Что сделать:\n"
            f"- `python3 hermes/scripts/build-covers.py --dates {day}` "
            "(Codex-first) → `python3 agents/gen-news.py` → git-sync + деплой;\n"
            "- если Codex «out of credits» — пополнить воркспейс, либо разово "
            f"`NPZ_COVERS_ALLOW_OPENROUTER=1` при живом OpenRouter-ключе.")


# ---- Инбокс инцидентов (docs/agents/incidents.md) ---------------------------
def _split(text: str):
    """head (до маркера включительно), [ (status, id, block_text), ... ]."""
    if MARKER in text:
        head, tail = text.split(MARKER, 1)
        head += MARKER
    else:
        head, tail = text.rstrip() + "\n\n" + MARKER, ""
    blocks = []
    cur = None
    for line in tail.splitlines(keepends=True):
        m = re.match(r"## \[(OPEN|RESOLVED)\] (\S+)", line)
        if m:
            if cur:
                blocks.append(cur)
            cur = [m.group(1), m.group(2), line]
        elif cur:
            cur[2] += line
    if cur:
        blocks.append(cur)
    return head, blocks


def update_incidents(problem_kinds, day: str) -> bool:
    """Открывает инциденты по текущим проблемам, авто-резолвит исчезнувшие
    (за сегодня). -> True если файл изменён."""
    if not INCIDENTS.exists():
        return False
    text = INCIDENTS.read_text()
    head, blocks = _split(text)
    open_ids = {b[1] for b in blocks if b[0] == "OPEN"}
    want = {f"{k}-{day}" for k in problem_kinds}
    changed = False

    # 1) авто-резолв: OPEN-инциденты за СЕГОДНЯ, которых уже нет среди проблем
    for b in blocks:
        if b[0] == "OPEN" and b[1].endswith(day) and b[1] not in want:
            b[0] = "RESOLVED"
            b[2] = (b[2].replace("## [OPEN] ", "## [RESOLVED] ", 1)
                        .replace("status: OPEN", "status: RESOLVED", 1)
                    + f"resolved: {now_msk()} — проблема исчезла (авто, сторож)\n")
            changed = True

    # 2) новые OPEN для актуальных проблем, которых ещё нет
    new_blocks = []
    for kind in problem_kinds:
        iid = f"{kind}-{day}"
        if iid in open_ids:
            continue
        new_blocks.append([
            "OPEN", iid,
            f"## [OPEN] {iid}\nstatus: OPEN\nopened: {now_msk()} — "
            f"summary-watchdog\n{incident_body(kind, day)}\n\n"])
        changed = True

    if not changed:
        return False
    body = "".join(b[2] for b in new_blocks + blocks)
    INCIDENTS.write_text(head + "\n\n" + body.rstrip() + "\n")
    return True


def git_sync(msg: str) -> None:
    """Застейджить инцидент-файл и закоммитить через штатный git-sync (pull+push)."""
    gs = ROOT / "agents" / "git-sync.sh"
    if not gs.exists():
        log("git-sync.sh нет — инцидент записан локально, но не запушен")
        return
    try:
        subprocess.run(["git", "-C", str(ROOT), "add", "docs/agents/incidents.md"],
                       check=True, timeout=30)
        r = subprocess.run(["bash", str(gs), msg], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=120)
        tail = (r.stdout + r.stderr).strip().splitlines()
        log("git-sync: " + (tail[-1] if tail else f"rc={r.returncode}"))
    except Exception as e:  # noqa: BLE001
        log(f"git-sync не выполнен: {e}")


# ---- есть ли вообще события за сегодня (тихий день vs провал) ----------------
def data_has_today(day: str) -> bool:
    for fn, key in (("strikes.json", "strikes"), ("fuel-voices.json", "voices")):
        try:
            d = json.loads((ROOT / "data" / fn).read_text(encoding="utf-8"))
            items = d.get(key, []) if isinstance(d, dict) else d
            if any(str(x.get("date", ""))[:10] == day for x in items):
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


# ---- самолечение: собрать сводку и запушить ---------------------------------
def _run(cmd, timeout=300, env=None):
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          timeout=timeout, env=env)


def heal(day: str):
    """Дособрать сводку за сегодня и запушить.
    -> (card_ok, cover_ok): card_ok — карточка собралась и запушилась (гарантия),
    cover_ok — реальная обложка (не заглушка). Codex работает и на VPS (0.144.0),
    и на Маке — обложка обычно собирается. Если Codex «out of credits», карточка
    всё равно выходит с og-image (best-effort), обложку дорисуют позже."""
    env = {**os.environ, "NPZ_REPO": str(ROOT)}
    coverf = ROOT / "assets" / f"cover-{day}.png"
    try:
        _run([sys.executable, "agents/gen-news.py"])                  # карточка + архив
        if not coverf.exists():
            # best-effort: на Маке Codex сделает обложку, на VPS — молча GENFAIL
            _run([sys.executable, "hermes/scripts/build-covers.py", "--dates", day],
                 timeout=600, env=env)
            if coverf.exists():
                _run([sys.executable, "agents/gen-news.py"])          # вшить обложку
    except Exception as e:  # noqa: BLE001
        log(f"самолечение: сборка упала: {e}")
        return False, False

    card_ok = (ROOT / "news" / f"{day}.html").exists() and \
        f"news/{day}" in (ROOT / "news.html").read_text(encoding="utf-8")
    cover_ok = coverf.exists()
    if not card_ok:
        log("самолечение: gen-news не создал карточку (нет данных за сегодня?)")
        return False, cover_ok

    files = ["news.html", "news", "news-sitemap.xml", "rss.xml", "sitemap.xml",
             "data/news-archive.json"]
    if cover_ok:
        files.append(f"assets/cover-{day}.png")
    _run(["git", "-C", str(ROOT), "add", "--", *files])
    gs = ROOT / "agents" / "git-sync.sh"
    if not gs.exists():
        log("самолечение: git-sync.sh нет — собрал, но не запушил")
        return False, cover_ok
    r = _run(["bash", str(gs), f"watchdog self-heal: сводка за {day} досгенерена"],
             timeout=150)
    out = r.stdout + r.stderr
    pushed = "pushed" in out or "nothing" in out
    log("самолечение git-sync: " + (out.strip().splitlines()[-1] if out.strip()
                                    else f"rc={r.returncode}"))
    return pushed, cover_ok


# ---- main -------------------------------------------------------------------
def main() -> int:
    day = today()
    if "--test" in sys.argv:
        tg_send(f"✅ Тест сторожа сводки. Проверяю {NEWS_URL} за {day}.")
        log("тестовый пинг отправлен")
        return 0
    dry = "--dry-run" in sys.argv
    try:
        html = fetch(NEWS_URL)
    except Exception as e:  # noqa: BLE001
        log(f"НЕ достучался до /news: {e}")
        if not dry:
            tg_send(f"⚠️ Сторож сводки не смог открыть {NEWS_URL} ({e}).")
        return 1

    problems = check(day, html)

    # всё на месте — закрыть возможный вчерашний инцидент и выйти
    if not problems:
        if update_incidents([], day) and not dry:
            git_sync(f"watchdog: сводка за {day} на месте — закрыл инцидент(ы)")
        log(f"OK: сводка за {day} на месте, обложка живая")
        return 0

    # карточки нет, но и событий за сегодня нет → тихий день, это НЕ провал
    if problems == ["card-missing"] and not data_has_today(day):
        log(f"OK: за {day} пока нет событий — сводка не нужна (тихий день)")
        return 0

    if dry:
        log(f"[dry-run] нашёл: {', '.join(problems)}; чинил бы самолечением")
        return 2

    # ===== ТОЛЬКО обложка-заглушка (карточка на месте) =====
    # Косметика: пробуем собрать обложку (Codex-first, обычно чинит). Не смогли
    # (Codex out of credits) → долг-инцидент один раз, без пинга/спама.
    if problems == ["cover-fallback"]:
        _, cover_ok = heal(day)
        if cover_ok:
            update_incidents([], day)
            log(f"обложку за {day} досоздал (Codex)")
            return 0
        if update_incidents(["cover-fallback"], day):
            git_sync(f"watchdog: обложка за {day} — заглушка, Codex не смог (долг)")
        log(f"карточка за {day} на месте; обложка-заглушка (Codex out of credits?)")
        return 0

    # ===== Карточки нет, но события есть → КРИТИЧНО: самолечение =====
    log(f"проблема: нет карточки за {day} (события есть) — самолечение")
    card_ok, cover_ok = heal(day)
    if card_ok:
        update_incidents([], day)                       # закрыть card-инцидент
        note = "" if cover_ok else " (обложка-заглушка, дорисуется на Маке)"
        tg_send(f"🛠 Топливный фронт: сводка за {day} не вышла по расписанию — "
                f"досгенерил автоматически, живая{note}.\n{NEWS_URL}")
        if not cover_ok:                                # оставить долг по обложке
            update_incidents(["cover-fallback"], day)
        log(f"САМОЛЕЧЕНИЕ УСПЕШНО: карточка за {day} собрана; обложка="
            f"{'реальная' if cover_ok else 'заглушка'}")
        return 0

    # карточку собрать не смогли — громкий алерт + инцидент
    changed = update_incidents(["card-missing"], day)
    tg_send(f"🔴 Топливный фронт — сводка за {day} НЕ вышла и самолечение НЕ помогло. "
            f"Нужны руки.\n{NEWS_URL}")
    if changed:
        git_sync(f"watchdog: сводка за {day} — самолечение не помогло, инцидент")
    log(f"ПРОВАЛ: карточка за {day} не собралась | инцидент {'заведён' if changed else 'был'}")
    return 2


def _selfcheck():
    assert check("2026-07-11", 'news/2026-07-11 cover-2026-07-11.png') == []
    assert check("2026-07-11", 'news/2026-07-11 og-image.png') == ["cover-fallback"]
    assert check("2026-07-11", 'news/2026-07-10 only') == ["card-missing"]
    # инбокс: открыть -> идемпотентно -> авто-резолв
    import tempfile
    global INCIDENTS
    d = Path(tempfile.mkdtemp())
    INCIDENTS = d / "incidents.md"
    INCIDENTS.write_text("# t\n\n" + MARKER + "\n")
    assert update_incidents(["card-missing"], "2026-07-11") is True
    assert "## [OPEN] card-missing-2026-07-11" in INCIDENTS.read_text()
    assert update_incidents(["card-missing"], "2026-07-11") is False  # не дублируется
    assert update_incidents([], "2026-07-11") is True                 # авто-резолв
    t = INCIDENTS.read_text()
    assert "## [RESOLVED] card-missing-2026-07-11" in t and "## [OPEN]" not in t, t
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
