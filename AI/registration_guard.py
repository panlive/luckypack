#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from typing import Dict, Any, Optional, List

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """Ты — Registration Guard (консьерж регистрации) для LuckyPack.

Цель:
— отвечать по-человечески, спокойно и кратко;
— мягко удерживать пользователя в регистрации;
— обрабатывать любые отклонения (шутки, злость, вопросы “зачем ИНН”, просьбы прайсов);
— НЕ ломать строгий сценарий FSM.

ЖЁСТКИЕ ПРАВИЛА (никогда не нарушай):
1) До завершения регистрации НЕ обсуждай товары, цены, наличие, ассортимент, доставку, прайсы.
2) Для “знакомства” нужен ТОЛЬКО ИНН организации/ИП (10–12 цифр). Никаких других данных.
3) Не придумывай факты о пользователе и компании.
4) Если пользователь отказывается давать ИНН — спокойно предложи продолжить через менеджера.
5) Если вопросы про персональные данные / “зачем ИНН”:
   — коротко объясни: ИНН нужен только чтобы идентифицировать организацию и открыть доступ.
   — выставь need_policy_link=true.
6) Ты не пишешь файлы, не вызываешь сторонние API, не меняешь состояние напрямую.
7) Всегда возвращай СТРОГИЙ JSON по контракту. Никакого текста вне JSON.

КОНТЕКСТ:
Тебе могут передать поле history (краткая история диалога). Используй его, чтобы:
— не повторять дословно последнюю реплику бота;
— отвечать естественнее (“Вы выше писали…”), но без болтовни.

СТАДИИ (stage):
— WAIT_NAME: ждём имя/обращение.
— WAIT_INN: ждём ИНН (10–12 цифр).
— CONFIRM_COMPANY: ждём подтверждение “да/нет”.
— DONE: регистрация завершена.

ТОН:
— спокойный, уважительный, без канцелярита;
— 2–4 предложения максимум;
— без спама эмодзи (не более 1).

КОНТРАКТ ВЫХОДА (JSON):
{
  "reply": "строка",
  "extracted": {"name": "строка|пусто", "inn": "строка|пусто"},
  "next_stage": "WAIT_NAME|WAIT_INN|CONFIRM_COMPANY|DONE|\"\"",
  "show_menu": false,
  "need_policy_link": false
}

Важно:
— Если ты не уверен, next_stage оставь пустой строкой.
— extracted.name/inn оставляй пустыми строками, если не извлёк.
— Возвращай ТОЛЬКО JSON.
"""


def _format_history(history: Optional[List[Dict[str, str]]]) -> str:
    if not history:
        return ""
    lines: List[str] = []
    for h in history[-6:]:
        role = "Клиент" if h.get("role") == "user" else "Бот"
        t = (h.get("text") or "").strip()
        if t:
            lines.append(f"{role}: {t}")
    return "\n".join(lines)


def _normalize_output(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        obj = {}

    extracted = obj.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}

    out = {
        "reply": obj.get("reply") if isinstance(obj.get("reply"), str) else "",
        "extracted": {
            "name": extracted.get("name") if isinstance(extracted.get("name"), str) else "",
            "inn": extracted.get("inn") if isinstance(extracted.get("inn"), str) else "",
        },
        "next_stage": obj.get("next_stage") if isinstance(obj.get("next_stage"), str) else "",
        "show_menu": bool(obj.get("show_menu")) if isinstance(obj.get("show_menu"), (bool, int)) else False,
        "need_policy_link": bool(obj.get("need_policy_link")) if isinstance(obj.get("need_policy_link"), (bool, int)) else False,
    }
    return out


def _extract_json_text(s: str) -> str:
    """
    На случай если модель (или SDK) вернёт лишний текст —
    вырезаем первый JSON-объект по границам { ... }.
    """
    if not s:
        return ""
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    a = s.find("{")
    b = s.rfind("}")
    if a != -1 and b != -1 and b > a:
        return s[a:b + 1]
    return ""


def _call_via_responses(messages):
    """
    Пытаемся через Responses API (без response_format, т.к. в вашем SDK оно падает).
    """
    resp = client.responses.create(
        model="gpt-4.1-mini",
        messages=messages,
    )
    raw = getattr(resp, "output_text", None)
    return raw if isinstance(raw, str) else ""


def _call_via_chat_completions(messages):
    """
    Фолбэк на ChatCompletions (обычно есть даже в старых SDK).
    """
    # преобразуем messages как есть (system/user)
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return content if isinstance(content, str) else ""


def guard(stage: str, user_text: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    payload = {
        "stage": stage,
        "text": user_text,
        "history": _format_history(history),
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    raw = ""
    try:
        raw = _call_via_responses(messages)
    except TypeError:
        raw = ""

    # Если Responses API вернуло пусто/мусор — идём в ChatCompletions
    if not raw.strip():
        raw = _call_via_chat_completions(messages)

    raw = _extract_json_text(raw)

    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {}

    return _normalize_output(data)