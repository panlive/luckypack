#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает все *.json из LuckyPricer/data/jsons/ в единый products.json.
Правила:
- ключ "Штрихкод" всегда выбрасывается;
- поле "Артикул" обязательно (строка, не пустая);
  если в записи нет "Артикул", но есть "Штрихкод" — копируем его в "Артикул" и Штрихкод НЕ сохраняем;
- порядок детерминированный: сортируем по "Артикул".
Лог в stdout: "готово: N; первые: A1, A2, A3".
"""
import json, glob, os, sys

SRC_DIR = "/srv/luckypack/project/LuckyPricer/data/jsons"
OUT_FP  = "/srv/luckypack/project/LuckyPricer/products.json"

def normalize_item(it: dict) -> dict:
    it = dict(it)  # копия
    # забираем штрихкод до удаления
    bc = it.get("Штрихкод")
    # удаляем "Штрихкод" в любом регистре ключа
    for k in list(it.keys()):
        if str(k).lower() == "штрихкод":
            it.pop(k, None)
    # гарантия "Артикул"
    art = str(it.get("Артикул","")).strip()
    if not art and bc:
        art = str(bc).strip()
    if not art:
        return None  # запись бракуем — без артикула нам не нужна
    it["Артикул"] = art
    return it

def load_any_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def main() -> int:
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.json")))
    items = []
    for fp in files:
        data = load_any_json(fp)
        if data is None:
            continue
        if isinstance(data, list):
            for r in data:
                if isinstance(r, dict):
                    r2 = normalize_item(r)
                    if r2: items.append(r2)
        elif isinstance(data, dict):
            r2 = normalize_item(data)
            if r2: items.append(r2)
        # всё остальное игнорируем молча
    # детерминируем порядок
    items.sort(key=lambda x: x.get("Артикул",""))
    # запись
    with open(OUT_FP, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    first3 = [it["Артикул"] for it in items[:3]]
    print(f"готово: {len(items)}; первые: {', '.join(first3)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
