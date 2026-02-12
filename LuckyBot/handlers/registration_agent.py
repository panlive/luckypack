#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
registration_agent.py
Единый регистрационный сценарий (детерминированный, без ИИ).

Задачи:
- каноничные тексты
- строгие этапы
- без зацикливаний
- после регистрации — МЕНЮ
"""

from aiogram import Dispatcher, types
from pathlib import Path
import json
import re
from datetime import datetime

from LuckyBot.handlers.registration_api import fetch_company_raw
from LuckyBot.handlers.registration_normalize import normalize_company
from LuckyBot.handlers.registration_registry import upsert_company
from LuckyBot.keyboards.main_menu import get_main_menu

DATA_USERS = Path("/srv/luckypack/data/clients_registry/users")
DATA_USERS.mkdir(parents=True, exist_ok=True)

# ---------- утилиты ----------

def _user_path(tg_id: int) -> Path:
    return DATA_USERS / f"tg_{tg_id}.json"

def load_user(tg_id: int) -> dict:
    p = _user_path(tg_id)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "tg_user_id": tg_id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": None,
        "stage": "START",
        "registered": False,
        "slots": {
            "name": None,
            "inn": None,
        },
    }

def save_user(u: dict):
    u["updated_at"] = datetime.utcnow().isoformat()
    _user_path(u["tg_user_id"]).write_text(
        json.dumps(u, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def is_inn(text: str) -> bool:
    return bool(re.fullmatch(r"\d{10}|\d{12}", text))

# ---------- тексты (КАНОНИЧЕСКИЕ) ----------

WELCOME_TEXT = (
    "👋 Добро пожаловать в среду нейро-поддержки LuckyPack!\n\n"
    "Чтобы воспользоваться всеми возможностями сервиса, "
    "нам необходимо познакомиться поближе.\n\n"
    "После этого Вам будут доступны:\n"
    "• 📄 Скачать Прайсы\n"
    "• 📥 Сделать Заказ\n"
    "• 🔍 Подбор Товаров\n"
    "• 🖼️ Подбор по Фото\n"
    "• 🚚 Доставка и Сборка\n"
    "• 📚 База Знаний\n"
    "• 👤 Связь с Менеджером"
)

ASK_NAME = "Как я могу к Вам обращаться?"
ASK_INN = "Пожалуйста, пришлите ИНН вашей компании — 10–12 цифр."
INN_NOT_FOUND = (
    "По этому ИНН ничего не найдено.\n"
    "Проверьте, пожалуйста, цифры и отправьте ИНН ещё раз."
)

CONFIRM_TEMPLATE = "Нашёл компанию:\n{title}\nИНН {inn}\n\nПодтвердите, пожалуйста: это Вы? (да/нет)"

REG_DONE = "Отлично, спасибо! Регистрация завершена ✅"

# ---------- хендлер ----------

def register(dp: Dispatcher):

    @dp.message_handler(commands=["start"], state="*")
    async def start(message: types.Message):
        u = load_user(message.from_user.id)
        u["stage"] = "WAIT_NAME"
        save_user(u)

        await message.answer(WELCOME_TEXT)
        await message.answer(ASK_NAME)

    @dp.message_handler(state="*")
    async def flow(message: types.Message):
        text = (message.text or "").strip()
        u = load_user(message.from_user.id)

        # ---- имя ----
        if u["stage"] == "WAIT_NAME":
            u["slots"]["name"] = text
            u["stage"] = "WAIT_INN"
            save_user(u)
            await message.answer(f"{text}, приятно познакомиться!\n{ASK_INN}")
            return

        # ---- ИНН ----
        if u["stage"] == "WAIT_INN":
            if not is_inn(text):
                await message.answer(ASK_INN)
                return

            try:
                raw = fetch_company_raw(text)
                profile = normalize_company(text)
            except Exception:
                await message.answer(INN_NOT_FOUND)
                return

            title = (
                profile.get("name_short_with_opf")
                or profile.get("name_full_with_opf")
                or profile.get("name_short")
                or profile.get("name_full")
                or "Компания"
            )
            u["slots"]["inn"] = text
            u["slots"]["company_profile"] = profile
            u["stage"] = "CONFIRM_COMPANY"
            save_user(u)

            await message.answer(CONFIRM_TEMPLATE.format(title=title, inn=text))
            return

        # ---- подтверждение ----
        if u["stage"] == "CONFIRM_COMPANY":
            if text.lower() not in ("да", "нет"):
                await message.answer("Пожалуйста, ответьте «да» или «нет».")
                return

            if text.lower() == "нет":
                u["slots"]["inn"] = None
                u["slots"].pop("company_profile", None)
                u["stage"] = "WAIT_INN"
                save_user(u)
                await message.answer(ASK_INN)
                return

            # ДА → регистрация
            profile = (u.get("slots") or {}).get("company_profile")
            if not isinstance(profile, dict):
                await message.answer(INN_NOT_FOUND)
                u["stage"] = "WAIT_INN"
                save_user(u)
                return
            upsert_company(profile)
            u["registered"] = True
            u["stage"] = "DONE"
            save_user(u)

            await message.answer(REG_DONE, reply_markup=get_main_menu())
            return

        # ---- после регистрации ----
        if u["stage"] == "DONE":
            await message.answer(
                "Вы уже зарегистрированы. Выберите действие в меню ниже.",
                reply_markup=get_main_menu()
            )
            return