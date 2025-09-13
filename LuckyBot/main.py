#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Основной файл Telegram-бота LuckyPackBot

-----------------------------------------------------
Назначение:
    • Запускает Telegram-бота LuckyPackBot (aiogram)
    • Ведёт регистрацию, оперирует профилями клиентов (мульти e-mail/телефоны/история)
    • Логирует и алертит критичные ошибки админу через admin_notify.py
    • Параметры тянет из config.py
Архитектура:
    • Обработчики и сервисы вынесены в handlers/ и отдельные utils
-----------------------------------------------------
"""

import os, sys, json, asyncio
from dotenv import load_dotenv

# --- Жёсткая фиксация PYTHONPATH, чтобы всегда находился пакет LuckyBot ---
PROJECT_ROOT = "/srv/luckypack/App"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import TELEGRAM_BOT_TOKEN, SUPERADMIN_ID
from states.registration_states import Registration
from admin_notify import notify_admin

# --- Устойчивый импорт главного меню (совместимо со старой и новой схемой) ---
try:
    # старая схема: функция main_menu_keyboard в keyboards.main_menu
    from keyboards.main_menu import main_menu_keyboard as _raw_menu
    def main_menu_keyboard():
        return _raw_menu() if callable(_raw_menu) else _raw_menu
except Exception:
    # новая схема: переменная main_menu_kb в LuckyBot.keyboards.main_menu
    from LuckyBot.keyboards.main_menu import main_menu_kb as _raw_menu
    def main_menu_keyboard():
        return _raw_menu() if callable(_raw_menu) else _raw_menu
# --- конец устойчивого импорта ---

# Загрузка .env
load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

# Регистрация готовых хендлеров
from LuckyBot.handlers.neighbors import register as register_neighbors
from LuckyBot.handlers.photo_pick import register as register_photo_pick
from LuckyBot.handlers import prices
register_neighbors(dp)
register_photo_pick(dp)
prices.register(dp)

# --- Простейшее хранилище клиентов на файлах ---

def load_client(user_id):
    path = f"data/clients/{user_id}.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        notify_admin(f"Ошибка чтения профиля клиента {user_id}: {e}", module="main.py")
        return None

def save_client(client):
    path = f"data/clients/{client['user_id']}.json"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(client, f, ensure_ascii=False, indent=2)
    except Exception as e:
        notify_admin(f"Ошибка сохранения профиля клиента {client.get('user_id', '-')}: {e}", module="main.py")

def add_history(client, event, value=None):
    client.setdefault("history", []).append({"event": event, "value": value})

def add_email(client, email):
    client.setdefault("emails", [])
    if email not in client["emails"]:
        client["emails"].append(email)
        add_history(client, "email_added", email)

def add_phone(client, phone):
    client.setdefault("phones", [])
    if phone not in client["phones"]:
        client["phones"].append(phone)
        add_history(client, "phone_added", phone)

# --- Жизненный цикл ---
async def on_startup(dispatcher: Dispatcher):
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        notify_admin(f"Ошибка при запуске on_startup: {e}", module="main.py")

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    try:
        client = load_client(user_id)
        name = client.get("name") if client and client.get("name") else message.from_user.first_name

        if client and client.get("is_verified"):
            import random
            greetings = [
                f"Привет, <b>{name}</b>! 👋",
                f"С возвращением, <b>{name}</b>!",
                f"Рады видеть вас снова, <b>{name}</b>!",
            ]
            greet = random.choice(greetings)
            await message.answer(
                f"{greet}\n\nЧем могу помочь сегодня? 👇",
                reply_markup=main_menu_keyboard()
            )
            return

        photo_path = os.path.join(os.path.dirname(__file__), 'media', 'start_screen.png')
        if os.path.exists(photo_path):
            await message.answer_photo(
                InputFile(photo_path),
                caption=(
                    f"<b>Спасибо, {name}!</b> 😊\n\n"
                    "Чтобы я мог предоставить вам прайсы и сервисы, мне нужно узнать чуть больше о вас."
                ),
                parse_mode="HTML"
            )
        else:
            await message.answer("⚠️ Приветственное изображение не найдено.")

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(text="Начать регистрацию", callback_data="start_work"))
        await message.answer("Начнём регистрацию:", reply_markup=kb)
    except Exception as e:
        notify_admin(f"Ошибка в cmd_start: {e}", module="main.py")

@dp.callback_query_handler(lambda c: c.data == 'start_work')
async def start_work(callback: types.CallbackQuery):
    try:
        user = callback.from_user
        client = {
            "user_id": str(user.id),
            "username": user.username,
            "name": user.first_name,
            "is_verified": False,
            "emails": [],
            "phones": [],
            "history": []
        }
        save_client(client)
        await callback.message.answer("🤗 Приятно познакомиться! Как вас зовут?")
        await Registration.waiting_for_name.set()
    except Exception as e:
        notify_admin(f"Ошибка в start_work: {e}", module="main.py")

@dp.message_handler(state=Registration.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    try:
        client = load_client(user_id)
        name = message.text.strip()
        client["name"] = name
        add_history(client, "name_entered", name)
        save_client(client)
        prompt = (
            f"<b>Спасибо, {name}!</b> 😊\n\n"
            "Теперь пришлите, пожалуйста, карточку предприятия (PDF, Word, фото), ИНН (10–12 цифр), телефон или e-mail."
        )
        await message.answer(prompt, parse_mode="HTML")
        await Registration.waiting_for_identification.set()
    except Exception as e:
        notify_admin(f"Ошибка в process_name: {e}", module="main.py")

@dp.message_handler(state=Registration.waiting_for_identification, content_types=['document','photo','text'])
async def process_identification(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    try:
        client = load_client(user_id)
        text = message.text.strip() if message.content_type == 'text' else ""

        # --- Проверка на ИНН (10-12 цифр) ---
        if text.isdigit() and 10 <= len(text) <= 12:
            client["inn"] = text
            add_history(client, "inn_entered", text)
            client["is_verified"] = True
            save_client(client)
            await message.answer("✅ ИНН получен. Вы идентифицированы.")
            await state.finish()
            await message.answer("Чем помочь дальше? 👇", reply_markup=main_menu_keyboard())
            return

        # --- Проверка email ---
        if "@" in text and "." in text:
            add_email(client, text)
            client["is_verified"] = True
            save_client(client)
            await message.answer("Спасибо, e-mail сохранён. Менеджер свяжется с вами.")
            await state.finish()
            return

        # --- Проверка телефона ---
        if "+" in text or (text.isdigit() and len(text) in (10, 11)):
            add_phone(client, text)
            client["is_verified"] = True
            save_client(client)
            await message.answer("Спасибо, телефон сохранён. Менеджер свяжется с вами.")
            await state.finish()
            return

        # --- Документ или фото ---
        if message.document or message.photo:
            add_history(client, "card_uploaded", "файл")
            client["is_verified"] = True
            save_client(client)
            await message.answer("✅ Карточка получена. Вы идентифицированы.")
            await state.finish()
            await message.answer("Чем помочь дальше? 👇", reply_markup=main_menu_keyboard())
            return

        await message.answer("Не распознал ввод. Пожалуйста, отправьте PDF, Word, фото или корректный ИНН (10–12 цифр), телефон, e-mail.")
    except Exception as e:
        notify_admin(f"Ошибка в process_identification: {e}", module="main.py")

if __name__ == '__main__':
    try:
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
    except Exception as e:
        notify_admin(f"Критическая ошибка при запуске бота: {e}", module="main.py")
# dev-reload-test Sat Sep 13 10:59:21 PM MSK 2025
# touch Sat Sep 13 11:09:51 PM MSK 2025
