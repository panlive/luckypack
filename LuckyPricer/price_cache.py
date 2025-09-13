#!/usr/bin/env python3
"""
price_cache.py — обновляет прайсы с Яндекс.Диска.

Особенности:
- Сам подхватывает .env из корня проекта (/srv/luckypack/project).
- Пишет логи в /srv/luckypack/logs/price_cache.log.
- Кладёт xlsx в PROJECT_ROOT/LuckyPricer/data/prices.
- По умолчанию обновляет не чаще раза в 24 часа. Можно форсировать, установив FORCE_UPDATE=1.
"""

import os
import time
from datetime import datetime, timedelta
import logging
import requests

# --------- Определяем корень проекта и .env ---------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))               # .../project/LuckyPricer
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, os.pardir))   # .../project

# Подхватываем .env из корня проекта, если есть (без зависимостей)
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.isfile(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)

# --------- Конфигурация ---------
YANDEX_DISK_LINK_PRICES = os.getenv("YANDEX_DISK_LINK_PRICES", "").strip()
LOGS_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")

LOCAL_PRICE_DIR = os.path.join(PROJECT_ROOT, "LuckyPricer", "data", "prices")
LAST_UPDATE_FILE = os.path.join(PROJECT_ROOT, "LuckyPricer", "data", "last_update.txt")
UPDATE_INTERVAL_HOURS = int(os.getenv("UPDATE_INTERVAL_HOURS", "24"))
FORCE_UPDATE = os.getenv("FORCE_UPDATE", "0") == "1"

os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "price_cache.log")

# Логирование: файл + stdout
logger = logging.getLogger("price_cache")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)

def log_info(msg): logger.info(msg); print(msg)
def log_err(msg):  logger.error(msg); print(msg)

def needs_update() -> bool:
    if FORCE_UPDATE:
        return True
    if not os.path.exists(LAST_UPDATE_FILE):
        return True
    try:
        with open(LAST_UPDATE_FILE, "r") as f:
            ts = float(f.read().strip())
    except Exception:
        return True
    last = datetime.fromtimestamp(ts)
    return datetime.now() - last > timedelta(hours=UPDATE_INTERVAL_HOURS)

def save_update_time():
    os.makedirs(os.path.dirname(LAST_UPDATE_FILE), exist_ok=True)
    with open(LAST_UPDATE_FILE, "w") as f:
        f.write(str(time.time()))

def get_excel_files_list(public_link: str, path: str = "/") -> list:
    url = "https://cloud-api.yandex.net/v1/disk/public/resources"
    params = {"public_key": public_link, "path": path}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    result = []
    for item in data.get("_embedded", {}).get("items", []):
        if item.get("type") == "file" and item.get("name", "").endswith((".xlsx", ".xls")):
            result.append(item)
        elif item.get("type") == "dir":
            result.extend(get_excel_files_list(public_link, item.get("path", "")))
    return result

def download_file(public_link: str, file_path_on_disk: str, local_destination: str):
    url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    params = {"public_key": public_link, "path": file_path_on_disk}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    href = resp.json().get("href")
    with requests.get(href, stream=True, timeout=60) as r:
        r.raise_for_status()
        os.makedirs(os.path.dirname(local_destination), exist_ok=True)
        with open(local_destination, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

def main():
    if not YANDEX_DISK_LINK_PRICES:
        log_err("❌ Не задан YANDEX_DISK_LINK_PRICES (укажите в .env)")
        return 1

    if not needs_update():
        log_info("⏳ Обновление не требуется — интервал ещё не истёк")
        return 0

    try:
        log_info("🕑 Запуск обновления прайсов")
        files = get_excel_files_list(YANDEX_DISK_LINK_PRICES)
        log_info(f"🧾 Найдено файлов: {[f.get('name') for f in files]}")
        ok = 0
        for item in files:
            name = item.get("name")
            local_path = os.path.join(LOCAL_PRICE_DIR, name)
            try:
                download_file(YANDEX_DISK_LINK_PRICES, item.get("path"), local_path)
                log_info(f"✅ Скачан: {name}")
                ok += 1
            except Exception as e:
                log_err(f"⚠️ Ошибка при скачивании {name}: {e}")
        save_update_time()
        log_info(f"📦 Прайсы обновлены (успешно: {ok}/{len(files)})")
        return 0
    except Exception as e:
        log_err(f"❌ Ошибка в update_prices: {e}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())