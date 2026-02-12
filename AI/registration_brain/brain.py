"""
RegistrationBrain — "мозг" регистрации.

Режим JSON (боевой):
- системный промпт требует строго один JSON-объект;
- мы парсим JSON и возвращаем BrainOutput;
- при любой ошибке (нет ключа, ошибка OpenAI, битый JSON) — безопасный fallback,
  чтобы бот не падал и не рестартился.
"""

import os
import json
import re
import traceback
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI  # новый клиент

from .models import RegistrationState, BrainOutput

# --- Загрузка конфигурации и инициализация клиента OpenAI ---
load_dotenv()
_api_key = os.getenv("OPENAI_API_KEY")

if _api_key:
    client: Optional[OpenAI] = OpenAI(api_key=_api_key)
else:
    client = None


def _load_system_prompt() -> str:
    """
    Загружаем системный промпт из prompts/system_ru.md.

    ВАЖНО: Никаких "режимов отладки" тут не добавляем.
    Контракт задаётся промптом, и модель должна возвращать JSON.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(base_dir, "prompts", "system_ru.md")

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        # Фолбек на случай отсутствия файла (не должен происходить в проде)
        return (
            "Ты — RegistrationBrain, мозг регистрации в сервисе LuckyPack.\n"
            "Всегда возвращай один JSON-объект по контракту:\n"
            '{"reply_text":"...","new_stage":"START","updated_slots":{},"action":"NONE"}'
        )


def _build_messages(state: RegistrationState, user_message: str) -> List[Dict[str, Any]]:
    """
    Формируем messages для ChatCompletion.

    Упаковываем текущее состояние в JSON, чтобы модель понимала контекст.
    """
    system_prompt = _load_system_prompt()

    payload = {
        "stage": state.stage,
        "slots": state.slots,
        "history_short": state.history_short,
        "memory_summary": state.memory_summary,
        "user_message": user_message,
    }

    user_content = (
        "Вот текущее состояние регистрации и новое сообщение клиента "
        "в формате JSON:\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "Ответь СТРОГО одним JSON-объектом по контракту из system prompt. "
        "Никакого текста вне JSON."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _call_gpt(messages: List[Dict[str, Any]]) -> Optional[str]:
    """
    Вызов OpenAI через новый клиент.
    """
    if client is None:
        print("[RegistrationBrain] OPENAI_API_KEY не найден, используем заглушку.")
        return None

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[RegistrationBrain] Ошибка обращения к OpenAI: {e}")
        print(traceback.format_exc())
        return None


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Пытаемся вытащить JSON-объект из ответа модели.

    Допускаем, что модель может завернуть JSON в ```json ... ```
    или добавить лишний текст. Мы это режем.
    """
    if not text:
        return None

    # Убираем code fences, если есть
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Сначала пробуем как есть
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Если не получилось — вырезаем самый вероятный объект { ... }
    try:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = cleaned[start : end + 1]
            obj = json.loads(snippet)
            if isinstance(obj, dict):
                return obj
    except Exception:
        return None

    return None


def build_debug_reply(state: RegistrationState, user_message: str) -> str:
    """
    Режим заглушки (без GPT или при ошибке).
    """
    lines = [
        "🧠 RegistrationBrain временно работает в режиме заглушки.",
        "",
        "Ваше сообщение:",
        f"«{user_message}»",
        "",
        f"Текущий этап регистрации: {state.stage}",
        "",
        "Попробуйте повторить сообщение позже или свяжитесь с менеджером.",
    ]
    return "\n".join(lines)


def run_registration_brain(state: RegistrationState, user_message: str) -> BrainOutput:
    """
    Точка входа в агент регистрации.

    Возвращаем BrainOutput, заполненный из JSON модели.
    При любой ошибке — безопасный fallback.
    """
    messages = _build_messages(state, user_message)
    raw = _call_gpt(messages)

    if raw is None:
        return BrainOutput(
            reply_text=build_debug_reply(state, user_message),
            new_stage=state.stage,
            updated_slots={},
            action="NONE",
            should_summarize=False,
            summary_hint=None,
            comment="Stub reply (no OpenAI API key or error during call).",
        )

    obj = _extract_json_object(raw)
    if obj is None:
        return BrainOutput(
            reply_text=(
                "Я вас понял. Давайте сделаем так: напишите, пожалуйста, "
                "ваш ИНН (10–12 цифр) или контакт (телефон/e-mail) для менеджера."
            ),
            new_stage=state.stage,
            updated_slots={},
            action="NONE",
            should_summarize=False,
            summary_hint=None,
            comment="GPT returned non-JSON or unparseable JSON.",
        )

    # Валидация ключей контракта (минимальная, чтобы не падать)
    reply_text = obj.get("reply_text")
    new_stage = obj.get("new_stage", state.stage)
    updated_slots = obj.get("updated_slots", {}) or {}
    action = obj.get("action", "NONE")

    if not isinstance(reply_text, str) or not reply_text.strip():
        reply_text = "Пожалуйста, уточните ваш запрос: имя, ИНН или контакт для менеджера."
    if not isinstance(new_stage, str) or not new_stage:
        new_stage = state.stage
    if not isinstance(updated_slots, dict):
        updated_slots = {}
    if not isinstance(action, str) or not action:
        action = "NONE"

    return BrainOutput(
        reply_text=reply_text.strip(),
        new_stage=new_stage,
        updated_slots=updated_slots,
        action=action,
        should_summarize=False,
        summary_hint=None,
        comment="GPT reply (JSON mode).",
    )
