#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CEAI Upsert (минимум, стабильная версия)

Назначение:
  Принять одно событие (JSON) типа user.update и аккуратно обновить карточку клиента
  в файловом реестре CEAI (Client / Event / Alias / Index):
    • contacts.email (и preferred=email) + индекс by_email
    • contacts.phone (E.164) + индекс by_phone

Поддержка событий (минимум):
  type = "user.update" с payload:
    {
      "telegram_user_id": <int>,
      "field": "email" | "phone",
      "value": <str>,
      "verified": true
    }
  source: "telegram" | "dialog" | др. (используется в поле source в карточке и actor для журнала)

Особенности:
  • Пытаемся использовать готовые нормализации из ClientCards/vision_parse.py:
      - EMAIL_RE
      - normalize_phone_ru
    Если импорт недоступен — используем фолбэк-реализации внутри этого файла (надёжно).
  • Журнал событий (events.jsonl) — append-only.
  • Запись JSON-файлов атомарно: *.tmp -> os.replace().

Запуск (пример):
  python3 /srv/luckypack/App/CEAI/upsert.py \
      --event /tmp/event_email.json \
      --reg   /srv/luckypack/data/clients/registry

Ограничения этой версии:
  • merge по ИНН не выполняется (будет отдельным шагом)
  • имя/компанию не трогаем
"""
from __future__ import annotations
import os, sys, json, argparse, time, uuid, re
from typing import Any, Dict, Optional

# ---------- утилиты ----------

def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_json_safe(p: str, default: Any = None) -> Any:
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default

def dump_atomic(p: str, obj: Any) -> None:
    d = os.path.dirname(p)
    os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def push_multimap(bucket: Dict[str, list], key: str, val: str) -> None:
    arr = bucket.get(key)
    if not isinstance(arr, list):
        arr = []
    if val not in arr:
        arr.append(val)
    bucket[key] = arr

# ---------- подключение нормализаций из ClientCards (если есть) ----------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /srv/luckypack/App
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CC_EMAIL_RE = None
cc_normalize_phone_ru = None
try:
    from ClientCards.vision_parse import EMAIL_RE as CC_EMAIL_RE, normalize_phone_ru as cc_normalize_phone_ru  # type: ignore
except Exception:
    pass

FALLBACK_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def normalize_phone_fallback(raw: str | None) -> Optional[str]:
    """Простой фолбэк: E.164.
       РФ: 8XXXXXXXXXX -> +7XXXXXXXXXX, 10 цифр -> +7XXXXXXXXXX.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    digits = re.sub(r"\D", "", s)
    if s.startswith('+'):
        return '+' + re.sub(r"\D", "", s[1:]) if 7 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits[0] == '8':
        return '+7' + digits[1:]
    if len(digits) == 10:
        return '+7' + digits
    if 6 <= len(digits) <= 15:
        return '+' + digits
    return None

def normalize_phone(raw: str | None) -> Optional[str]:
    if cc_normalize_phone_ru:
        try:
            return cc_normalize_phone_ru(raw)
        except Exception:
            return normalize_phone_fallback(raw)
    return normalize_phone_fallback(raw)

# ---------- CEAI примитивы ----------

def resolve_canonical_by_tg(reg_dir: str, tgid: str) -> str:
    idx_path = os.path.join(reg_dir, "index.json")
    idx = load_json_safe(idx_path, {"by_inn":{}, "by_tg":{}, "by_email":{}, "by_phone":{}})
    arr = (idx.get("by_tg") or {}).get(str(tgid))
    if arr:
        return arr[0]

    canon = f"tg:{tgid}"
    base = os.path.join(reg_dir, "by_id", canon)
    os.makedirs(base, exist_ok=True)

    # client.json каркас
    client_p = os.path.join(base, "client.json")
    if not os.path.exists(client_p):
        now = now_utc()
        client = {
            "canonical_id": canon,
            "identifiers": {"telegram_user_id": int(tgid)},
            "company": {},
            "contacts": {
                "email":   {"value": None, "confidence": 0.0, "verified": False, "source": "unknown"},
                "phone":   {"value": None, "confidence": 0.0, "verified": False, "source": "unknown"},
                "preferred": {"channel": "telegram", "value": str(tgid)}
            },
            "person": {"name": {"value": "", "verified": False, "source": "unknown"}},
            "audit": {"created_at": now, "last_updated_at": now}
        }
        dump_atomic(client_p, client)

    # aliases.json
    aliases_p = os.path.join(base, "aliases.json")
    aliases = load_json_safe(aliases_p, {"canonical_id": canon, "aliases": []})
    alias = f"tg:{tgid}"
    if alias not in aliases["aliases"]:
        aliases["aliases"].append(alias)
        dump_atomic(aliases_p, aliases)

    # индекс by_tg
    push_multimap(idx.setdefault("by_tg", {}), str(tgid), canon)
    dump_atomic(idx_path, idx)
    return canon


def append_event(base: str, event: Dict[str, Any]) -> None:
    p = os.path.join(base, "events.jsonl")
    e = dict(event)
    e.setdefault("event_id", str(uuid.uuid4()))
    e.setdefault("ts", now_utc())
    e.setdefault("actor", "client" if e.get("source") == "telegram" else "system")
    with open(p, 'a', encoding='utf-8') as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def apply_user_update_email(reg_dir: str, canon: str, event: Dict[str, Any]) -> tuple[bool, str]:
    base = os.path.join(reg_dir, "by_id", canon)
    client_p = os.path.join(base, "client.json")
    client = load_json_safe(client_p)
    if client is None:
        return False, "client.json missing"

    payload = event.get("payload") or {}
    email_raw = payload.get("value")
    if not isinstance(email_raw, str):
        return False, "bad email"
    email = email_raw.strip()

    # проверка почты: сначала CC_EMAIL_RE, иначе фолбэк
    ok = bool(CC_EMAIL_RE.match(email)) if CC_EMAIL_RE else bool(FALLBACK_EMAIL_RE.match(email))
    if not ok:
        return False, "bad email"
    email_lc = email.lower()

    # обновим client.json
    contacts = client.setdefault("contacts", {})
    email_slot = contacts.setdefault("email", {"value": None, "confidence": 0.0, "verified": False, "source": "unknown"})
    email_slot.update({"value": email, "confidence": 1.0, "verified": True, "source": event.get("source", "dialog")})

    preferred = contacts.setdefault("preferred", {})
    preferred.update({"channel": "email", "value": email})

    client.setdefault("audit", {})["last_updated_at"] = now_utc()
    dump_atomic(client_p, client)

    # индекс by_email
    idx_path = os.path.join(reg_dir, "index.json")
    idx = load_json_safe(idx_path, {"by_inn":{}, "by_tg":{}, "by_email":{}, "by_phone":{}})
    push_multimap(idx.setdefault("by_email", {}), email_lc, canon)
    dump_atomic(idx_path, idx)
    return True, "ok"


def apply_user_update_phone(reg_dir: str, canon: str, event: Dict[str, Any]) -> tuple[bool, str]:
    base = os.path.join(reg_dir, "by_id", canon)
    client_p = os.path.join(base, "client.json")
    client = load_json_safe(client_p)
    if client is None:
        return False, "client.json missing"

    payload = event.get("payload") or {}
    phone_raw = payload.get("value")
    e164 = normalize_phone(phone_raw)
    if not e164:
        return False, "bad phone"

    contacts = client.setdefault("contacts", {})
    phone_slot = contacts.setdefault("phone", {"value": None, "confidence": 0.0, "verified": False, "source": "unknown"})
    phone_slot.update({"value": e164, "confidence": 1.0, "verified": True, "source": event.get("source", "dialog")})

    preferred = contacts.setdefault("preferred", {})
    # не перетираем, если уже выбран канал (например, email)
    if not preferred.get("channel"):
        preferred.update({"channel": "phone", "value": e164})

    client.setdefault("audit", {})["last_updated_at"] = now_utc()
    dump_atomic(client_p, client)

    # индекс by_phone
    idx_path = os.path.join(reg_dir, "index.json")
    idx = load_json_safe(idx_path, {"by_inn":{}, "by_tg":{}, "by_email":{}, "by_phone":{}})
    push_multimap(idx.setdefault("by_phone", {}), e164, canon)
    dump_atomic(idx_path, idx)
    return True, "ok"


# ---------- CLI ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True, help="путь к JSON событию")
    ap.add_argument("--reg", default="/srv/luckypack/data/clients/registry", help="путь к корню реестра CEAI")
    args = ap.parse_args()

    event = load_json_safe(args.event, {})
    if not event:
        print("ERR: пустое/нечитаемое событие"); return
    if event.get("type") != "user.update":
        print("SKIP: type != user.update"); return

    payload = event.get("payload") or {}
    if not payload.get("verified", False):
        print("SKIP: not verified"); return

    tgid = payload.get("telegram_user_id")
    if not tgid:
        print("ERR: нет telegram_user_id"); return

    canon = resolve_canonical_by_tg(args.reg, str(tgid))
    base = os.path.join(args.reg, "by_id", canon)
    append_event(base, event)

    field = payload.get("field")
    if field == "email":
        ok, msg = apply_user_update_email(args.reg, canon, event)
    elif field == "phone":
        ok, msg = apply_user_update_phone(args.reg, canon, event)
    else:
        print("SKIP: unsupported field"); return

    print(("OK: " if ok else "ERR: ") + msg, "| canon:", canon)

if __name__ == "__main__":
    main()
