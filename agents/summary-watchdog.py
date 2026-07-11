#!/usr/bin/env python3
"""Сторож дневной сводки /news.

Проверяет ЖИВОЙ сайт (не git): вышла ли карточка-сводка за сегодня и стоит ли
на ней реальная обложка (а не заглушка og-image). При провале:
  1) пингует владельцу в Telegram;
  2) заводит OPEN-инцидент в docs/agents/incidents.md с конкретными шагами фикса
     и коммитит его через git-sync -> Hermes подхватит на следующем `git pull`
     (см. HERMES.md §0, шаг 1a) и починит.
Когда проблема исчезает — сам закрывает свой инцидент (RESOLVED (авто)).
Ставится в cron на 8:15 и 20:15 МСК — после плановых сводок 08:00 / 20:00.

Ловит два реальных провала из практики 11.07.2026:
  card-missing  — карточки за сегодня нет на живом /news;
  cover-fallback— карточка есть, но обложка = og-image (гонка cover->news).

Токен: env NPZ_BOT_TOKEN -> ~/.npz-bot/token. Чат: env NPZ_OWNER_CHAT -> 609952529.
Запуск:  python3 agents/summary-watchdog.py         # тихо; пинг+инцидент только при проблеме
         python3 agents/summary-watchdog.py --test  # тестовый пинг, без инцидента/git
         python3 agents/summary-watchdog.py --selfcheck
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
    return (f"Карточка за {day} есть, но обложка = заглушка og-image "
            "(gen-news отработал раньше Codex-обложки).\n"
            "Что сделать:\n"
            f"- если assets/cover-{day}.png существует → `python3 agents/gen-news.py` "
            "+ git-sync (подхватит обложку, деплой автоматом);\n"
            f"- если файла нет → `python3 hermes/scripts/build-covers.py --dates {day}` "
            "(Codex image_gen), затем gen-news.")


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


# ---- main -------------------------------------------------------------------
def main() -> int:
    day = today()
    if "--test" in sys.argv:
        tg_send(f"✅ Тест сторожа сводки. Проверяю {NEWS_URL} за {day}.")
        log("тестовый пинг отправлен")
        return 0
    try:
        html = fetch(NEWS_URL)
    except Exception as e:  # noqa: BLE001
        log(f"НЕ достучался до /news: {e}")
        tg_send(f"⚠️ Сторож сводки не смог открыть {NEWS_URL} ({e}).")
        return 1

    problems = check(day, html)
    incidents_changed = update_incidents(problems, day)

    if not problems:
        if incidents_changed:      # что-то авто-зарезолвилось
            git_sync(f"watchdog: сводка за {day} восстановлена — закрыл инцидент(ы)")
            log(f"OK: сводка за {day} на месте; закрыл прежний инцидент")
        else:
            log(f"OK: сводка за {day} на месте, обложка живая")
        return 0

    labels = {"card-missing": "нет карточки-сводки",
              "cover-fallback": "обложка = заглушка og-image"}
    what = "; ".join(labels.get(k, k) for k in problems)
    tg_send(f"🔴 Топливный фронт — сводка за {day} НЕ вышла: {what}.\n"
            f"Завёл инцидент Гермесу (docs/agents/incidents.md), починит на heartbeat.\n{NEWS_URL}")
    if incidents_changed:
        git_sync(f"watchdog: сводка за {day} не вышла ({what}) — инцидент Гермесу")
    log(f"ПРОБЛЕМА: {what} | инцидент {'заведён' if incidents_changed else 'уже был'}")
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
