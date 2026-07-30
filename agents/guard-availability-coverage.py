#!/usr/bin/env python3
"""Страж покрытия data/fuel-availability.json — регионы не должны пропадать.

Зовётся из .githooks/pre-commit. Сравнивает staged-версию с версией в HEAD:
если регионов стало меньше чем на 10%, ДОКЛЕИВАЕТ пропавшие из HEAD и
перезаписывает рабочий файл. Свежие данные агента при этом сохраняются —
берётся его версия региона, из HEAD добавляются только отсутствующие.

Почему доклейка, а не блокировка:
  27.07 агент отдал 13 регионов вместо 88 — 6131 АЗС посерели на 4 суток.
  30.07 повторилось (24 вместо 86), и плохая версия упёрлась в конфликт,
  заклинив git-sync на 13 часов (rebase застрял на шаге 18/72, флот коммитил
  в пустоту). Файл едет в общем коммите git-sync вместе с радаром, поэтому
  exit 1 остановил бы публикацию целиком — лечение оказалось бы хуже болезни.

Печатает одну строку для лога хука, если вмешался; молчит, если всё в норме.
Самопроверка: python3 agents/guard-availability-coverage.py --selfcheck
"""
import json
import subprocess
import sys

PATH = "data/fuel-availability.json"
KEEP_RATIO = 0.9  # падение больше чем на 10% считаем аварией


def merge_regions(old, new):
    """Версия агента + недостающие регионы из HEAD. Порядок: свежие, потом восстановленные."""
    have = {r.get("region") for r in new}
    restored = [r for r in old if r.get("region") not in have]
    return new + restored, restored


def _read(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def main():
    head = _read(["git", "show", f"HEAD:{PATH}"])
    staged = _read(["git", "show", f":{PATH}"])
    if not head or not staged:
        return 0  # первый коммит файла или нечитаемо — не наше дело

    old, new = head.get("regions", []), staged.get("regions", [])
    if len(old) <= 5 or len(new) >= int(len(old) * KEEP_RATIO):
        return 0  # покрытие в норме

    merged, restored = merge_regions(old, new)
    staged["regions"] = merged
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(staged, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"fuel-availability теряла регионы ({len(old)} → {len(new)}) — "
          f"доклеено {len(restored)} из HEAD до {len(merged)}, свежие данные сохранены.")
    return 0


def _selfcheck():
    old = [{"region": f"Регион{i}", "level": "old"} for i in range(86)]
    new = [{"region": "Регион0", "level": "СВЕЖЕЕ"}] + \
          [{"region": f"Регион{i}", "level": "new"} for i in range(1, 24)]

    merged, restored = merge_regions(old, new)
    assert len(merged) == 86, f"покрытие не восстановлено: {len(merged)}"
    assert len(restored) == 62, f"доклеено не то число: {len(restored)}"
    assert merged[0]["level"] == "СВЕЖЕЕ", "свежие данные агента затёрты"
    names = [r["region"] for r in merged]
    assert len(names) == len(set(names)), "появились дубли регионов"

    # покрытие в норме — не вмешиваемся
    ok_new = [{"region": f"Регион{i}"} for i in range(80)]
    assert len(ok_new) >= int(len(old) * KEEP_RATIO), "порог сдвинулся: 80 из 86 — это норма"

    # граница: 77 из 86 — ещё норма, 76 — уже авария
    assert 77 >= int(86 * KEEP_RATIO) > 76
    print("selfcheck OK: 86→24 доклеивается до 86, свежее сохраняется, дублей нет")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        sys.exit(main())
