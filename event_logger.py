"""
event_logger.py
---------------

Назначение:
    • Журналирует ключевые события взаимодействия клиентов с ботом.
    • Все события сохраняются в файл logs/clients.log (НЕ clients.json!).
    • Используется для контроля, аудита, аналитики, просмотра истории через админку.

Формат:
    Каждая строка — одно событие:
        [YYYY-MM-DD HH:MM:SS] 👤 ID: {telegram_id} | name: {имя или —} | event: {описание события}

Особенности:
    - Если имя ещё неизвестно — подставляется «—»
    - Папка logs создаётся автоматически, если не существует
    - Поддерживает кириллицу, UTF-8
    - Ошибки логирования не влияют на основной поток работы бота (fail-safe)
"""

import os
from datetime import datetime

LOG_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "clients.log")


def log_event(user_id: int, name: str, event: str) -> None:
    """
    Записывает событие в clients.log. Безопасно: ошибки подавляются.

    :param user_id: Telegram ID пользователя
    :param name: Имя пользователя или None/пустая строка
    :param event: Текстовое описание события
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    display_name = name.strip() if name and name.strip() else "—"
    log_line = f"[{timestamp}] 👤 ID: {user_id} | name: {display_name} | event: {event}\n"

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(log_line)
    except Exception:
        # Fail-safe: при любых ошибках не останавливаем работу бота
        pass