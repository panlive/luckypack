#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LuckyBot/keyboards/main_menu.py — главное меню бота

Назначение:
  • Определяет клавиатуру главного меню.
  • Используется во всех хендлерах для возврата в корень.
  • Экспортирует функции и переменные для совместимости любых импортов.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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

# Совместимость старых импортов
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return build_main_menu()

# Имя, которое ожидает registration_agent.py
def get_main_menu() -> InlineKeyboardMarkup:
    return build_main_menu()

# Готовый объект клавиатуры (если где-то импортят переменную)
main_menu_kb = build_main_menu()
