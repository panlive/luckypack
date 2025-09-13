#!/usr/bin/env python3
"""
export_and_send.py — Экспорт товаров в Excel и отправка пользователю
"""

import os
import shutil
import time
import pandas as pd
import logging
from config import EXPORTS_DIR, JSONS_DIR, LOGS_DIR
from admin_notify import notify_admin

LOG_FILE = os.path.join(LOGS_DIR, "exports.log")

# === Логирование ===
logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)

def log_both(msg, level='info'):
    print(msg)
    getattr(logging, level)(msg)

def export_and_send(user_id: str, filter_keyword: str, send_func):
    ts = time.strftime('%Y%m%d_%H%M%S')
    export_id = f"{user_id}_{ts}"
    export_path = os.path.join(EXPORTS_DIR, export_id)
    os.makedirs(export_path, exist_ok=True)

    try:
        for json_fname in os.listdir(JSONS_DIR):
            if not json_fname.lower().endswith('.json'):
                continue
            df = pd.read_json(os.path.join(JSONS_DIR, json_fname), orient='records', dtype=str)
            df_sel = df[df['Номенклатура, Характеристика, Упаковка']
                        .str.contains(filter_keyword, case=False, na=False)]
            if df_sel.empty:
                continue
            excel_name = f"{os.path.splitext(json_fname)[0]}_{filter_keyword}.xlsx"
            df_sel.to_excel(os.path.join(export_path, excel_name), index=False)

        files_to_send = [os.path.join(export_path, f) for f in os.listdir(export_path) if f.lower().endswith('.xlsx')]

        if not files_to_send:
            log_both(f"⚠️ Пользователь {user_id}: нет файлов по фильтру '{filter_keyword}'", 'warning')
            shutil.rmtree(export_path, ignore_errors=True)
            return

        send_func(user_id, files_to_send)
        log_both(f"✅ Отправлены пользователю {user_id}: {[os.path.basename(f) for f in files_to_send]}")

        shutil.rmtree(export_path, ignore_errors=True)
        log_both(f"🧹 Временная папка {export_path} удалена")

    except Exception as e:
        err_msg = f"❌ Ошибка при экспорте/отправке пользователю {user_id}: {e}"
        log_both(err_msg, 'error')
        notify_admin(err_msg, module='export_and_send.py')