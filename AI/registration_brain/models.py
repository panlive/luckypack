"""
RegistrationBrain — модели данных.

Этот модуль описывает структуры, которые используются на границе
между Telegram-ботом и GPT-агентом регистрации.

Задача:
- Чётко описать, что такое "состояние регистрации" (stage + slots + краткая история).
- Чётко описать, что возвращает агент (текст ответа, новое состояние, действие).

Важно:
- Никакой бизнес-логики здесь нет, только данные.
- Используем dataclasses из стандартной библиотеки, чтобы не тянуть лишние зависимости.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Возможные этапы регистрации.
# Мы не жёстко валидируем здесь, но фиксируем канонический набор значений.
REGISTRATION_STAGES = {
    "START",
    "WAIT_NAME",
    "WAIT_INN",
    "CONFIRM_COMPANY",
    "MANAGER_HANDOFF",
    "DONE",
}


# Возможные действия, которые может запросить агент.
REGISTRATION_ACTIONS = {
    "NONE",               # Ничего не делать, просто ответить клиенту.
    "CHECK_INN",          # Проверить ИНН через DaData.
    "ASK_MANAGER_CONTACT",# Попросить контакт для передачи менеджеру.
    "SEND_TO_MANAGER",    # Отправить собранные данные менеджеру.
    "SHOW_MENU",          # Показать основное меню после завершения.
}


@dataclass
class RegistrationState:
    """
    Текущее состояние регистрации для конкретного пользователя.

    stage:
        Текущий этап регистрации (см. REGISTRATION_STAGES).
    slots:
        Собранные данные:
        - name
        - inn
        - phone
        - email
        - company_profile
        и любые дополнительные поля.
    history_short:
        Краткая история последних реплик.
        Формат элемента:
        {
            "role": "user" | "assistant" | "system",
            "text": "..."
        }
        Длинную историю здесь не держим, только 2–3 последних шага.
    memory_summary:
        Краткое текстовое резюме о клиенте, которое можно обновлять
        в ключевые моменты (наш лёгкий слой саморизации).
    """

    stage: str = "START"
    slots: Dict[str, Any] = field(default_factory=dict)
    history_short: List[Dict[str, str]] = field(default_factory=list)
    memory_summary: Optional[str] = None


@dataclass
class BrainOutput:
    """
    Ответ RegistrationBrain.

    reply_text:
        Текст, который нужно отправить клиенту в Telegram.
    new_stage:
        Новый этап регистрации (может совпадать со старым).
    updated_slots:
        Словарь изменений в слотах.
        Пример: {"inn": "7707083893"} или {"phone": "+7..."}.
        Эти данные должны быть аккуратно смёржены с существующими slots.
    action:
        Какое действие должен выполнить Python-код:
        - "NONE"
        - "CHECK_INN"
        - "ASK_MANAGER_CONTACT"
        - "SEND_TO_MANAGER"
        - "SHOW_MENU"
    should_summarize:
        Флаг, что по результатам этого шага имеет смысл обновить memory_summary.
    summary_hint:
        Короткая текстовая подсказка для саморизации:
        "Клиент дал ИНН и подтвердил компанию, предпочитает общение по чату."
    comment:
        Произвольный комментарий агента для логов/отладки.
        Клиенту НЕ показываем.
    """

    reply_text: str
    new_stage: str
    updated_slots: Dict[str, Any] = field(default_factory=dict)
    action: str = "NONE"
    should_summarize: bool = False
    summary_hint: Optional[str] = None
    comment: Optional[str] = None
