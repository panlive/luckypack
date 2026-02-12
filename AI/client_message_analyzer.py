#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client_message_analyzer.py — упрощённый анализатор сообщений клиента.

ВАЖНО:
- Это НЕ старая GPT-версия.
- Это лёгкая заглушка на регулярках и простых правилах.
- Её задача — не уронить бота, пока мы переносим логику в RegistrationBrain.

Функция analyze_client_message(text: str) возвращает словарь:

{
    "status": "valid_inn" | "company_info" | "ask_later" |
              "card_decline" | "decline_all" | "none",
    "inn": str | None,
    "phone": str | None,
    "email": str | None,
    "extra_comment": str | None,
}
"""

import re
from typing import Dict, Optional


def _extract_inn(text: str) -> Optional[str]:
    """
    Ищем подряд идущие цифры длиной 10 или 12.
    Берём первый подходящий блок.
    """
    for match in re.finditer(r"\d{10,12}", text):
        inn = match.group(0)
        if len(inn) in (10, 12):
            return inn
    return None


def _extract_phone(text: str) -> Optional[str]:
    """
    Примитивный поиск телефона:
    - хотя бы 10 цифр,
    - допускаем +, пробелы, тире, скобки.
    """
    # Убираем лишнее для анализа
    cleaned = re.sub(r"[^\d+]", " ", text)
    # Ищем что-то похожее на номер с 10+ цифрами
    candidates = cleaned.split()
    for c in candidates:
        digits = re.sub(r"\D", "", c)
        if len(digits) >= 10:
            return c.strip()
    return None


def _extract_email(text: str) -> Optional[str]:
    """
    Примитивный поиск e-mail.
    """
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if match:
        return match.group(0)
    return None


def analyze_client_message(text: str) -> Dict[str, Optional[str]]:
    """
    Упрощённый анализ сообщения клиента.

    Возвращает словарь:
    - status:
        - "valid_inn"   — найден ИНН (10 или 12 цифр).
        - "ask_later"   — клиент пишет "потом", "позже", "сейчас нет" и т.п.
        - "card_decline"— клиент не хочет давать ИНН, но не посылает нас насовсем.
        - "decline_all" — клиент явно посылает/отказывается от любых данных.
        - "none"        — ничего полезного не нашли.
    - остальные поля — inn/phone/email/extra_comment.
    """

    original = text or ""
    t = original.strip()
    lower = t.lower()

    result: Dict[str, Optional[str]] = {
        "status": "none",
        "inn": None,
        "phone": None,
        "email": None,
        "extra_comment": None,
    }

    # 1) Пробуем найти ИНН
    inn = _extract_inn(t)
    if inn:
        result["status"] = "valid_inn"
        result["inn"] = inn
        return result

    # 2) Пробуем найти телефон/e-mail
    phone = _extract_phone(t)
    email = _extract_email(t)
    if phone:
        result["phone"] = phone
    if email:
        result["email"] = email

    # 3) "Потом", "сейчас нет", "нет под рукой" и т.п.
    ask_later_markers = [
        "потом", "позже", "сейчас нет", "нет под рукой",
        "как будет", "как найду", "напомни", "напишите позже",
    ]
    if any(m in lower for m in ask_later_markers):
        result["status"] = "ask_later"
        result["extra_comment"] = original
        return result

    # 4) Явный отказ от ИНН, но ещё не полный посыл (card_decline)
    decline_inn_markers = [
        "не буду", "не хочу", "не дам инн", "инн не дам",
        "инн не хочу", "инн не отправлю",
    ]
    if any(m in lower for m in decline_inn_markers):
        # Если при этом есть телефон или почта — нам хватит для менеджера
        result["status"] = "card_decline"
        result["extra_comment"] = original
        return result

    # 5) Полный отказ/агрессия (decline_all)
    hard_decline_markers = [
        "отстань", "отвалите", "иди нах", "иди на х",
        "не пишет", "не пиши", "не связывайтесь", "уберите",
    ]
    if any(m in lower for m in hard_decline_markers):
        result["status"] = "decline_all"
        result["extra_comment"] = original
        return result

    # 6) Если ничего не поймали, но есть телефон/e-mail — пусть будет "card_decline"
    # Это мягко подталкивает старый сценарий к handoff менеджеру.
    if phone or email:
        result["status"] = "card_decline"
        result["extra_comment"] = original
        return result

    # 7) Ничего полезного
    return result
