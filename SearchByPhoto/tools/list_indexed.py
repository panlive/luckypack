#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
list_indexed.py — печатает уже ПРОИНДЕКСИРОВАННЫЕ id (артикулы) из img_ids.npy.

ЗАДАЧА
- Прочитать файл индекса id: /srv/luckypack/project/SearchByPhoto/index/img_ids.npy
- Аккуратно декодировать элементы (bytes → utf-8) и обрезать пробелы
- Напечатать по одному id в строке (уникальные, отсортированные — чтобы удобно сравнивать)

ВЫХОД
- STDOUT: по одному id (артикулу) в строке
- RC=0 всегда:
  • если файл отсутствует/пустой/битый — молча печатает НИЧЕГО и выходит с 0
  • если всё ок — печатает id

КОНТЕКСТ
- Используется в nightly_photo_rebuild.sh:
    VALID = (CANDIDATES ∩ PRODUCTS) \ INDEXED
  где:
    INDEXED — результат ЭТОГО скрипта.
"""

import os
import sys
import numpy as np

IDS = "/srv/luckypack/project/SearchByPhoto/index/img_ids.npy"


def main() -> int:
    if not os.path.isfile(IDS) or os.path.getsize(IDS) == 0:
        return 0
    try:
        arr = np.load(IDS, allow_pickle=True).tolist()
    except Exception:
        # файл битый — не шумим (по ТЗ), просто «как будто индекса нет»
        return 0

    seen = set()
    out = []
    for it in arr:
        if isinstance(it, (bytes, bytearray)):
            s = it.decode("utf-8", "ignore").strip()
        else:
            s = str(it).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    out.sort()
    for s in out:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
