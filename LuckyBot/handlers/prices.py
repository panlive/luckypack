#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handlers/prices.py — хендлеры для кнопки «📄 Прайсы»

Назначение:
  • Вход в подменю «Прайсы» (callback_data="menu_prices").
  • «📥 Получить Excel файлы в чат» — отправка .xlsx партиями ≤10, без временных файлов.
  • «◀️ В главное меню» — возврат к корневой клавиатуре.
Примечания:
  • «📦 Скачать архив по ссылке» и «📧 Отправить архив по e-mail» будут добавлены отдельными шагами.
  • Обработчик не создаёт временных файлов; пишет только в стандартные логи бота.
"""

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import os, asyncio, glob

# Путь к прайсам (подбираем автоматически)
PRICES_DIRS = [
    "/app/LuckyPricer/data/prices",
    "/srv/luckypack/App/LuckyPricer/data/prices"
]


def pick_prices_dir():
    for d in PRICES_DIRS:
        if os.path.isdir(d):
            return d
    return None


# === Клавиатура подменю Прайсов ===
def get_prices_menu():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(text="📥 Получить Excel файлы в чат", callback_data="prices_chat"))
    kb.add(InlineKeyboardButton(text="📦 Скачать архив по ссылке", callback_data="prices_link"))
    kb.add(InlineKeyboardButton(text="📧 Отправить архив по e-mail", callback_data="prices_email"))
    kb.add(InlineKeyboardButton(text="◀️ В главное меню", callback_data="prices_back"))
    return kb

# === Постоянная нижняя кнопка у поля ввода ===
# Показ: одноразово включаем в любом подменю, дальше она висит до замены/удаления

def get_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton('🏠 Меню')]],
        resize_keyboard=True,
        one_time_keyboard=False
    )


# === Вход в подменю «Прайсы» ===
def register_menu_prices(dp):
    async def _handle_menu_prices(callback: types.CallbackQuery):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        text = "Прайсы.\n\nВыберите действие ниже ⬇️"
        await callback.message.answer(text, reply_markup=get_prices_menu())
        await callback.answer()
    dp.register_callback_query_handler(_handle_menu_prices, lambda c: c.data == "menu_prices")


# === Обработчик "📥 Excel файлы в чат" ===
def register_prices_chat(dp):
    from aiogram.utils.exceptions import RetryAfter

    async def _send_doc_with_retry(message, path):
        try:
            await message.answer_document(types.InputFile(path), caption=os.path.basename(path))
            return True
        except RetryAfter as e:
            await asyncio.sleep(getattr(e, "timeout", 2) + 1)
            try:
                await message.answer_document(types.InputFile(path), caption=os.path.basename(path))
                return True
            except Exception:
                return False
        except Exception:
            return False

    async def _handle_prices_chat(callback: types.CallbackQuery):
        try:
            prices_dir = pick_prices_dir()
            if not prices_dir:
                await callback.message.answer("Никак: каталог прайсов не найден. Проверь путь к прайсам.")
                await callback.answer()
                return

            files = sorted(f for f in glob.glob(os.path.join(prices_dir, "*.xlsx")) if os.path.isfile(f))
            if not files:
                await callback.message.answer("Сейчас актуальных прайсов нет — отправлять нечего.")
                await callback.message.answer("Ещё действия с прайсами:", reply_markup=get_prices_menu())
                await callback.answer()
                return

            CHUNK = 10
            sent = 0
            failed = []
            for i in range(0, len(files), CHUNK):
                batch = files[i:i+CHUNK]
                for f in batch:
                    ok = await _send_doc_with_retry(callback.message, f)
                    if ok:
                        sent += 1
                        await asyncio.sleep(0.2)
                    else:
                        failed.append(os.path.basename(f))
                await asyncio.sleep(0.7)

            msg = f"📤 Отправил {sent} файл(ов)."
            if failed:
                msg += ("\n⚠️ Не отправлены: " + ", ".join(failed) +
                        "\nСовет: используйте «📦 Скачать архив по ссылке». ")
            await callback.message.answer(msg)
            await callback.message.answer("Ещё действия с прайсами:", reply_markup=get_prices_menu())
            await callback.answer()
        except Exception as e:
            await callback.message.answer(f"Ошибка при отправке прайсов: {e}")
            await callback.message.answer("Ещё действия с прайсами:", reply_markup=get_prices_menu())
            await callback.answer()

    dp.register_callback_query_handler(_handle_prices_chat, lambda c: c.data == "prices_chat")


# === Обработчик "◀️ В главное меню" ===
def register_prices_back(dp):
    import importlib

    async def _handle_back(callback: types.CallbackQuery):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        kb = None
        try:
            mm = importlib.import_module("LuckyBot.keyboards.main_menu")
            for name in ("main_menu_kb", "get_main_menu_kb", "build_main_menu", "main_menu"):
                cand = getattr(mm, name, None)
                if callable(cand):
                    kb = cand
                    break
        except Exception:
            kb = None

        if kb:
            try:
                await callback.message.answer("Главное меню:", reply_markup=kb())
            except Exception:
                await callback.message.answer("Главное меню. Нажми /start.")
        else:
            await callback.message.answer("Главное меню. Нажми /start.")
        await callback.answer()

    dp.register_callback_query_handler(_handle_back, lambda c: c.data == "prices_back")


# === Общая регистрация ===
def register(dp):
    register_menu_prices(dp)
    register_prices_chat(dp)
    register_prices_back(dp)

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
def _build_main_menu_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📄 Прайсы", callback_data="menu_prices"))
    kb.add(InlineKeyboardButton("📷 Подбор по фото", callback_data="menu_photo"))
    kb.add(InlineKeyboardButton("🔍 Подбор по тексту", callback_data="menu_search"))
    kb.add(InlineKeyboardButton("🛒 Сделать заказ", callback_data="menu_sendorder"))
    kb.add(InlineKeyboardButton("🚚 Доставка и сборка", callback_data="menu_delivery"))
    kb.add(InlineKeyboardButton("📚 База знаний", callback_data="menu_knowledge"))
    kb.add(InlineKeyboardButton("👨‍💼 Связаться с менеджером", callback_data="menu_manager"))
    return kb


# === Глобальная кнопка у поля ввода «🏠 Меню» ===
def register_global_home_button(dp):
    from aiogram import types as _types
    async def _home_btn(message: _types.Message):
        if message.text == '🏠 Меню':
            await message.answer("Главное меню:", reply_markup=_build_main_menu_kb())
    dp.register_message_handler(_home_btn, content_types=_types.ContentTypes.TEXT)
