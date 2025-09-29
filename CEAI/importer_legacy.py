#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ceai_import_legacy.py
Импорт из /srv/luckypack/data/clients/*.json в CEAI-реестр.

Логика (бережно):
- canonical_id: если ИНН (10/12 цифр) -> inn:..., иначе если есть tg -> tg:...
- client.json: создать минимальный, ЕСЛИ не существует; не перетирать.
- events.jsonl: всегда append ingest.* и user.update для найденных полей.
- index.json: мульти-карта; обновление атомарно (tmp + os.replace).

Пример запуска (НЕ запускается автоматически этим файлом):
  python3 Tools/ceai_import_legacy.py --in /srv/luckypack/data/clients \
      --reg /srv/luckypack/data/clients/registry
"""
import os, json, argparse, time, uuid, glob, re, tempfile

def is_inn(s:str) -> bool:
    return bool(s) and s.isdigit() and len(s) in (10,12)

def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_json_safe(p, default=None):
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default

def dump_atomic(p:str, obj):
    d = os.path.dirname(p)
    os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def push_multimap(bucket:dict, key:str, val:str):
    arr = bucket.get(key)
    if not isinstance(arr, list):
        arr = []
    if val not in arr:
        arr.append(val)
    bucket[key] = arr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", default="/srv/luckypack/data/clients")
    ap.add_argument("--reg", dest="reg_dir", default="/srv/luckypack/data/clients/registry")
    args = ap.parse_args()

    in_dir  = args.in_dir
    reg_dir = args.reg_dir
    by_id   = os.path.join(reg_dir, "by_id")
    os.makedirs(by_id, exist_ok=True)

    idx_path = os.path.join(reg_dir, "index.json")
    idx = load_json_safe(idx_path, {"by_inn":{}, "by_tg":{}, "by_email":{}, "by_phone":{}})

    files = sorted(glob.glob(os.path.join(in_dir, "*.json")))
    imported = 0

    for fp in files:
        data = load_json_safe(fp, {})
        # извлечём тг и инн из данных или имени файла
        tgid = data.get("telegram_user_id")
        if tgid is None:
            # пробуем по имени файла: <tgid>.json
            m = re.search(r'(\d+)\.json$', fp)
            if m:
                try:
                    tgid = int(m.group(1))
                except Exception:
                    tgid = None
        inn = data.get("inn") or (data.get("identifiers", {}) or {}).get("inn")
        inn = str(inn) if inn is not None else None
        name = (data.get("person", {}) or {}).get("name") or data.get("name")

        canon = None
        if inn and is_inn(inn):
            canon = f"inn:{inn}"
        elif tgid is not None:
            canon = f"tg:{tgid}"
        else:
            # нет твёрдого признака — пропускаем
            continue

        base = os.path.join(by_id, canon)
        os.makedirs(base, exist_ok=True)

        # client.json — создаём, если нет
        client_p = os.path.join(base, "client.json")
        if not os.path.exists(client_p):
            created = now_utc()
            client = {
                "canonical_id": canon,
                "identifiers": {
                    **({"inn": inn} if inn else {}),
                    **({"telegram_user_id": tgid} if tgid is not None else {})
                },
                "company": {},
                "contacts": {
                    "email":   {"value": None, "confidence": 0.0, "verified": False, "source": "unknown"},
                    "phone":   {"value": None, "confidence": 0.0, "verified": False, "source": "unknown"},
                    "preferred": {"channel": "telegram" if tgid is not None else "unknown",
                                  "value": str(tgid) if tgid is not None else ""}
                },
                "person": {
                    "name": {"value": name or "", "verified": False, "source": "legacy"}
                },
                "audit": {"created_at": created, "last_updated_at": created}
            }
            dump_atomic(client_p, client)

        # events.jsonl — всегда append
        events_p = os.path.join(base, "events.jsonl")
        ts = now_utc()
        evs = []
        evs.append({"event_id": str(uuid.uuid4()), "ts": ts, "type":"ingest.legacy_client",
                    "actor":"system","source":"import","payload":{"from": fp}})
        if name:
            evs.append({"event_id": str(uuid.uuid4()), "ts": ts, "type":"user.update",
                        "actor":"client","source":"telegram",
                        "payload":{"field":"name","value":name,"verified":True if name else False}})
        if inn and is_inn(inn):
            evs.append({"event_id": str(uuid.uuid4()), "ts": ts, "type":"user.update",
                        "actor":"client","source":"telegram",
                        "payload":{"field":"inn","value":inn,"verified":True}})

        with open(events_p, 'a', encoding='utf-8') as f:
            for e in evs:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

        # aliases.json — дополним tg:* если есть
        aliases_p = os.path.join(base, "aliases.json")
        aliases = load_json_safe(aliases_p, {"canonical_id": canon, "aliases": []})
        if tgid is not None:
            alias = f"tg:{tgid}"
            if alias not in aliases["aliases"]:
                aliases["aliases"].append(alias)
                dump_atomic(aliases_p, aliases)
        else:
            if not os.path.exists(aliases_p):
                dump_atomic(aliases_p, aliases)

        # index.json — мульти-карта
        if inn and is_inn(inn):
            push_multimap(idx.setdefault("by_inn", {}), inn, canon)
        if tgid is not None:
            push_multimap(idx.setdefault("by_tg", {}), str(tgid), canon)

        imported += 1

    dump_atomic(idx_path, idx)
    print(f"OK: обработано файлов: {imported}, индекс обновлён: {idx_path}")

if __name__ == "__main__":
    main()
