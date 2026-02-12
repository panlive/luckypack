"""
registration_registry.py — работа с реестром клиентов LuckyPack (registry.json).

Задача файла:
- вести единый JSON-реестр клиентов по ИНН;
- добавлять/обновлять запись после успешной нормализации профиля;
- хранить минимальный набор полей, достаточный для бота.

Где хранится реестр:
- внутри контейнера: /app/data/clients_registry/registry.json
- на хосте:        /srv/luckypack/data/clients_registry/registry.json
  (примонтировано в контейнер как /app/data)

Как использовать:
1. В нормализаторе (registration_normalize.py) после сохранения профиля:
   - загрузить словарь профиля (profile: dict);
   - вызвать upsert_company(profile).

2. Функция upsert_company:
   - по ключу "inn" добавляет или обновляет запись в registry.json;
   - не дублирует клиентов при повторных вызовах;
   - аккуратно перезаписывает файл (через временный .tmp).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


# Абсолютный путь внутри контейнера. Через volume мапится на /srv/luckypack/data/clients_registry.
REGISTRY_PATH = Path("/app/data/clients_registry/registry.json")


@dataclass
class CompanyRegistryEntry:
    """
    Структура одной записи в registry.json.

    Храним:
    - short_name      — короткое имя (для интерфейса бота)
    - full_name       — полное юридическое наименование
    - registered_at   — дата регистрации из профиля (если есть)
    - profile_path    — относительный путь к профилю внутри /app
    - date_added      — когда впервые появился клиент в реестре
    - date_updated    — когда запись обновлялась последний раз
    - history         — список произвольных событий (зарезервировано на будущее)
    """

    short_name: str
    full_name: str
    registered_at: str | None
    profile_path: str
    date_added: str
    date_updated: str
    history: list[Any]


def _load_registry() -> Dict[str, Dict[str, Any]]:
    """Загрузить текущий registry.json. Если файла нет — вернуть пустой словарь."""
    if not REGISTRY_PATH.exists():
        return {}

    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError("registry.json повреждён: корень должен быть объектом (dict).")

    return data


def _save_registry(registry: Dict[str, Dict[str, Any]]) -> None:
    """
    Сохранить registry.json безопасно:
    - пишем во временный файл *.tmp;
    - затем атомарно заменяем основной файл.
    """
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = REGISTRY_PATH.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    tmp_path.replace(REGISTRY_PATH)


def upsert_company(profile: Dict[str, Any], profile_rel_path: str | None = None) -> None:
    """
    Добавить или обновить компанию в registry.json на основании нормализованного профиля.

    Ожидается формат профиля (минимально важные поля):
    - profile["inn"]                 — ИНН
    - profile["name_short"]         — короткое имя (если есть)
    - profile["name_full"]          — полное имя (если есть)
    - profile["registration_date"]  — дата регистрации (опционально)

    :param profile: словарь нормализованного профиля компании.
    :param profile_rel_path: относительный путь к JSON-профилю внутри /app
                             (по умолчанию: "data/clients_registry/profiles/{inn}.json").
    """
    inn = profile.get("inn")
    if not inn:
        raise ValueError("Профиль не содержит 'inn' — невозможно добавить в registry.json")

    # Имя для интерфейса бота — сначала короткое, потом fallback на полное.
    short_name = (
        profile.get("name_short")
        or profile.get("name_short_with_opf")
        or profile.get("name_full")
        or profile.get("name_full_with_opf")
        or inn
    )
    full_name = (
        profile.get("name_full")
        or profile.get("name_full_with_opf")
        or short_name
    )

    registered_at = profile.get("registration_date")
    now_iso = datetime.now(timezone.utc).isoformat()

    registry = _load_registry()

    existing = registry.get(inn, {})
    date_added = existing.get("date_added", now_iso)
    history = existing.get("history", [])

    entry = CompanyRegistryEntry(
        short_name=str(short_name),
        full_name=str(full_name),
        registered_at=registered_at,
        profile_path=profile_rel_path or f"data/clients_registry/profiles/{inn}.json",
        date_added=date_added,
        date_updated=now_iso,
        history=history,
    )

    # Преобразуем dataclass в обычный dict и сохраняем
    registry[inn] = {
        "short_name": entry.short_name,
        "full_name": entry.full_name,
        "registered_at": entry.registered_at,
        "profile_path": entry.profile_path,
        "date_added": entry.date_added,
        "date_updated": entry.date_updated,
        "history": entry.history,
    }

    _save_registry(registry)