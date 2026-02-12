#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LuckyBot/main.py — оркестратор бота (aiogram 2.25.x)
Задача: инициализировать bot/dp и зарегистрировать ХЕНДЛЕРЫ (только /start).
Никакой бизнес-логики здесь нет.
"""

import os
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

# --- конфиг и .env ---
try:
    from dotenv import load_dotenv
    load_dotenv("/srv/luckypack/.env")
except Exception:
    pass

try:
    from config import TELEGRAM_BOT_TOKEN
except Exception:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не найден (ни в config.py, ни в .env)")

# --- инициализация бота ---
bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

# --- регистрация минимального набора хендлеров ---

# Старая регистрация (скриптовая логика v1 — пока остаётся рабочей)
# from LuckyBot.handlers.registration import register as register_registration
# register_registration(dp)

# Новая агентная регистрация (RegistrationBrain).
# Сейчас хендлер-пустышка, позже здесь появится реальная логика.
from LuckyBot.handlers.registration_agent import register as register_registration_agent
register_registration_agent(dp)


async def on_startup(dispatcher: Dispatcher):
    # Чистый старт без вебхука и без pending updates
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)