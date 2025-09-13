"""
yandex_api.py — Скачивание и синхронизация фото с Яндекс.Диска

• Собирает рекурсивно все фото из публичной папки Я.Диск (по ссылке из config.py)
• Скачивает только новые фото (jpg/jpeg/png), лишние локальные удаляет
• Все действия и ошибки логируются (logs/photos.log), критичные ошибки — админу через admin_notify
"""

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import requests
import re
import os
import time
from config import YANDEX_DISK_LINK_PHOTOS, PHOTO_DOWNLOAD_PATH, ALLOWED_PHOTO_EXTENSIONS, LOGS_DIR
from admin_notify import notify_admin

# Логируем в корневую папку logs проекта LuckyPackProject
PHOTOS_LOG = os.path.join(LOGS_DIR, "photos.log")
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(PHOTO_DOWNLOAD_PATH, exist_ok=True)

def write_photo_log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(PHOTOS_LOG, "a", encoding="utf-8") as logf:
        logf.write(f"[{ts}] {msg}\n")

def extract_public_key_from_url(url):
    """Извлекает публичный ключ из ссылки Яндекс.Диска"""
    if "/d/" in url:
        return url.split("/d/")[1].split("?")[0]
    return url  # fallback (если уже ключ)

def get_all_files_recursive(public_key, path='/', _silent=False):
    url = 'https://cloud-api.yandex.net/v1/disk/public/resources'
    params = {
        'public_key': public_key,
        'path': path,
        'limit': 1000,
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            files = []
            if '_embedded' in data and 'items' in data['_embedded']:
                for item in data['_embedded']['items']:
                    if item['type'] == 'file':
                        files.append({
                            'name': item['name'],
                            'path': item['path'],
                            'modified': item['modified']
                        })
                    elif item['type'] == 'dir':
                        sub_files = get_all_files_recursive(public_key, item['path'], _silent=True)
                        files.extend(sub_files)
            return files
        else:
            err = f"Ошибка при получении списка файлов: {response.status_code} — {response.text}"
            write_photo_log(err)
            if not _silent:
                notify_admin(err, module="yandex_api.py")
            return []
    except requests.exceptions.RequestException as e:
        err = f"Сетевая ошибка при получении файлов: {e}"
        write_photo_log(err)
        if not _silent:
            notify_admin(err, module="yandex_api.py")
        return []

def download_files_with_check(files, download_path, public_key, allowed_extensions=None):
    allowed_extensions = allowed_extensions or ALLOWED_PHOTO_EXTENSIONS
    allowed = {e.lower() for e in allowed_extensions}
    os.makedirs(download_path, exist_ok=True)

    # ===== Name-based dedup plan =====
    def base_of(stem: str) -> str:
        return re.sub(r"\s+\(\d+\)$", "", stem or "")

    def parse_n(stem: str) -> int:
        m = re.search(r"\((\d+)\)$", stem or "")
        return int(m.group(1)) if m else 0

    def norm_basename(stem: str) -> str:
        digits = re.sub(r"\D", "", stem or "")
        return digits if digits else (stem or "unnamed")

    groups = {}  # (base, ext) -> {"base_exists": bool, "items": [(name, path, n)]}
    for f in files:
        name = f.get("name", "")
        path = f.get("path", "")
        ext = os.path.splitext(name)[1].lower()
        if ext not in allowed:
            continue
        stem = os.path.splitext(name)[0]
        base = base_of(stem)
        n = parse_n(stem)
        key = (base, ext)
        entry = groups.setdefault(key, {"base_exists": False, "items": []})
        entry["items"].append((name, path, n))
        if n == 0:
            entry["base_exists"] = True

    planned = []
    skipped_name_dups = 0
    for (base, ext), info in groups.items():
        items = sorted(info["items"], key=lambda t: (t[2], t[0]))
        if info["base_exists"]:
            for name, path, n in items:
                if n == 0:
                    planned.append({"name": name, "path": path, "target_name": f"{norm_basename(base)}{ext}"})
                else:
                    write_photo_log(f"Skip duplicate by name: {name}")
                    skipped_name_dups += 1
        else:
            name, path, n = items[0]
            planned.append({"name": name, "path": path, "target_name": f"{norm_basename(base)}{ext}"})
            for name2, _, _ in items[1:]:
                write_photo_log(f"Skip duplicate by name: {name2}")
                skipped_name_dups += 1

    write_photo_log(f"Planned after name-dedup: {len(planned)}; skipped: {skipped_name_dups}")

    # Set of expected normalized filenames from cloud
    cloud_targets = set()
    for f in planned:
        tname = f.get("target_name") or f["name"]
        ext = os.path.splitext(tname)[1].lower()
        if ext in allowed:
            cloud_targets.add(tname)

    local_file_names = set(os.listdir(download_path))
    extra_files = sorted(local_file_names - cloud_targets)
    for extra in extra_files:
        try:
            os.remove(os.path.join(download_path, extra))
            write_photo_log(f"Removed extra local file: {extra}")
        except Exception as e:
            err = f"Error removing file {extra}: {e}"
            write_photo_log(err)
            notify_admin(err, module="yandex_api.py")

    skipped_existing = 0
    to_download = []
    for f in planned:
        tname = f.get("target_name") or f["name"]
        tpath = os.path.join(download_path, tname)
        if os.path.exists(tpath):
            skipped_existing += 1
        else:
            to_download.append(f)

    total = len(to_download)
    if total == 0:
        write_photo_log("No new photos — all already downloaded.")
    else:
        write_photo_log(f"New photos to download: {total}")

    url_get = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    downloaded = 0
    for i, f in enumerate(to_download, 1):
        name = f["name"]; path = f["path"]
        tname = f.get("target_name") or name
        tpath = os.path.join(download_path, tname)
        try:
            resp = requests.get(url_get, params={"public_key": public_key, "path": path})
            if resp.status_code == 200:
                href = resp.json().get("href")
                try:
                    with requests.get(href, stream=True) as r:
                        with open(tpath, "wb") as out:
                            for chunk in r.iter_content(chunk_size=8192):
                                out.write(chunk)
                    downloaded += 1
                    write_photo_log(f"Downloaded: {tname}")
                except Exception as e:
                    err = f"Error writing file {tname}: {e}"
                    write_photo_log(err)
                    notify_admin(err, module="yandex_api.py")
                    if os.path.exists(tpath):
                        os.remove(tpath)
            else:
                err = f"Cannot get download link for: {name}"
                write_photo_log(err)
                notify_admin(err, module="yandex_api.py")
        except requests.exceptions.RequestException as e:
            err = f"Network error while downloading {name}: {e}"
            write_photo_log(err)
            notify_admin(err, module="yandex_api.py")
            if os.path.exists(tpath):
                os.remove(tpath)
        write_photo_log(f"Progress: {i} of {total} — {tname}")

    write_photo_log(f"New files downloaded: {downloaded}; already existed: {skipped_existing}")

def sync_yandex_photos():
    public_key = extract_public_key_from_url(YANDEX_DISK_LINK_PHOTOS)
    files = get_all_files_recursive(public_key)
    download_files_with_check(files, PHOTO_DOWNLOAD_PATH, public_key)

if __name__ == "__main__":
    sync_yandex_photos()