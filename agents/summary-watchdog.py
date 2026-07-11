#!/usr/bin/env python3
"""Сторож дневной сводки /news.

Проверяет ЖИВОЙ сайт (не git): вышла ли карточка-сводка за сегодня и стоит ли
на ней реальная обложка (а не заглушка og-image). Пингует в Telegram владельцу
ТОЛЬКО при провале. Ставится в cron на 8:15 и 20:15 МСК — после плановых
сводок 08:00 / 20:00.

Ровно два провала из практики 11.07.2026, которые он ловит:
  A) карточки за сегодня нет на живом /news (сборщик/деплой отстал);
  B) карточка есть, но ссылается на og-image.png — gen-news отработал РАНЬШЕ,
     чем Codex дорисовал обложку (гонка cover->news).

Токен: env NPZ_BOT_TOKEN -> ~/.npz-bot/token. Чат: env NPZ_OWNER_CHAT -> 609952529.
Запуск:  python3 agents/summary-watchdog.py        # тихо, пинг только при проблеме
         python3 agents/summary-watchdog.py --test # принудительный тестовый пинг
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

NEWS_URL = "https://npz-tactical-map.vercel.app/news"
MSK = timezone(timedelta(hours=3))
OWNER_DEFAULT = "609952529"
LOG = Path(__file__).resolve().parent / "logs" / "summary-watchdog.log"


def today_msk() -> str:
    return datetime.now(MSK).strftime("%Y-%m-%d")


def fetch(url: str) -> str:
    # cache-bust + no-cache: смотрим origin, а не edge/браузерный кэш
    bust = f"{url}?wd={int(datetime.now(timezone.utc).timestamp())}"
    req = urllib.request.Request(bust, headers={
        "User-Agent": "npz-summary-watchdog/1",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def get_token() -> str:
    t = os.environ.get("NPZ_BOT_TOKEN", "").strip()
    if t:
        return t
    for p in (Path.home() / ".npz-bot" / "token",):
        if p.exists():
            return p.read_text().strip()
    return ""


def tg_send(text: str) -> bool:
    token = get_token()
    chat = os.environ.get("NPZ_OWNER_CHAT", OWNER_DEFAULT).strip()
    if not token:
        log("НЕТ токена бота — пинг не отправлен")
        return False
    data = urllib.parse.urlencode({
        "chat_id": chat, "text": text, "disable_web_page_preview": "true",
    }).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return json.load(r).get("ok", False)
    except Exception as e:  # noqa: BLE001
        log(f"ошибка отправки TG: {e}")
        return False


def log(msg: str) -> None:
    ts = datetime.now(MSK).strftime("%Y-%m-%d %H:%M МСК")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def check(today: str, html: str):
    """-> (ok: bool, problems: list[str])."""
    problems = []
    if f"news/{today}" not in html:
        problems.append(f"карточки-сводки за {today} НЕТ на живом /news")
        return False, problems  # нет карточки -> обложку проверять незачем
    if f"cover-{today}.png" not in html:
        problems.append(f"карточка за {today} есть, но обложка = заглушка og-image "
                        f"(gen-news отработал раньше Codex-обложки)")
    return (not problems), problems


def main() -> int:
    force = "--test" in sys.argv
    today = today_msk()
    try:
        html = fetch(NEWS_URL)
    except Exception as e:  # noqa: BLE001
        log(f"НЕ достучался до /news: {e}")
        tg_send(f"⚠️ Топливный фронт: сторож сводки не смог открыть {NEWS_URL} ({e}). Проверь сайт.")
        return 1

    ok, problems = check(today, html)

    if force:
        tg_send(f"✅ Тест сторожа сводки. Сегодня {today}: "
                + ("всё на месте." if ok else "ПРОБЛЕМА — " + "; ".join(problems)))
        log("тестовый пинг отправлен")
        return 0

    if ok:
        log(f"OK: сводка за {today} на месте, обложка живая")
        return 0

    msg = ("🔴 Топливный фронт — СВОДКА НЕ ВЫШЛА\n"
           f"Дата: {today}\n" + "\n".join("• " + p for p in problems)
           + f"\n{NEWS_URL}")
    sent = tg_send(msg)
    log(f"ПРОБЛЕМА: {'; '.join(problems)} | пинг {'отправлен' if sent else 'НЕ отправлен'}")
    return 2


def _selfcheck():
    # обложка есть -> ok
    ok, p = check("2026-07-11", 'x href="news/2026-07-11" img="cover-2026-07-11.png" y')
    assert ok and not p, (ok, p)
    # карточка есть, обложка заглушка -> провал B
    ok, p = check("2026-07-11", 'href="news/2026-07-11" img="og-image.png"')
    assert not ok and "заглушка" in p[0], p
    # карточки нет -> провал A
    ok, p = check("2026-07-11", 'href="news/2026-07-10" only')
    assert not ok and "НЕТ на живом" in p[0], p
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
