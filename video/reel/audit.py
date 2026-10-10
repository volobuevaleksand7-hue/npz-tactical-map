#!/usr/bin/env python3
"""Аудит собранного рилса по эталону 04.10. Использование: audit.py YYYY-MM-DD [reel|urgent]
Код 1 — жёсткий провал (публиковать нельзя): нет голоса, длина вне 30–90 с, заголовок с ошибкой падежа,
реплики не по формату. Предупреждения (мало ударов, нет клипов) только печатаются."""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_reel as B  # noqa: E402


def audit(date, build: Path):
    hard, warn = [], []
    nar = json.loads((build / "narration.json").read_text(encoding="utf-8"))
    plan = json.loads((build / "plan.json").read_text(encoding="utf-8"))
    clips = json.loads((build / "clips.json").read_text(encoding="utf-8"))
    nar = nar[:plan.get("n_strikes", len(nar))]   # только удары, попавшие в ролик
    for i, x in enumerate(nar):
        for p in B.line_problems(x):
            hard.append(f"реплика {i}: {p}: {x[:70]!r}")
    if len(plan.get("voice", [])) < len(nar) + 2:
        hard.append(f"голос: озвучено {len(plan.get('voice', []))} из {len(nar) + 2} реплик")
    lo = 12 if build.name.startswith("urgent-") else 30   # срочный — один удар
    # 60 → 90 с (07.10): с клипами очевидцев день из 9 ударов — 70 с; Shorts принимает до 3 мин
    hi = 60   # цель ~45 с (REEL_MAX_SEC); 60 — жёсткий потолок
    if not lo <= plan.get("total", 0) <= hi:
        hard.append(f"длительность {plan.get('total')} с вне {lo}–{hi}")
    desc = (build / "description.txt").read_text(encoding="utf-8").splitlines()[0]
    if re.search(r"\bпо [А-ЯЁ][а-яё]+(ая|яя|ое|ее) ", desc):
        hard.append(f"заголовок: падеж: {desc!r}")
    if len(nar) < 3 and not build.name.startswith("urgent-"):
        warn.append(f"мало ударов: {len(nar)} (эталон — 5)")
    # ── чужие кадры (лимит 10.10.2026, см. build_reel.FOREIGN_*) ──
    total = float(plan.get("total", 0)) or 1.0
    foreign = plan.get("foreign", [])
    for f in foreign:
        if float(f["dur"]) > B.FOREIGN_SEG_MAX + 0.05:
            hard.append(f"чужой фрагмент {f['i']}: {f['dur']} с > {B.FOREIGN_SEG_MAX} с")
        if not str(f.get("caption") or "").strip() or f.get("caption") == "открытые источники":
            hard.append(f"чужой фрагмент {f['i']}: нет подписи источника ({f.get('src')!r})")
    share = float(plan.get("foreign_share", 0))
    if share > B.FOREIGN_MAX_SHARE + 0.001:
        hard.append(f"чужих кадров {share:.0%} длины ролика > {B.FOREIGN_MAX_SHARE:.0%}")
    elif share > B.FOREIGN_WARN_SHARE:
        warn.append(f"чужих кадров {share:.0%} длины ролика — близко к лимиту {B.FOREIGN_MAX_SHARE:.0%}")
    # ── контекст в кадре и финальная плашка ──
    page = (build / "index.html").read_text(encoding="utf-8")
    if B.CTX_ON:
        if plan.get("ctx_lines", 0) < plan.get("n_strikes", 0) or "ОЦЕНКА</div>" not in page:
            hard.append("нет строки контекста «место · дата · источник · ОЦЕНКА» на сценах ударов")
        if "ссылка в шапке канала" not in page:
            hard.append("нет финальной плашки «Карта — ссылка в шапке канала»")
    got = sum(1 for c in clips if c)
    if not got:
        warn.append("нет ни одного клипа (карта и плашки без кадров)")
    return hard, warn


if __name__ == "__main__":
    date = sys.argv[1]
    kind = sys.argv[2] if len(sys.argv) > 2 else "reel"
    hard, warn = audit(date, HERE.parent / ".build" / f"{kind}-{date}")
    for w in warn:
        print(f"audit WARN: {w}")
    for h in hard:
        print(f"audit FAIL: {h}")
    print(f"audit {date}: {'FAIL' if hard else 'OK'} ({len(hard)} жёстких, {len(warn)} предупреждений)")
    sys.exit(1 if hard else 0)
