#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Разовый тест: применить событие user.update(phone) к твоей карточке CEAI
и показать, что номер записался в client.json и индекс by_phone.

Запуск:
  python3 /tmp/apply_phone_once.py
"""
from __future__ import annotations
import sys, os, json

APP_ROOT = "/srv/luckypack/App"
REG      = "/srv/luckypack/data/clients/registry"
TGID     = 815549184
RAW_PHONE= "8 999 123-45-67"

# Делаем импорт CEAI надёжным
sys.path[:0] = [APP_ROOT]
from CEAI import upsert

print("uses ClientCards normalize?:", bool(upsert.cc_normalize_phone_ru))
print("normalize_phone(\"%s\") ->" % RAW_PHONE, upsert.normalize_phone(RAW_PHONE))

# Готовим событие
ev = {
  "type": "user.update",
  "source": "telegram",
  "payload": {
    "telegram_user_id": TGID,
    "field": "phone",
    "value": RAW_PHONE,
    "verified": True
  }
}

# Применяем к карточке
canon = upsert.resolve_canonical_by_tg(REG, str(TGID))
base  = os.path.join(REG, 'by_id', canon)
upsert.append_event(base, ev)
ok, msg = upsert.apply_user_update_phone(REG, canon, ev)
print("apply_user_update_phone:", ok, msg, "| canon:", canon)

# Проверяем client.json
client_p = os.path.join(base, "client.json")
j = json.load(open(client_p, encoding="utf-8"))
phone_val = (j.get("contacts") or {}).get("phone", {}).get("value")
print("client.contacts.phone.value ->", phone_val)

# Проверяем index.json
idx = json.load(open(os.path.join(REG, "index.json"), encoding="utf-8"))
by_phone = idx.get("by_phone") or {}
print("index.by_phone has +79991234567:", "+79991234567" in by_phone)
print("index.by_phone[+79991234567] ->", by_phone.get("+79991234567"))
