"""
registration_states.py — Состояния FSM для регистрации клиента в LuckyPackBot

-----------------------------------------------------
Назначение:
    • Описывает все этапы (шаги) регистрации нового клиента с помощью FSM (aiogram)
    • Используется в main.py/handlers для управления диалогом с пользователем
    • Позволяет строго пошагово опрашивать клиента: имя, способ идентификации, загрузка карточки, ИНН, контактные данные

Состояния:
    - waiting_for_name            — ожидание ввода имени клиента
    - waiting_for_identification  — способ идентификации (карточка/ИНН/контакт)
    - waiting_for_card            — загрузка карточки предприятия
    - waiting_for_inn             — ввод ИНН (10-12 цифр)
    - waiting_for_contact         — ввод телефона или e-mail

Дополнительно:
    • Легко расширяется новыми статусами (при необходимости)
    • Соответствует стандарту FSM aiogram
-----------------------------------------------------
"""

from aiogram.dispatcher.filters.state import StatesGroup, State

class Registration(StatesGroup):
    """
    Состояния FSM для регистрации клиента:
    1. waiting_for_name        — ввод имени
    2. waiting_for_identification — выбор карточки/ИНН/контакта
    3. waiting_for_card        — загрузка карточки предприятия
    4. waiting_for_inn         — ввод ИНН
    5. waiting_for_contact     — ввод телефона или e-mail
    """
    waiting_for_name = State()
    waiting_for_identification = State()
    waiting_for_card = State()
    waiting_for_inn = State()
    waiting_for_contact = State()