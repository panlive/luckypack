#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LuckyBot/keyboards/main_menu.py — главное меню бота

Назначение:
  • Определяет клавиатуру главного меню.
  • Используется во всех хендлерах для возврата в корень.
  • Экспортирует и функцию main_menu_keyboard(), и переменную main_menu_kb — для совместимости любых импортов.
Примечания:
  • Кнопки расположены в один столбец (row_width=1).
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# === Основная клавиатура главного меню ===
def build_main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(text="📄 Прайсы", callback_data="menu_prices"))
    kb.add(InlineKeyboardButton(text="📷 Подбор по фото", callback_data="menu_photo"))
    kb.add(InlineKeyboardButton(text="🔍 Подбор по тексту", callback_data="menu_search"))
    kb.add(InlineKeyboardButton(text="🛒 Сделать заказ", callback_data="menu_sendorder"))
    kb.add(InlineKeyboardButton(text="🚚 Доставка и сборка", callback_data="menu_delivery"))
    kb.add(InlineKeyboardButton(text="📚 База знаний", callback_data="menu_knowledge"))
    kb.add(InlineKeyboardButton(text="👤 Связь с менеджером", callback_data="menu_manager"))
    return kb

# === Совместимость интерфейсов ===
# 1) Функция, как в старой схеме
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return build_main_menu()

# 2) Переменная, как в новой схеме
main_menu_kb = build_main_menu()

# 3) На всякий случай экспортим и привычное имя
get_main_menu_kb = build_main_menu