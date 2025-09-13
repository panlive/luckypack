#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
list_product_articles.py — печатает ВСЕ артикулы из products.json.

ЗАДАЧА
- Прочитать /srv/luckypack/project/LuckyPricer/products.json
- Взять поле "Артикул" у каждой записи (если есть)
- Напечатать по одному артикулу в строке (уникальность/сортировку делает вызывающий скрипт)

ВЫХОД
- STDOUT: артикулы (по одному в строке)
- RC=0 при успехе; RC=0 и пустой вывод — если файл пуст/отсутствует/не читается (молчим, не падаем)

КОНТЕКСТ
- Используется в nightly_photo_rebuild.sh:
    VALID = (CANDIDATES ∩ PRODUCTS) \ INDEXED
  где:
    PRODUCTS — результат ЭТОГО скрипта (артикулы из products.json)
"""

import json
import os
import sys

PROD = "/srv/luckypack/project/LuckyPricer/products.json"


def main() -> int:
    if not os.path.isfile(PROD) or os.path.getsize(PROD) == 0:
        return 0
    try:
        data = json.load(open(PROD, "r", encoding="utf-8"))
    except Exception:
        # не шумим — пустой вывод, RC=0
        return 0

    out = []
    if isinstance(data, list):
        for rec in data:
            if isinstance(rec, dict):
                v = str(rec.get("Артикул", "")).strip()
                if v:
                    out.append(v)
    elif isinstance(data, dict):
        v = str(data.get("Артикул", "")).strip()
        if v:
            out.append(v)

    for a in out:
        print(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
