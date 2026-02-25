#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LuckyBot/handlers/registration_agent.py
Регистрация клиента + живой Guard (с короткой памятью в FSMContext).

DEV/PROD:
- SUPERADMIN_ID (ENV) всегда DEV: /start запускает регистрацию заново.
- Все остальные: если уже registered/stage DONE, /start НЕ сбрасывает, а показывает меню.
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path

from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext

from LuckyBot.handlers.registration_api import fetch_company_raw
from LuckyBot.handlers.registration_normalize import normalize_company
from LuckyBot.handlers.registration_registry import upsert_company
from LuckyBot.keyboards.main_menu import build_main_menu

from AI.registration_guard import guard as registration_guard


# ===============================
# DATA
# ===============================

DATA_USERS = Path("/srv/luckypack/data/clients_registry/users")
DATA_USERS.mkdir(parents=True, exist_ok=True)

_GH_KEY = "guard_history"
_GH_MAX = 6  # 3 пары user/bot


# ===============================
# UTILS
# ===============================

def _get_superadmin_id() -> int:
    """
    Берём SUPERADMIN_ID из ENV.
    Поддерживаем несколько имён на случай разночтений.
    """
    for k in ("SUPERADMIN_ID", "SUPER_ADMIN_ID", "SUPERADMIN_TG_ID", "SUPER_ADMIN_TG_ID"):
        v = os.getenv(k)
        if v and v.strip().isdigit():
            return int(v.strip())
    return 0


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
            "company_profile": None,
        },
    }


def save_user(u: dict):
    u["updated_at"] = datetime.utcnow().isoformat()
    _user_path(u["tg_user_id"]).write_text(
        json.dumps(u, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def is_inn(text: str) -> bool:
    return bool(re.fullmatch(r"\d{10}|\d{12}", (text or "").strip()))


def normalize_yes_no(text: str):
    t = (text or "").strip().lower()
    if t in {"да", "ok", "ок", "yes", "угу", "ага"}:
        return True
    if t in {"нет", "no", "неа"}:
        return False
    return None


# ===============================
# GUARD SHORT MEMORY
# ===============================

async def _gh_reset(state: FSMContext):
    await state.update_data(**{_GH_KEY: []})


async def _gh_get(state: FSMContext):
    data = await state.get_data()
    hist = data.get(_GH_KEY, [])
    return hist if isinstance(hist, list) else []


async def _gh_add(state: FSMContext, role: str, text: str):
    text = (text or "").strip()
    if not text:
        return
    hist = await _gh_get(state)
    hist.append({"role": role, "text": text})
    hist = hist[-_GH_MAX:]
    await state.update_data(**{_GH_KEY: hist})


# ===============================
# TEXTS
# ===============================

POLICY_URL = "https://drive.google.com/file/d/1Ewc1vAbDsEcbonExfEvrflXFHnyhQ_LI/view?usp=drive_link"

WELCOME_TEXT = (
    "Здравствуйте! 🙂\n"
    "Рады приветствовать вас в среде нейро-поддержки компании Lucky Pack.\n\n"
    "Чтобы предоставить Вам доступ ко всем возможностям сервиса, "
    "нам необходимо познакомиться и определить вашу организацию. "
    "Это займёт меньше минуты..."
)

ASK_NAME = "Как я могу к Вам обращаться?"

ASK_INN = (
    "Пожалуйста, пришлите ИНН вашей организации (10–12 цифр).\n\n"
    "<i>Отправляя ИНН, Вы подтверждаете согласие с «Политикой обработки данных».</i>\n"
    f'<a href="{POLICY_URL}"><u>Ознакомиться с документом</u></a>'
)

INN_NOT_FOUND = (
    "По этому ИНН ничего не найдено.\n"
    "Проверьте цифры и отправьте ещё раз."
)

CONFIRM_TEMPLATE = (
    "Найдена организация:\n{title}\nИНН {inn}\n\n"
    "Это Ваша компания? (да/нет)"
)

REG_DONE = "Отлично. Регистрация завершена! ✅\n"


# ===============================
# HANDLER
# ===============================

def register(dp: Dispatcher):

    @dp.message_handler(commands=["start"], state="*")
    async def start(message: types.Message, state: FSMContext):

        await _gh_reset(state)

        superadmin_id = _get_superadmin_id()
        is_superadmin = (superadmin_id != 0 and message.from_user.id == superadmin_id)

        u = load_user(message.from_user.id)

        # PROD: уже зарегистрированным (НЕ супер-админу) не сбрасываем регистрацию
        if (not is_superadmin) and (u.get("registered") is True or u.get("stage") == "DONE"):
            name = (u.get("slots") or {}).get("name") or "друг"
            msg = f"С возвращением, {name}! 🙂\nЧем могу быть полезен сегодня?"
            await message.answer(msg, reply_markup=build_main_menu())
            await _gh_add(state, "bot", msg)
            return

        # DEV (супер-админ) и незарегистрированные: начинаем регистрацию заново
        u["stage"] = "WAIT_NAME"
        u["registered"] = False
        save_user(u)

        await message.answer(WELCOME_TEXT)
        await _gh_add(state, "bot", WELCOME_TEXT)

        await message.answer(ASK_NAME)
        await _gh_add(state, "bot", ASK_NAME)

    @dp.message_handler(state="*")
    async def flow(message: types.Message, state: FSMContext):

        text = (message.text or "").strip()
        await _gh_add(state, "user", text)

        u = load_user(message.from_user.id)
        stage = u.get("stage") or "START"

        # ===== Guard for deviations =====
        need_guard = False
        if stage == "WAIT_INN" and text and not is_inn(text):
            need_guard = True
        elif stage == "CONFIRM_COMPANY" and normalize_yes_no(text) is None:
            need_guard = True
        elif stage == "WAIT_NAME" and is_inn(text):
            need_guard = True

        if need_guard:
            history = await _gh_get(state)
            g = registration_guard(stage, text, history=history)

            reply = (g.get("reply") or "").strip()
            extracted = g.get("extracted") or {}

            if extracted.get("name"):
                u["slots"]["name"] = extracted["name"]
                u["stage"] = "WAIT_INN"
                save_user(u)

            if extracted.get("inn") and is_inn(extracted["inn"]):
                u["slots"]["inn"] = extracted["inn"]
                u["stage"] = "WAIT_INN"
                save_user(u)

            if reply:
                await message.answer(reply)
                await _gh_add(state, "bot", reply)
                return

        # ===== WAIT_NAME =====
        if u["stage"] == "WAIT_NAME":
            u["slots"]["name"] = text
            u["stage"] = "WAIT_INN"
            save_user(u)

            msg = f"{text}, приятно познакомиться! 🙂\n\n{ASK_INN}"
            await message.answer(msg)
            await _gh_add(state, "bot", msg)
            return

        # ===== WAIT_INN =====
        if u["stage"] == "WAIT_INN":

            if not is_inn(text):
                await message.answer(ASK_INN)
                await _gh_add(state, "bot", ASK_INN)
                return

            inn = text.strip()

            try:
                fetch_company_raw(inn)
                profile = normalize_company(inn)
            except Exception:
                await message.answer(INN_NOT_FOUND)
                await _gh_add(state, "bot", INN_NOT_FOUND)
                return

            u["slots"]["inn"] = inn
            u["slots"]["company_profile"] = profile
            u["stage"] = "CONFIRM_COMPANY"
            save_user(u)

            title = (
                profile.get("name_short_with_opf")
                or profile.get("name_short")
                or profile.get("name_full_with_opf")
                or profile.get("name_full")
                or "Организация"
            )

            msg = CONFIRM_TEMPLATE.format(title=title, inn=inn)
            await message.answer(msg)
            await _gh_add(state, "bot", msg)
            return

        # ===== CONFIRM =====
        if u["stage"] == "CONFIRM_COMPANY":

            yn = normalize_yes_no(text)

            if yn is None:
                msg = "Пожалуйста, ответьте «да» или «нет»."
                await message.answer(msg)
                await _gh_add(state, "bot", msg)
                return

            if not yn:
                u["stage"] = "WAIT_INN"
                save_user(u)
                await message.answer(ASK_INN)
                await _gh_add(state, "bot", ASK_INN)
                return

            profile = u["slots"].get("company_profile") or {}

            try:
                inn = u["slots"].get("inn")
                if inn:
                    upsert_company(profile)
            except Exception:
                pass

            u["registered"] = True
            u["stage"] = "DONE"
            save_user(u)

            await message.answer(REG_DONE, reply_markup=build_main_menu())
            await _gh_add(state, "bot", REG_DONE)
            return

        # ===== DONE =====
        if u["stage"] == "DONE":
            msg = "Вы уже зарегистрированы."
            await message.answer(msg, reply_markup=build_main_menu())
            await _gh_add(state, "bot", msg)
            return