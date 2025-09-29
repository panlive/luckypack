#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LuckyBot/ceai_bridge.py — мост между ботом и CEAI

Назначение:
  Из бота (хэндлеры, сценарии) вызывать единый метод
  для применения событий user.update (email/phone)
  в реестре CEAI.

Пример вызова:
  from LuckyBot.ceai_bridge import ceai_apply_event
  ok, msg = ceai_apply_event(
      reg_dir="/srv/luckypack/data/clients/registry",
      tgid=message.from_user.id,
      field="phone",
      value="8 999 123-45-67"
  )
"""
from __future__ import annotations
import os
from typing import Tuple

from CEAI import upsert


def ceai_apply_event(reg_dir: str, tgid: int, field: str, value: str, source: str = "telegram") -> Tuple[bool, str]:
    """
    Применяет событие user.update (email/phone) для клиента по telegram_user_id.

    Args:
        reg_dir: путь к корню CEAI-реестра
        tgid: telegram_user_id
        field: "email" или "phone"
        value: значение
        source: источник (по умолчанию "telegram")

    Returns:
        (ok, msg): bool, str
    """
    canon = upsert.resolve_canonical_by_tg(reg_dir, str(tgid))
    base = os.path.join(reg_dir, "by_id", canon)

    ev = {
        "type": "user.update",
        "source": source,
        "payload": {
            "telegram_user_id": tgid,
            "field": field,
            "value": value,
            "verified": True
        }
    }
    upsert.append_event(base, ev)

    if field == "email":
        return upsert.apply_user_update_email(reg_dir, canon, ev)
    elif field == "phone":
        return upsert.apply_user_update_phone(reg_dir, canon, ev)
    else:
        return False, f"unsupported field: {field}"