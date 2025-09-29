#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
/start: баннер + канонический текст + кнопка «НАЧАТЬ РЕГИСТРАЦИЮ».
Вступление жирным в одной строке: «…познакомиться поближе. После чего Вам будут доступны:»
"""

import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputFile

BANNER_PATH = "/srv/luckypack/data/media/start_screen.png"

CANON_TEXT = (
    "<b>Чтобы воспользоваться всеми возможностями сервиса, нам необходимо познакомиться поближе. "
    "После чего Вам будут доступны следующее меню:</b>\n\n"
    "• 📄 Скачать Прайсы\n"
    "• 📥 Сделать Заказ\n"
    "• 🔍 Подбор Товаров\n"
    "• 🖼️ Подбор по Фото\n"
    "• 🚚 Доставка и Сборка\n"
    "• 📚 База Знаний\n"
    "• 👤 Связь с Менеджером"
)

def register(dp):
    @dp.message_handler(commands=["start"], state="*")
    async def handle_start(message: types.Message):
        # 1) баннер
        if os.path.isfile(BANNER_PATH):
            try:
                await message.answer_photo(InputFile(BANNER_PATH))
            except Exception:
                pass
        # 2) текст + кнопка
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("НАЧАТЬ РЕГИСТРАЦИЮ", callback_data="start_reg"))
        await message.answer(CANON_TEXT, reply_markup=kb, disable_web_page_preview=True)
