#!/usr/bin/env python3
"""
client_message_analyzer.py — Анализатор текстовых сообщений клиента для LuckyPackBot

-----------------------------------------------------
Назначение:
    • Обрабатывает произвольный текст от клиента (если не прислана карточка предприятия).
    • Извлекает ИНН, телефон, e-mail, а также статус намерения клиента (юридическое лицо, отказ, попытка уйти от идентификации и пр.).
    • Использует OpenAI GPT (gpt-4o) для гибкого смыслового анализа, чтобы корректно реагировать даже на нечёткие формулировки, опечатки и жаргон.
    • Возвращает структуру с подробной разбивкой: что найдено, статус, какие поля клиент оставил.
    • Все действия и ошибки логируются в logs/client_message_analyzer.log.
    • Критичные ошибки (сбои OpenAI, невозможность разбора) отправляются админу в Telegram (admin_notify.py).
    • Легко расширяется новыми статусами, полями, сценариями.

Что происходит шаг за шагом:
    1. Получает текст от клиента (произвольное сообщение).
    2. Сначала пробует вытащить ИНН, телефон, e-mail регулярками.
    3. Если что-то найдено — возвращает статус и найденные значения.
    4. Если не найдено — обращается к GPT-4o с подробным промптом для смыслового разбора (определяет, как клиент хочет продолжить общение).
    5. Все этапы и ошибки пишутся в лог.
    6. Все критичные ошибки дублируются админу LuckyPackBot в Telegram.

Требования:
    — admin_notify.py в корне проекта.
    — В .env прописаны OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, SUPERADMIN_ID.
    — Каталог logs/ существует (создаётся автоматически).

Статусы (status):
    - valid_inn — найден валидный ИНН (10 или 12 цифр)
    - valid_phone — найден валидный телефон
    - valid_email — найден e-mail
    - company_info — признаки юрлица, но нет ИНН
    - card_decline — явно отказался присылать карточку
    - decline_all — не хочет присылать никаких данных, но хочет продолжить
    - none — ничего не найдено (пустой или бессмысленный текст)
    - unknown — не удалось однозначно классифицировать

-----------------------------------------------------
"""
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
import re
import json
import datetime
from dotenv import load_dotenv
import openai
import traceback

from admin_notify import notify_admin

# --- Настройки логирования ---
BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "client_message_analyzer.log")
os.makedirs(LOG_DIR, exist_ok=True)

def write_log(msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_PATH, "a", encoding="utf-8") as logf:
        logf.write(f"[{ts}] {msg}\n")

# --- Загрузка ключа OpenAI ---
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- Регулярки для извлечения данных ---
def extract_inn(text: str) -> str | None:
    match = re.search(r"\b\d{10,12}\b", text)
    return match.group(0) if match else None

def extract_phone(text: str) -> str | None:
    match = re.search(r"\+?\d{10,15}", text)
    return match.group(0) if match else None

def extract_email(text: str) -> str | None:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    return match.group(0) if match else None

# --- Основная функция анализа ---
def analyze_client_message(message_text: str) -> dict:
    try:
        write_log(f"Получено сообщение: {message_text!r}")

        inn = extract_inn(message_text)
        phone = extract_phone(message_text)
        email = extract_email(message_text)

        if inn:
            write_log(f"Найден ИНН: {inn}")
            return {"status": "valid_inn", "inn": inn, "phone": phone, "email": email}
        if phone:
            write_log(f"Найден телефон: {phone}")
            return {"status": "valid_phone", "inn": None, "phone": phone, "email": email}
        if email:
            write_log(f"Найден e-mail: {email}")
            return {"status": "valid_email", "inn": None, "phone": phone, "email": email}

        # --- PROMPT для GPT ---
        system_prompt = """
Ты — ассистент в Telegram-боте B2B компании LuckyPack.

Тебе прислали текст от клиента. Нужно понять по смыслу, как действовать дальше.
Возможные ситуации:
- valid_inn: если явно указан ИНН (10 или 12 цифр)
- valid_phone: если указан телефон
- valid_email: если указан e-mail
- company_info: если есть признаки юрлица (ООО, ИП и т.п.), но нет ИНН
- card_decline: если клиент отказывается присылать карточку предприятия
- decline_all: если не хочет присылать ни ИНН, ни карточку, ни контакты, но хочет продолжить общение
- none: если вообще ничего не понятно или бессмысленный текст

Ответь строго в формате JSON:
{"status": "...", "inn": null, "phone": null, "email": null}

Статус выбери только из предложенных. Если что-то найдено — заполни соответствующее поле.
""".strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f'Текст клиента: "{message_text.strip()}"'}
        ]

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                temperature=0.1,
                messages=messages,
                max_tokens=200
            )
            reply = response.choices[0].message.content.strip()
            write_log(f"Ответ GPT: {reply}")
            result = json.loads(reply)
            return result
        except Exception as e:
            err_msg = f"❌ Ошибка при обращении к OpenAI: {e}"
            write_log(err_msg)
            write_log(traceback.format_exc())
            notify_admin(err_msg)
            return {"status": "unknown", "inn": None, "phone": None, "email": None}

    except Exception as e:
        err_msg = f"❌ Критическая ошибка анализа сообщения: {e}"
        write_log(err_msg)
        write_log(traceback.format_exc())
        notify_admin(err_msg)
        return {"status": "unknown", "inn": None, "phone": None, "email": None}

# --- Пример теста (если нужен для отладки) ---
if __name__ == "__main__":
    text = input("Введите текст клиента:\n> ")
    result = analyze_client_message(text)
    print("Результат анализа:", result)