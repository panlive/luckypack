#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
list_candidates.py — даёт список «кандидатов к индексации» по фото.

ЗАДАЧА
- Пройти по /app/data/photos/vectorized
- Взять все файлы с расширением .webp
- Напечатать ИМЕНА БЕЗ .webp, которые выглядят как корректные артикулы:
  • без пробелов
  • без скобок (никаких "(1)", "(2)" — это дубли)
  • только [0-9 A-Za-z - _]

ВЫХОД
- STDOUT: по одному артикулу в строке.
- RC=0 при успехе; RC=1, если папка vectorized отсутствует.

КОНТЕКСТ
- Используется в nightly_photo_rebuild.sh в формуле:
    VALID = (CANDIDATES ∩ PRODUCTS) \ INDEXED
  где:
    CANDIDATES — этот скрипт,
    PRODUCTS   — артикулы из products.json,
    INDEXED    — уже проиндексированные id из img_ids.npy.
"""

import os
import sys

VECT = "/app/data/photos/vectorized"


def is_article_name(name: str) -> bool:
    """Правило валидации артикула по имени файла (без .webp)."""
    if not name:
        return False
    if "(" in name or ")" in name or " " in name:
        return False
    for ch in name:
        if not (ch.isalnum() or ch in "-_"):
            return False
    return True


def main() -> int:
    if not os.path.isdir(VECT):
        return 1
    out = []
    for fname in os.listdir(VECT):
        if not fname.endswith(".webp"):
            continue
        base = fname[:-5]
        if is_article_name(base):
            out.append(base)
    for a in out:
        print(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
