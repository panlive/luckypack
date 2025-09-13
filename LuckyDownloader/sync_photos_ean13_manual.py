#!/usr/bin/env python3
import sys, os, re, time
from pathlib import Path

# Подхват .env до импортов проекта
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
except Exception:
    pass
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from photo_sync.yandex_api import (
    get_all_files_recursive,
    download_files_with_check,
    write_photo_log,
)
from config import YANDEX_DISK_LINK_PHOTOS, PHOTO_DOWNLOAD_PATH, ALLOWED_PHOTO_EXTENSIONS

VALID_NAME = re.compile(r'^\d{13}\.(jpg|jpeg|png)$', re.IGNORECASE)

def main():
    # Жёстко МСК на всякий
    try:
        os.environ['TZ'] = 'Europe/Moscow'
        time.tzset()
    except Exception:
        pass

    link = (YANDEX_DISK_LINK_PHOTOS or '').strip()
    if not link:
        msg = "❌ YANDEX_DISK_LINK_PHOTOS не задан в .env — обёртка остановлена."
        try:
            write_photo_log(msg)
        except Exception:
            pass
        print(msg)
        return

    # Я.Диск принимает либо публичный ключ, либо полную ссылку — используем ссылку
    public_key = link

    # Получаем список файлов
    files = get_all_files_recursive(public_key)
    total = len(files)

    # Фильтр по имени
    filtered = [f for f in files if VALID_NAME.match((f.get('name') or '').strip())]
    dropped = total - len(filtered)
    write_photo_log(f"🔎 EAN13 wrapper: отброшено по имени: {dropped}, к скачиванию: {len(filtered)}")

    if not filtered:
        write_photo_log("⚠️ EAN13 wrapper: к скачиванию 0 файлов (после фильтра).")
        print("⚠️ После фильтра новых файлов нет.")
        return

    # Скачивание
    download_files_with_check(
        filtered,
        PHOTO_DOWNLOAD_PATH,
        public_key,
        allowed_extensions=ALLOWED_PHOTO_EXTENSIONS
    )
    print("✅ EAN-13: скачивание завершено (см. photos.log).")

if __name__ == "__main__":
    main()
