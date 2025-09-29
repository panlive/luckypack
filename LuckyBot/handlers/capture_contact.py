# -*- coding: utf-8 -*-
# Глобальный ловец телефона/e-mail (aiogram v2)
#  • /start обрабатывается в main.py
#  • Здесь ловим только e-mail/телефон по regexp
from aiogram import types, Dispatcher
import re, traceback
from LuckyBot.ceai_bridge import ceai_apply_event

REG_DIR = "/srv/luckypack/data/clients/registry"
EMAIL_RE = r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$"
PHONE_RE = r"^\+?[0-9][0-9\s\-\(\)]{6,}$"

async def _save_email(message: types.Message):
    try:
        uid = str(message.from_user.id)
        txt = (message.text or "").strip()
        ok = ceai_apply_event(REG_DIR, uid, "email", txt)
        print(f"[capture_contact] email from {uid} -> {ok}: {txt}")
        await message.answer("✅ E-mail сохранён." if ok else "⚠️ Не удалось сохранить e-mail.")
    except Exception as e:
        print(f"[capture_contact] email error: {e}")
        print(traceback.format_exc())

async def _save_phone(message: types.Message):
    try:
        uid = str(message.from_user.id)
        txt = (message.text or "").strip()
        ok = ceai_apply_event(REG_DIR, uid, "phone", txt)
        print(f"[capture_contact] phone from {uid} -> {ok}: {txt}")
        await message.answer("✅ Телефон сохранён." if ok else "⚠️ Не удалось сохранить телефон.")
    except Exception as e:
        print(f"[capture_contact] phone error: {e}")
        print(traceback.format_exc())

def register(dp: Dispatcher):
    dp.register_message_handler(_save_email, regexp=EMAIL_RE, content_types=types.ContentType.TEXT)
    dp.register_message_handler(_save_phone, regexp=PHONE_RE, content_types=types.ContentType.TEXT)
    print("[capture_contact] handler registered (regexp-only)")
