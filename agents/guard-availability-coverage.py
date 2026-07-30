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
import re
import subprocess
import sys

PATH = "data/fuel-availability.json"

# Сверять имена регионов ПО СМЫСЛУ, а не по строке: агент периодически меняет написание
# («Свердловская обл.» ↔ «Свердловская область»), и сравнение строк принимало такой регион
# за пропавший — доклеивало копию из HEAD и оставляло в файле ДВЕ записи об одном субъекте.
# Нормализация та же, что в app.js normRegion() и agents/validate-azs.py.
RE_REG = re.compile(r"республика|область|обл\.?|край|автономный округ|автономная|город|г\.")


def norm_region(s):
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"[^а-я]", "", RE_REG.sub("", s))


def merge_regions(old, new):
    """Версия агента + недостающие регионы из HEAD. Порядок: свежие, потом восстановленные.
    Доклеиваем при ЛЮБОЙ потере, без порога: раньше падение до 78 из 86 проходило молча
    (10% допуска), и повторяясь, оно уводило покрытие вниз ступеньками 86→78→71→64."""
    have = {norm_region(r.get("region")) for r in new}
    restored = [r for r in old if norm_region(r.get("region")) not in have]
    return new + restored, restored


def _read(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def fix_worktree():
    """Вызывается в crontab СРАЗУ после агента, до git add. Сравнивает рабочий файл
    с последней закоммиченной версией и доклеивает то, что агент не перенёс.
    Так урезанный файл не доживает даже до индекса."""
    head = _read(["git", "show", f"HEAD:{PATH}"])
    try:
        cur = json.load(open(PATH, encoding="utf-8"))
    except Exception:
        return 0                      # агент не дописал файл — не наше дело, поймает JSON-guard
    if not head:
        return 0
    old, new = head.get("regions", []), cur.get("regions", [])
    if len(old) <= 5:
        return 0
    merged, restored = merge_regions(old, new)
    if not restored:
        return 0
    cur["regions"] = merged
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"coverage-fix: агент отдал {len(new)} регионов из {len(old)} — "
          f"доклеено {len(restored)}, итого {len(merged)}.")
    return 0


def main():
    head = _read(["git", "show", f"HEAD:{PATH}"])
    staged = _read(["git", "show", f":{PATH}"])
    if not head or not staged:
        return 0  # первый коммит файла или нечитаемо — не наше дело

    old, new = head.get("regions", []), staged.get("regions", [])
    if len(old) <= 5:
        return 0
    merged, restored = merge_regions(old, new)
    if not restored:
        return 0  # покрытие в норме
    staged["regions"] = merged
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(staged, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"fuel-availability теряла регионы ({len(old)} → {len(new)}) — "
          f"доклеено {len(restored)} из HEAD до {len(merged)}, свежие данные сохранены.")
    return 0


def _selfcheck():
    # Имена берём реальными: norm_region() вырезает всё, кроме кириллицы, поэтому
    # синтетические «Регион1..Регион86» схлопываются в ОДИН ключ и тест ничего не проверяет
    # (на этом он и упал, когда сверку перевели со строк на смысл).
    alphabet = "абвгдежзиклмнопрстуфхцчшщэюя"
    old = [{"region": f"{a}{b}ская область", "level": "old"}
           for a in alphabet for b in alphabet][:86]
    assert len({norm_region(r["region"]) for r in old}) == 86, "имена в тесте не различимы"
    new = [dict(old[0], level="СВЕЖЕЕ")] + [dict(r, level="new") for r in old[1:24]]

    merged, restored = merge_regions(old, new)
    assert len(merged) == 86, f"покрытие не восстановлено: {len(merged)}"
    assert len(restored) == 62, f"доклеено не то число: {len(restored)}"
    assert merged[0]["level"] == "СВЕЖЕЕ", "свежие данные агента затёрты"
    names = [r["region"] for r in merged]
    assert len(names) == len(set(names)), "появились дубли регионов"

    # покрытие в норме — доклеивать нечего
    _, none_restored = merge_regions(old, list(old))
    assert not none_restored, "вмешался там, где всё на месте"

    # переименование НЕ создаёт вторую запись об одном субъекте
    ren_old = [{"region": "Свердловская область", "level": "old"},
               {"region": "Тульская область", "level": "old"}]
    ren_new = [{"region": "Свердловская обл.", "level": "СВЕЖЕЕ"}]
    ren_merged, ren_restored = merge_regions(ren_old, ren_new)
    assert [r["region"] for r in ren_restored] == ["Тульская область"], \
        f"переименованный регион принят за пропавший: {[r['region'] for r in ren_restored]}"
    keys = [norm_region(r["region"]) for r in ren_merged]
    assert len(keys) == len(set(keys)), f"дубль по смыслу: {[r['region'] for r in ren_merged]}"

    # малая потеря (85 из 86) больше не проходит молча
    _, small = merge_regions(old, old[:85])
    assert len(small) == 1, f"потеря одного региона не замечена: {len(small)}"

    print("selfcheck OK: 86→24 доклеивается до 86; переименование не даёт дубля; "
          "потеря даже одного региона замечена; свежее сохраняется")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    elif "--fix-worktree" in sys.argv:
        sys.exit(fix_worktree())
    else:
        sys.exit(main())
