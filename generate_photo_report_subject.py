#!/usr/bin/env python3
"""
generate_photo_report_subject.py

-------------------------------------------------
Назначение:
    • Сравнивает штрихкоды из прайсов (XLS/XLSX) с именами фото из папки (фотографии товаров).
    • Проверяет соответствие: фото названы корректно (штрихкодом?), есть ли такой штрихкод в прайсах?
    • Генерирует Excel-отчёт: 
        — 🟢 Есть в прайсе и на диске
        — 🟡 Есть на диске, но нет в прайсе
        — 🔴 Не штрихкод (шляпа)
    • Логирует ошибки в logs/generate_photo_report_subject.log
    • Критичные ошибки отправляются админу через admin_notify (если доступен)

Параметры:
    PRICES_DIR  — путь к папке с прайсами
    PHOTOS_DIR  — путь к фото (локальной папке)
    OUTPUT_FILE — имя Excel-отчёта

Запуск:
    python3 generate_photo_report_subject.py
-------------------------------------------------
"""

import os
import re
import pandas as pd
import logging
from admin_notify import notify_admin

# === ПАРАМЕТРЫ ===
PRICES_DIR = "LuckyPricer/cleaned"
PHOTOS_DIR = "LuckyDownloader/data/photos"
OUTPUT_FILE = "сравнение_штрихкодов.xlsx"

# === ЛОГИРОВАНИЕ ===
LOGS_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "generate_photo_report_subject.log")
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)

def log_both(msg, level='info', critical=False):
    print(msg)
    getattr(logging, level)(msg)
    if critical:
        try:
            notify_admin(msg, module="generate_photo_report_subject.py")
        except Exception:
            pass  # Не паникуем, если алерт не прошёл

# === ШТРИХКОДЫ ИЗ ПРАЙСОВ ===
def extract_barcodes_from_excel(file_path):
    barcodes = set()
    try:
        df = pd.read_excel(file_path, dtype=str, engine="openpyxl" if file_path.endswith(".xlsx") else "xlrd")
        for col in df.columns:
            values = ' '.join(df[col].dropna().astype(str))
            barcodes.update(re.findall(r'\b\d{12,13}\b', values))
    except Exception as e:
        log_both(f"⚠️ Ошибка чтения {file_path}: {e}", level='error', critical=True)
    return barcodes

def collect_all_barcodes(prices_dir):
    all_codes = set()
    for root, _, files in os.walk(prices_dir):
        for file in files:
            if file.endswith((".xls", ".xlsx")):
                path = os.path.join(root, file)
                all_codes |= extract_barcodes_from_excel(path)
    return all_codes

# === ФОТО ИЗ ЛОКАЛЬНОЙ ПАПКИ ===
def get_local_photo_filenames(photos_dir):
    filenames = []
    for file in os.listdir(photos_dir):
        if os.path.isfile(os.path.join(photos_dir, file)):
            name, _ = os.path.splitext(file)
            filenames.append(name)
    return filenames

# === СРАВНЕНИЕ ===
def generate_report():
    log_both("🔍 Чтение штрихкодов из прайсов...")
    barcodes = collect_all_barcodes(PRICES_DIR)
    log_both(f"✅ Найдено штрихкодов: {len(barcodes)}")

    log_both(f"📂 Чтение локальных имён файлов из {PHOTOS_DIR}...")
    photo_names = get_local_photo_filenames(PHOTOS_DIR)
    log_both(f"✅ Фотографий в папке: {len(photo_names)}")

    matched = []
    unmatched = []
    invalid = []

    for name in photo_names:
        if not re.fullmatch(r'\d{12,13}', name):
            invalid.append((name, len(name)))
        elif name in barcodes:
            matched.append((name, len(name)))
        else:
            unmatched.append((name, len(name)))

    max_len = max(len(matched), len(unmatched), len(invalid))

    def pad(lst):
        return lst + [("", "")] * (max_len - len(lst))

    df = pd.DataFrame({
        "🟢 Есть в прайсе и на диске": [x[0] for x in pad(matched)],
        "Длина 🟢": [x[1] for x in pad(matched)],
        "🟡 Есть на диске, но нет в прайсе": [x[0] for x in pad(unmatched)],
        "Длина 🟡": [x[1] for x in pad(unmatched)],
        "🔴 Не штрихкод (шляпа)": [x[0] for x in pad(invalid)],
        "Длина 🔴": [x[1] for x in pad(invalid)]
    })

    try:
        df.to_excel(OUTPUT_FILE, index=False)
        log_both(f"📄 Отчёт сохранён: {OUTPUT_FILE}")
    except Exception as e:
        log_both(f"❌ Ошибка при сохранении отчёта: {e}", level='error', critical=True)

if __name__ == "__main__":
    generate_report()