#!/usr/bin/env python3
import argparse
import html
import json
import re
import urllib.request


def strip_tags(value):
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def is_ru(text):
    text = str(text or "")
    cyr = sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in text)
    lat = sum("a" <= c.lower() <= "z" for c in text)
    return cyr >= lat and cyr > 0


def parse_tme_posts(page_html):
    posts = []
    pattern = re.compile(
        r'<div class="[^"]*tgme_widget_message[^"]*"[^>]*data-post="[^/"]+/(\d+)"[^>]*>(.*?)'
        r'(?=<div class="[^"]*tgme_widget_message[^"]*"[^>]*data-post=|\Z)',
        re.S,
    )
    for match in pattern.finditer(page_html or ""):
        message_id = int(match.group(1))
        block = match.group(2)
        dt = ""
        dt_match = re.search(r'<time[^>]*datetime="([^"]+)"', block)
        if dt_match:
            dt = html.unescape(dt_match.group(1))
        text = ""
        text_match = re.search(r'<div class="[^"]*tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.S)
        if text_match:
            text = strip_tags(text_match.group(1))
        posts.append({
            "message_id": message_id,
            "url": "https://t.me/NPZmap/%d" % message_id,
            "datetime": dt,
            "text": text,
        })
    return posts


def normalized_text(text):
    text = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    return re.sub(r"[^0-9a-zа-яё ]+", "", text)


def audit_posts(posts):
    seen = {}
    candidates = []
    for post in posts:
        reasons = []
        text = post.get("text", "")
        norm = normalized_text(text)
        if text and not is_ru(text):
            reasons.append("english_or_mixed")
        if any(word in norm for word in ("test", "тест", "служебн", "debug", "dry run")):
            reasons.append("service_or_test")
        if norm in seen:
            reasons.append("duplicate_text")
        elif norm:
            seen[norm] = post.get("message_id")
        editorial_markers = ("главное", "почему важно", "статус", "мониторинг")
        generic_digest = "сводка" in norm or "топливный фронт рф" in norm
        if generic_digest and not any(marker in norm for marker in editorial_markers):
            reasons.append("weak_no_main_point")
        if reasons:
            candidates.append({
                "message_id": post.get("message_id"),
                "url": post.get("url"),
                "datetime": post.get("datetime"),
                "snippet": text[:180].replace("\n", " "),
                "reasons": reasons,
                "action": "review_delete_candidate",
            })
    return candidates


def render_markdown(candidates):
    lines = ["| message_id | date | reason | snippet | url |", "|---:|---|---|---|---|"]
    for c in candidates:
        lines.append("| %s | %s | %s | %s | %s |" % (
            c["message_id"], c.get("datetime", ""), ", ".join(c["reasons"]),
            str(c.get("snippet", "")).replace("|", "/"), c.get("url", "")))
    return "\n".join(lines)


def load_html(args):
    if args.html:
        with open(args.html, encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(args.url, headers={"User-Agent": "NPZ-channel-audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser(description="Read-only audit of @NPZmap Telegram posts.")
    parser.add_argument("--html", help="Local t.me/s HTML file")
    parser.add_argument("--url", default="https://t.me/s/NPZmap", help="Public Telegram web URL")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument("--limit", type=int, default=0, help="Limit posts after parsing")
    args = parser.parse_args()

    posts = parse_tme_posts(load_html(args))
    if args.limit:
        posts = posts[-args.limit:]
    candidates = audit_posts(posts)
    if args.json:
        print(json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(candidates))


if __name__ == "__main__":
    main()
