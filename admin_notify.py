#!/usr/bin/env python3
"""
admin_notify.py — Универсальный модуль для алертов админу LuckyPackBot

-----------------------------------------------------
Назначение:
    • Отправляет любые критичные ошибки и события админу (через Telegram API)
    • Дублирует все алерты в отдельный лог logs/admin_notify.log (для аудита)
    • Используется во всех ключевых скриптах (парсеры, обработчики, AI-агенты)
    • Сообщение можно вызывать из любого модуля: notify_admin("Ошибка в select_products: ...")

Требования:
    — В .env заданы TELEGRAM_BOT_TOKEN и SUPERADMIN_ID
    — Каталог logs/ существует (создаётся автоматически)
-----------------------------------------------------
"""

import os
import requests
import datetime
from config import LOGS_DIR


LOG_DIR = LOGS_DIR
LOG_PATH = os.path.join(LOGS_DIR, "admin_notify.log")
os.makedirs(LOGS_DIR, exist_ok=True)

def write_admin_log(msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_PATH, "a", encoding="utf-8") as logf:
        logf.write(f"[{ts}] {msg}\n")

def notify_admin(msg: str, module: str = None):
    """
    Отправляет текстовое уведомление админу в Telegram и пишет в лог.
    msg — текст события или ошибки.
    module — опционально, название скрипта/модуля для метки (например, 'select_products', 'universal_pars')
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        admin_id = os.getenv("SUPERADMIN_ID")
        if not token or not admin_id:
            write_admin_log(f"❗ Не заданы TELEGRAM_BOT_TOKEN / SUPERADMIN_ID: {msg}")
            return

        prefix = f"[{module}] " if module else ""
        msg_clean = (prefix + msg).strip()
        msg_clean = msg_clean[:4096]  # Telegram лимит
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": admin_id,
            "text": msg_clean,
            "parse_mode": "HTML"
        }
        requests.post(url, data=data, timeout=10)
        write_admin_log(msg_clean)
    except Exception as e:
        write_admin_log(f"❗ Ошибка notify_admin: {e}; Исходное сообщение: {msg}")