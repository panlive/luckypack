#!/usr/bin/env python3
import os, re, sys, time
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
except Exception:
    pass

from photo_sync.yandex_api import get_all_files_recursive, download_files_with_check, write_photo_log
from config import YANDEX_DISK_LINK_PHOTOS, PHOTO_DOWNLOAD_PATH, ALLOWED_PHOTO_EXTENSIONS

VALID_NAME = re.compile(r'^\d{13}\.(jpg|jpeg|png)$', re.IGNORECASE)

def main():
    try:
        os.environ['TZ'] = 'Europe/Moscow'; time.tzset()
    except Exception: pass

    link = (os.environ.get('YANDEX_DISK_LINK_PHOTOS') or YANDEX_DISK_LINK_PHOTOS or '').strip()
    if not link:
        write_photo_log("❌ Guard: YANDEX_DISK_LINK_PHOTOS не задан"); print("no link"); return

    # 1) Все валидные файлы с Диска
    files = get_all_files_recursive(link)
    filtered = [f for f in files if VALID_NAME.match((f.get('name') or '').strip())]
    write_photo_log(f"🔎 Guard: валидных на диске: {len(filtered)}")
    # --- DETECTOR: changed-by-modified ---
    # Слепок modified по облаку -> сравнение с манифестом
    cloud_mod = {}
    for f in filtered:
        name = (f.get("name") or "").strip()
        path = f.get("path")
        mod  = f.get("modified")
        ean  = os.path.splitext(name)[0]
        if re.fullmatch(r"\d{13}", ean):
            cloud_mod[ean] = {"modified": mod, "path": path}

    manifest_path = "/srv/luckypack/project/LuckyDownloader/state/photos_manifest.json"
    try:
        import json
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest = json.load(mf)
        else:
            manifest = {}
    except Exception:
        manifest = {}

    changed = []
    for ean, meta in cloud_mod.items():
        old = manifest.get(ean, {})
        if old.get("modified") != meta.get("modified"):
            changed.append(ean)

    # Логируем сухую статистику
    try:
        write_photo_log(f"🛈 Changed-by-modified: {len(changed)}; sample: {sorted(changed)[:10]}")
    except Exception:
        pass

    # Обновляем манифест на текущий снимок
    try:
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(cloud_mod, mf, ensure_ascii=False, indent=2)
    except Exception as e:
        write_photo_log(f"Manifest write error: {e}")
    # --- /DETECTOR ---

    # 2) Уже имеющиеся EAN в vectorized
    have = set()
    for _, _, fnames in os.walk("/app/data/photos/vectorized"):
        for n in fnames:
            m = re.match(r'^(\d{13})\.webp$', n, re.IGNORECASE)
            if m: have.add(m.group(1))

    # 3) Фильтрация: оставить только те, которых нет в vectorized
    def ean_of(name:str)->str:
        return os.path.splitext(name)[0]
    filtered2 = [f for f in filtered if ean_of(f['name']) not in have]
    write_photo_log(f"�� Guard: уже в vectorized: {len(have)}; будет скачано: {len(filtered2)}")

    if not filtered2:
        write_photo_log("⚠️ Guard: новинок нет — к скачиванию 0."); print("no new"); return

    download_files_with_check(filtered2, PHOTO_DOWNLOAD_PATH, link, allowed_extensions=ALLOWED_PHOTO_EXTENSIONS)
    print("ok")
if __name__ == "__main__":
    main()
