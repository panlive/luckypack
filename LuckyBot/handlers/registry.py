#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registry.py — работа с общим реестром клиентов LuckyPack.

Назначение:
    • Хранить список всех зарегистрированных клиентов.
    • Обновлять или добавлять запись по ИНН.
    • Используется registration_flow.py для записей в реестр.
    • Не содержит никакой Telegram-логики, только файловые операции.

Структура registry.json:
{
  "7707083893": {
    "short_name": "...",
    "full_name": "...",
    "registered_at": "2025-11-22 19:35:00",
    "profile_path": "/app/data/clients_registry/profiles/7707083893.json",
    "date_added": "2025-11-22 19:35:00",
    "history": []
  },
  ...
}
"""

import os
import json
from datetime import datetime

# Корневой путь реестра
DATA_ROOT = "/app/data/clients_registry"
REGISTRY_PATH = os.path.join(DATA_ROOT, "registry.json")

os.makedirs(DATA_ROOT, exist_ok=True)


def _load_registry() -> dict:
    """Загрузка registry.json. Если файла нет — создаётся пустой реестр."""
    if not os.path.exists(REGISTRY_PATH):
        return {}

    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Если файл повреждён, начинаем с чистого
        return {}


def _save_registry(data: dict):
    """Сохранение registry.json с форматированием."""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def upsert_company(profile: dict, profile_path: str) -> None:
    """
    Добавить или обновить запись о компании в registry.json.

    profile — нормализованный профиль компании (из registration_normalize.py)
    profile_path — путь к файлу профиля (JSON)
    """
    inn = profile.get("inn")
    if not inn:
        raise ValueError("Профиль не содержит ИНН — невозможно обновить registry.json")

    registry = _load_registry()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record = registry.get(inn, {
        "date_added": now,
        "history": []
    })

    # Обновляем основные поля
    record["short_name"] = profile.get("short_name")
    record["full_name"] = profile.get("full_name")
    record["registered_at"] = now
    record["profile_path"] = profile_path

    registry[inn] = record
    _save_registry(registry)