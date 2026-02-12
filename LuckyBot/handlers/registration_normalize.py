#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registration_normalize.py — нормализация карточки клиента из DaData.

Этап 1 (уже есть):
  registration_api.fetch_company_raw(inn) ->
    сохраняет "сырые" данные DaData в:
      /app/data/clients_registry/raw_dadata/<ИНН>.json

Этап 2 (этот файл):
  normalize_company(inn):
    • читает raw_dadata/<ИНН>.json
    • берёт первый элемент из suggestions[]
    • вытаскивает ключевые поля (ИНН, КПП, ОГРН, имена, адрес, статус и т.п.)
    • пытается достать телефон/почту, если они есть
    • сохраняет аккуратный профиль в:
        /app/data/clients_registry/profiles/<ИНН>.json
    • возвращает профиль как dict
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from LuckyBot.handlers.registration_registry import upsert_company

RAW_DIR = Path("/srv/luckypack/data/clients_registry/raw_dadata")
PROFILE_DIR = Path("/srv/luckypack/data/clients_registry/profiles")


def _ms_to_iso_date(ms: Optional[int]) -> Optional[str]:
    """Переводит миллисекунды Unix (из DaData) в YYYY-MM-DD."""
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except Exception:
        return None


def _first_or_none(seq: Any, key: str = "value") -> Optional[str]:
    """
    Берём первый элемент из списка словарей (phones/emails)
    и достаём поле key (обычно "value").
    """
    if not isinstance(seq, (list, tuple)) or not seq:
        return None
    item = seq[0]
    if isinstance(item, dict):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _load_raw(inn: str) -> Dict[str, Any]:
    """Читает RAW-файл DaData по ИНН."""
    path = RAW_DIR / f"{inn}.json"
    if not path.exists():
        raise FileNotFoundError(f"RAW-файл DaData не найден: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_company(inn: str) -> Dict[str, Any]:
    """
    Основная функция нормализации.

    На вход: ИНН (строка).
    На выход: dict с аккуратным профилем + запись в profiles/<ИНН>.json.
    """
    raw = _load_raw(inn)
    suggestions = raw.get("suggestions") or []
    if not suggestions:
        raise ValueError(f"В RAW-данных DaData нет suggestions для ИНН {inn}")

    # Берём первую подсказку как основную
    s0 = suggestions[0]
    data = s0.get("data") or {}

    name = data.get("name") or {}
    addr = data.get("address") or {}
    addr_data = addr.get("data") or {}
    state = data.get("state") or {}

    # Основные реквизиты
    inn_val = data.get("inn") or inn
    kpp = data.get("kpp")
    ogrn = data.get("ogrn")

    # Названия
    name_full_with_opf = name.get("full_with_opf")
    name_short_with_opf = name.get("short_with_opf")
    name_full = name.get("full")
    name_short = name.get("short")

    # Адрес (человеческий)
    address_full = addr.get("unrestricted_value") or addr.get("value")

    # Статус и даты
    state_status = state.get("status")  # ACTIVE, LIQUIDATED и т.п.
    registration_date = _ms_to_iso_date(state.get("registration_date"))
    actuality_date = _ms_to_iso_date(state.get("actuality_date"))

    # ОКВЭД
    okved = data.get("okved")

    # Руководитель
    management = data.get("management") or {}
    management_name = management.get("name")
    management_post = management.get("post")

    # Контакты (если DaData их отдаёт)
    phone = _first_or_none(data.get("phones") or [])
    email = _first_or_none(data.get("emails") or [])

    # Служебное
    now_utc = datetime.now(tz=timezone.utc).isoformat()

    profile: Dict[str, Any] = {
        "inn": inn_val,
        "kpp": kpp,
        "ogrn": ogrn,

        "name_full_with_opf": name_full_with_opf,
        "name_short_with_opf": name_short_with_opf,
        "name_full": name_full,
        "name_short": name_short,

        "address_full": address_full,
        "address_postal_code": addr_data.get("postal_code"),
        "address_region": addr_data.get("region_with_type"),
        "address_city": addr_data.get("city_with_type") or addr_data.get("settlement_with_type"),
        "address_fias_id": addr_data.get("fias_id"),

        "state_status": state_status,
        "registration_date": registration_date,
        "actuality_date": actuality_date,

        "okved": okved,

        "management_name": management_name,
        "management_post": management_post,

        "phone": phone,
        "email": email,

        "_source": {
            "dadata_hid": data.get("hid"),
            "dadata_type": data.get("type"),
        },
        "_meta": {
            "created_utc": now_utc,
            "source": "dadata_findById_party",
        },
    }

    # Создаём директорию и пишем аккуратный профиль
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROFILE_DIR / f"{inn_val}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    # Добавляем запись в общий реестр клиентов
    upsert_company(profile, f"data/clients_registry/profiles/{inn_val}.json")    

    return profile


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Использование: python -m LuckyBot.handlers.registration_normalize <ИНН>")
        sys.exit(1)

    inn_arg = sys.argv[1].strip()
    prof = normalize_company(inn_arg)
    print(json.dumps(prof, ensure_ascii=False, indent=2))