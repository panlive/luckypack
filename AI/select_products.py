#!/usr/bin/env python3
"""
select_products.py — Смысловой поиск товаров с помощью GPT-4o, с логированием и уведомлением администратора.

-----------------------------------------------------
Назначение:
    • Позволяет по свободному текстовому запросу клиента находить нужные товары из ассортимента LuckyPack.
    • Использует OpenAI GPT-4o для интерпретации любых формулировок клиента (ошибки, сленг, неформальный стиль).
    • Автоматически подбирает товары по смыслу: цвет, назначение, оттенки, параметры.
    • Все действия и ошибки логируются в logs/select_products.log.
    • Критичные ошибки (сбои OpenAI, парсинг, отсутствие данных) отправляются админу LuckyPackBot в Telegram (через admin_notify.py).
    • Работает как консольный скрипт: запрос вводится вручную, результат сохраняется в selected.json.

Что происходит шаг за шагом:
    1. Загружает все JSON-файлы товаров из LuckyPricer/data/jsons/.
    2. Запрашивает у пользователя текстовый запрос (любое описание).
    3. Формирует мощный PROMPT для GPT-4o, чтобы AI понимал смысл даже неявных и “кривых” сообщений.
    4. Отправляет первые 100 товаров и текст запроса в GPT-4o.
    5. Получает от GPT-4o массив отобранных товаров (JSON).
    6. Сохраняет результат в LuckyPricer/data/selected.json.
    7. Все этапы и ошибки пишутся в logs/select_products.log.
    8. Все критичные ошибки дублируются админу в Telegram.

Требования:
    — Файл admin_notify.py должен быть в корне проекта.
    — В .env прописаны OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, SUPERADMIN_ID.
    — Каталог logs/ существует (создаётся автоматически).
    — Запускать из любой среды (терминал VSCode, ssh и т.д.)

Автор: LuckyPackProject / 2025
-----------------------------------------------------
"""
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
import json
import datetime
from dotenv import load_dotenv
import openai
import traceback

from admin_notify import notify_admin

# --- Загрузка конфигурации и ключей ---
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    err_msg = "❌ OPENAI_API_KEY не найден в .env"
    print(err_msg)
    notify_admin(err_msg)
    raise RuntimeError(err_msg)
openai.api_key = api_key

# --- Пути ---
BASE = os.path.dirname(os.path.abspath(__file__))
JSON_DIR = os.path.normpath(os.path.join(BASE, "..", "LuckyPricer", "data", "jsons"))
OUTPUT_PATH = os.path.normpath(os.path.join(BASE, "..", "LuckyPricer", "data", "selected.json"))
LOG_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "select_products.log")

os.makedirs(LOG_DIR, exist_ok=True)

def write_log(msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_PATH, "a", encoding="utf-8") as logf:
        logf.write(f"[{ts}] {msg}\n")

def main():
    try:
        # --- Получаем запрос от пользователя ---
        query = input("🗣️ Введите запрос клиента (например: красная плёнка и бежевый фоамиран):\n> ")
        write_log(f"Получен запрос: {query}")

        # --- Загружаем товары ---
        products = []
        loaded_files = 0
        for fname in os.listdir(JSON_DIR):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(JSON_DIR, fname), "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        products.extend(loaded)
                        loaded_files += 1
                except Exception as e:
                    err_msg = f"⚠️ Ошибка в файле {fname}: {e}"
                    print(err_msg)
                    write_log(err_msg)
                    notify_admin(err_msg)

        write_log(f"Загружено товаров: {len(products)} из {loaded_files} файлов.")

        if not products:
            err_msg = "❌ Нет товаров для поиска!"
            print(err_msg)
            write_log(err_msg)
            notify_admin(err_msg)
            return

        # --- PROMPT для GPT-4o ---
        system_prompt = """
Ты — умный ассистент по подбору упаковки.
У тебя есть список товаров (ассортимент) в формате JSON.

Клиент написал, что ищет — это может быть любой текст: с ошибками, сленгом, опечатками, сокращениями или необычной формулировкой.
Игнорируй орфографические и пунктуационные ошибки, понимай смысл даже запутанных или неформальных запросов.

Твоя задача — выбрать из списка только те товары, которые реально соответствуют запросу по смыслу, цвету, назначению, оттенкам, параметрам, даже если совпадение не точное.

Отдай ответ только в виде массива JSON-объектов (без пояснений и комментариев).

Пример запроса: "Мне бы что-то розовое, как зефир, но не яркое и не матовое, чтобы на 8 марта подошло".
Твоя задача — понять, что человек ищет светло-розовые, возможно полупрозрачные или глянцевые упаковочные материалы для подарков на весенний праздник.

Формат ответа — строго JSON (массив товаров).
""".strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Запрос клиента: {query}\n\nСписок товаров:\n{json.dumps(products[:100], ensure_ascii=False)}"}
        ]

        # --- Запрос к OpenAI GPT-4o ---
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                temperature=0.3,
                messages=messages
            )
        except Exception as e:
            err_msg = f"❌ Ошибка обращения к OpenAI: {e}"
            print(err_msg)
            write_log(err_msg)
            write_log(traceback.format_exc())
            notify_admin(err_msg)
            return

        reply = response["choices"][0]["message"]["content"]

        # --- Сохраняем результат ---
        try:
            result = json.loads(reply)
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"✅ Найдено товаров: {len(result)}")
            print(f"📁 Сохранено в: {OUTPUT_PATH}")
            write_log(f"✅ Найдено товаров: {len(result)}. Результат сохранён в {OUTPUT_PATH}")
        except Exception as e:
            err_msg = f"❌ Ошибка при разборе ответа от GPT: {e}"
            print(err_msg)
            print("Ответ GPT:\n", reply)
            write_log(err_msg)
            write_log(f"Ответ GPT:\n{reply}")
            write_log(traceback.format_exc())
            notify_admin(err_msg)
    except Exception as e:
        err_msg = f"❌ Критическая ошибка: {e}"
        print(err_msg)
        write_log(err_msg)
        write_log(traceback.format_exc())
        notify_admin(err_msg)

if __name__ == "__main__":
    main()