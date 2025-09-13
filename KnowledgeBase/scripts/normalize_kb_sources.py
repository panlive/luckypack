#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
normalize_kb_sources.py
Ручной запуск. Читает Markdown из ./src и собирает normalized/knowledge_base.json.
- Никакого крона. Запускается вручную или из админ-кнопки позже.
- Хэш-гвард: если содержимое не менялось, файл не перезаписывается.
- Категория определяется эвристикой по заголовку.
"""
import os, re, json, hashlib, sys, datetime
from pathlib import Path

ROOT = Path("/srv/luckypack/project/KnowledgeBase")
SRC = ROOT / "src"
OUT = ROOT / "normalized"
OUT.mkdir(parents=True, exist_ok=True)
LOG = Path("/srv/luckypack/logs/knowledgebase.log")

def log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} [NORMALIZE] {msg}\n")

def parse_md(path: Path):
    txt = path.read_text(encoding="utf-8")
    title_m = re.search(r'^\s*#\s+(.+)$', txt, re.M)
    def section(name):
        m = re.search(rf'^##\s+{re.escape(name)}\s*\n(.*?)(?=^##\s+|\Z)', txt, re.S | re.M)
        return (m.group(1).strip() if m else "")
    def bullets(s):
        return [re.sub(r'^\s*-\s*', '', line).strip()
                for line in s.splitlines() if re.match(r'^\s*-\s+', line)]
    d = {
        "slug": path.stem,
        "title": title_m.group(1).strip() if title_m else path.stem,
        "summary": section("Кратко").strip(),
        "specs": bullets(section("Характеристики")),
        "advantages": bullets(section("Преимущества")),
        "applications": bullets(section("Применение")),
        "prices_note": section("Цены и политика").strip()
    }
    return d

def guess_category(title: str) -> str:
    t = title.lower()
    if "лента" in t: return "Ленты"
    if "корзин" in t: return "Корзины"
    if "плён" in t or "пленк" in t: return "Плёнка"
    if "тишью" in t or "бумага" in t: return "Бумага"
    if "фоамиран" in t or "eva" in t: return "Декор"
    return "Прочее"

def dict_hash(d) -> str:
    return hashlib.sha256(json.dumps(d, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

def build_payload():
    items = []
    for p in sorted(SRC.glob("*.md")):
        d = parse_md(p)
        items.append({
            "slug": d["slug"],
            "title": d["title"],
            "category": guess_category(d["title"]),
            "summary": d["summary"],
            "specs": d["specs"],
            "advantages": d["advantages"],
            "applications": d["applications"],
            "pricing_policy": {
                "has_prices": any(ch.isdigit() for ch in d["prices_note"]),
                "price_note": d["prices_note"]
            },
            "source_file": p.name
        })
    return {"items": items}

def main():
    payload = build_payload()
    out_json = OUT / "knowledge_base.json"
    hash_file = OUT / "kb_hash.txt"
    new_hash = dict_hash(payload)
    old_hash = hash_file.read_text(encoding="utf-8").strip() if hash_file.exists() else ""
    if new_hash == old_hash and out_json.exists():
        log("unchanged — skip write")
        print("KB unchanged — nothing to do.")
        return
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    hash_file.write_text(new_hash, encoding="utf-8")
    log(f"wrote {out_json} (items: {len(payload['items'])})")
    print(f"Wrote {out_json} (items: {len(payload['items'])})")

if __name__ == "__main__":
    main()
