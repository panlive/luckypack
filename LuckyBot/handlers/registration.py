#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
registration.py — версия V2 (агентная).
Вся логика регистрации полностью передана RegistrationBrain.

Файл делает только три вещи:
1) /start — приветствие + кнопка.
2) start_reg — создаёт пустое состояние и ждёт первое сообщение.
3) Любое сообщение → в RegistrationBrain → ждём reply_text → показываем клиенту.

Никаких FSM, никаких validate-INN, никаких reg-веток.
"""

from aiogram import types, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from AI.registration_brain.brain import run_registration_brain
from AI.registration_brain.models import RegistrationState, BrainOutput


# --------------------------------------------------------------------
# 1. Приветствие
# --------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 Добро пожаловать в среду нейро-поддержи LuckyPack!\n\n"
    "Мы тестируем новую V2-схему регистрации на базе агентного мозга.\n"
    "Нажмите кнопку ниже, чтобы начать."
)


def register(dp: Dispatcher):

    # --------------------------------------------------------------
    # /start — просто показать кнопку
    # --------------------------------------------------------------
    @dp.message_handler(commands=["start"], state="*")
    async def handle_start(message: types.Message):
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("НАЧАТЬ ЗНАКОМСТВО", callback_data="start_reg")
        )
        await message.answer(WELCOME_TEXT, reply_markup=kb)

    # --------------------------------------------------------------
    # Старт регистрации — создаём пустое состояние
    # --------------------------------------------------------------
    @dp.callback_query_handler(lambda c: c.data == "start_reg", state="*")
    async def cb_start_reg(callback: types.CallbackQuery):
        # Пустое состояние (нулевое)
        state = RegistrationState(
            stage="START",
            slots={},
            history_short="",
            memory_summary=None,
        )

        text = (
            "Отлично 👍\n\n"
            "Я готов. Напишите первое сообщение — и дальше я буду отвечать "
            "живым человеческим текстом на основе RegistrationBrain."
        )

        # сохраняем state в user_data
        await dp.storage.set_data(
            user=callback.from_user.id,
            chat=callback.message.chat.id,
            data={"reg_state": state.dict()}
        )

        await callback.message.answer(text)
        await callback.answer()

    # --------------------------------------------------------------
    # Любое текстовое сообщение после старта → прямой вызов мозга
    # --------------------------------------------------------------
    @dp.message_handler(content_types=types.ContentTypes.TEXT, state="*")
    async def all_messages(message: types.Message):
        # достаём состояние
        data = await dp.storage.get_data(
            user=message.from_user.id,
            chat=message.chat.id
        )
        raw_state = data.get("reg_state")

        # если состояния нет — просим нажать /start
        if not raw_state:
            await message.answer("Нажмите /start, чтобы начать регистрацию.")
            return

        # превращаем dict → модель
        state = RegistrationState.from_dict(raw_state)

        # вызов мозга
        brain: BrainOutput = run_registration_brain(state, message.text)

        # показываем ответ
        await message.answer(brain.reply_text)

        # обновляем state в хранилище (но stage мы пока НЕ меняем)
        new_state = RegistrationState(
            stage=brain.new_stage,
            slots=state.slots,
            history_short=state.history_short,
            memory_summary=state.memory_summary,
        )

        await dp.storage.set_data(
            user=message.from_user.id,
            chat=message.chat.id,
            data={"reg_state": new_state.dict()}
        )