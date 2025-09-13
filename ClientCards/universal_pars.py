#!/usr/bin/env python3
"""
universal_pars.py — универсальный парсер документов (сервис).
• Обрабатывает Excel/PDF/изображения по расписанию, пишет в data/, логирует в logs/.
• Долгоживущий процесс в контейнере luckypack_universal.
Не изменять без необходимости.
"""
# -*- coding: utf-8 -*-

"""
universal_pars.py — Универсальный приёмник входящих карточек LuckyPack

Что делает:
  • Берёт файлы из INCOMING_DIR (/app/data/cards/incoming_cards)
  • Для изображений (png/jpg/jpeg/heic/tif/tiff/webp/bmp) — просто копирует в OUTPUT_DIR
    c читаемым суффиксом "__ДД.ММ.ГГГГ_ЧЧ:ММ" и удаляет исходник.
  • Для pdf/docx/xlsx — конвертирует в PNG (первая страница), сохраняет в OUTPUT_DIR и удаляет исходник.
  • Весь процесс логируется в /app/logs/parsing.log
"""

import os
import re
import shutil
import logging
import traceback
import subprocess
import unicodedata
from datetime import datetime

# --- Внешние библиотеки ---
try:
    from transliterate import translit
    from pdf2image import convert_from_path
    from PIL import Image
except ImportError as e:
    print(f"❗ Не установлена библиотека: {e.name}. Установи через pip.")
    raise

# --- Пути ---
INCOMING_DIR = "/app/data/cards/incoming_cards"
OUTPUT_DIR   = "/app/data/cards/vision_temp"

# --- Логи ---
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "parsing.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# --- Поддерживаемые расширения ---
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".webp", ".bmp"}
DOC_EXTS   = {".pdf", ".docx", ".xlsx"}

# --- Утилиты ---
def _translit_name(name: str) -> str:
    name = translit(name, 'ru', reversed=True)
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[^A-Za-z0-9_]+', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name

def _timestamp_suffix() -> str:
    # Читаемо: ДД.ММ.ГГГГ_ЧЧ:ММ (без секунд)
    return datetime.now().strftime("%d.%m.%Y_%H:%M")

def make_dest_filename(src_filename: str, target_ext: str | None = None) -> str:
    """
    Собирает имя в OUTPUT_DIR:
      <транслитерированная_база>__ДД.ММ.ГГГГ_ЧЧ:ММ<ext>
    Если target_ext не задан — берём исходное расширение.
    """
    base, ext = os.path.splitext(src_filename)
    base = _translit_name(base)
    ext = (target_ext or ext).lower()
    return f"{base}__{_timestamp_suffix()}{ext}"

def convert_office_to_pdf(src_path: str, out_dir: str) -> str | None:
    """docx/xlsx -> pdf через libreoffice --headless"""
    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, src_path],
            check=True
        )
        base = os.path.splitext(os.path.basename(src_path))[0]
        pdf_path = os.path.join(out_dir, base + ".pdf")
        if os.path.exists(pdf_path):
            return pdf_path
        logging.error("PDF не создан: %s", pdf_path)
        return None
    except Exception as e:
        logging.error("Ошибка конвертации в PDF (%s): %s", src_path, e)
        logging.error(traceback.format_exc())
        return None

def pdf_first_page_to_png(pdf_path: str, png_path: str) -> bool:
    try:
        images = convert_from_path(pdf_path, first_page=1, last_page=1)
        if images:
            images[0].save(png_path, "PNG")
            return True
        logging.error("Не удалось извлечь страницу из PDF: %s", pdf_path)
    except Exception as e:
        logging.error("Ошибка pdf->png (%s): %s", pdf_path, e)
        logging.error(traceback.format_exc())
    return False

def copy_image_as_is(src_path: str, dst_path: str) -> bool:
    """Изображение просто копируем (HEIC/TIFF/WEBP и т.п. тоже)."""
    try:
        shutil.copy2(src_path, dst_path)
        return True
    except Exception as e:
        logging.error("Ошибка копирования изображения (%s): %s", src_path, e)
        logging.error(traceback.format_exc())
        return False

def handle_document(src_path: str, ext: str, dst_filename_png: str) -> bool:
    """
    PDF — сразу в PNG (1-я страница).
    DOCX/XLSX — сначала в PDF, затем PNG.
    """
    try:
        tmp_pdf = None
        if ext == ".pdf":
            tmp_pdf = src_path
        elif ext in {".docx", ".xlsx"}:
            tmp_pdf = convert_office_to_pdf(src_path, OUTPUT_DIR)
            if not tmp_pdf:
                return False
        else:
            logging.error("Неожиданное расширение дока: %s", ext)
            return False

        dst_png_path = os.path.join(OUTPUT_DIR, dst_filename_png)
        ok = pdf_first_page_to_png(tmp_pdf, dst_png_path)
        # чистим промежуточный PDF (если мы его создавали)
        if tmp_pdf and tmp_pdf != src_path:
            try:
                os.remove(tmp_pdf)
            except Exception:
                pass
        return ok
    except Exception as e:
        logging.error("Ошибка обработки документа (%s): %s", src_path, e)
        logging.error(traceback.format_exc())
        return False

def process_one(src_filename: str) -> None:
    src_path = os.path.join(INCOMING_DIR, src_filename)
    base_name, ext = os.path.splitext(src_filename)
    ext = ext.lower()

    logging.info("Начинаем обработку файла: %s", src_filename)

    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if ext in IMAGE_EXTS:
            # просто копируем изображение как есть
            dst_filename = make_dest_filename(src_filename)  # то же расширение
            dst_path = os.path.join(OUTPUT_DIR, dst_filename)
            if copy_image_as_is(src_path, dst_path):
                logging.info("Изображение сохранено: %s", dst_filename)
                os.remove(src_path)
                logging.info("Исходник удалён: %s", src_filename)
            else:
                logging.error("Срыв копирования изображения: %s", src_filename)

        elif ext in DOC_EXTS:
            # документ -> PNG (первая страница)
            dst_filename_png = make_dest_filename(src_filename, ".png")
            ok = handle_document(src_path, ext, dst_filename_png)
            if ok:
                logging.info("PNG создан: %s", dst_filename_png)
                os.remove(src_path)
                logging.info("Исходник удалён: %s", src_filename)
            else:
                logging.error("Не удалось создать PNG для: %s", src_filename)

        else:
            logging.warning("Неподдерживаемый формат: %s", src_filename)

        logging.info("Обработка завершена: %s", src_filename)

    except Exception as e:
        logging.error("Критическая ошибка обработки (%s): %s", src_filename, e)
        logging.error(traceback.format_exc())

def main():
    if not os.path.isdir(INCOMING_DIR):
        logging.error("INCOMING_DIR не найден: %s", INCOMING_DIR)
        print(f"❗ INCOMING_DIR не найден: {INCOMING_DIR}")
        return

    files = [f for f in sorted(os.listdir(INCOMING_DIR)) if not f.startswith('.')]
    if not files:
        logging.info("Нет файлов для обработки.")
        print("Нет файлов для обработки.")
        return

    for f in files:
        process_one(f)

if __name__ == "__main__":
    main()