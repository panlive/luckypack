#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_upsert_event.py — простой раннер одного события CEAI

Назначение:
  Прочитать событие user.update (email/phone) из JSON и применить его к реестру CEAI,
  минуя CLI-обвязку. Печатает понятный результат и короткую сводку.

Запуск:
  python3 /srv/luckypack/App/CEAI/run_upsert_event.py /tmp/ev_phone.json /srv/luckypack/data/clients/registry
  python3 /srv/luckypack/App/CEAI/run_upsert_event.py /tmp/ev_email.json /srv/luckypack/data/clients/registry

Формат события (минимум):
{
  "type": "user.update",
  "source": "telegram",
  "payload": {"telegram_user_id": 815549184, "field": "phone"|"email", "value": "...", "verified": true}
}
"""
from __future__ import annotations
import os, sys, json
from typing import Any

APP_ROOT = "/srv/luckypack/App"
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

try:
    from CEAI import upsert
except Exception as e:
    print("ERR: не могу импортировать CEAI.upsert:", repr(e))
    sys.exit(1)


def load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERR: файл не найден: {path}")
        sys.exit(1)
    except Exception as e:
        print(f"ERR: не получилось прочитать {path}: {e}")
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python3 run_upsert_event.py <event.json> <reg_dir>")
        sys.exit(1)

    ev_path = sys.argv[1]
    reg_dir = sys.argv[2]

    ev = load_json(ev_path)

    if ev.get("type") != "user.update":
        print("ERR: поддерживается только type=user.update")
        sys.exit(1)

    payload = ev.get("payload") or {}
    tgid = payload.get("telegram_user_id")
    field = payload.get("field")
    value = payload.get("value")
    verified = bool(payload.get("verified"))

    if not (tgid and field in ("email", "phone") and isinstance(value, str) and verified):
        print("ERR: payload должен содержать telegram_user_id, field in {email,phone}, value:str, verified:true")
        sys.exit(1)

    canon = upsert.resolve_canonical_by_tg(reg_dir, str(tgid))
    base = os.path.join(reg_dir, "by_id", canon)
    upsert.append_event(base, ev)

    if field == "email":
        ok, msg = upsert.apply_user_update_email(reg_dir, canon, ev)
    else:
        ok, msg = upsert.apply_user_update_phone(reg_dir, canon, ev)

    print("canon:", canon)
    print("apply:", field, "->", ok, msg)

    # сводка из client.json
    client_p = os.path.join(base, "client.json")
    client = load_json(client_p)
    contacts = client.get("contacts", {})

    if field == "email":
        email = (contacts.get("email") or {}).get("value")
        print("client.contacts.email.value:", email)
        idx = load_json(os.path.join(reg_dir, "index.json"))
        print("index.by_email has:", (email or "").lower() in (idx.get("by_email") or {}))
        print("index.by_email[", (email or "").lower(), "] -> ", (idx.get("by_email") or {}).get((email or "").lower()))
    else:
        phone = (contacts.get("phone") or {}).get("value")
        print("client.contacts.phone.value:", phone)
        idx = load_json(os.path.join(reg_dir, "index.json"))
        print("index.by_phone has:", (phone or "") in (idx.get("by_phone") or {}))
        print("index.by_phone[", (phone or ""), "] -> ", (idx.get("by_phone") or {}).get((phone or "")))


if __name__ == "__main__":
    main()
