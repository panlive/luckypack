#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision_entry.py — точка входа для luckypack_vision без правки legacy-кода.

НАЗНАЧЕНИЕ
- Задать пути из ENV (VISION_TEMP / VISION_RESULTS / VISION_LOG)
- Создать каталоги, включить тихий лог
- Передать совместимые переменные окружения (TEMP / OUT / LOGS)
- Запустить исходный ClientCards/vision_parse.py через runpy.run_path

Почему так:
- Не трогаем ваш vision_parse.py.
- Если он читает ENV или переменные TEMP/OUT/LOGS — всё заработает без редактирования.
- Если внутри много своих print/logging — мы глушим болтовню, оставляя файл-лог только для INFO/ERROR.
"""

import os
import sys
import pathlib
import logging
import runpy

# 1) Пути из окружения с дефолтами внутри контейнера
TEMP = os.getenv('VISION_TEMP', '/app/data/cards/tmp')
RESULTS = os.getenv('VISION_RESULTS', '/app/data/cards/parse_results')
LOGFILE = os.getenv('VISION_LOG', '/app/logs/vision.log')

# 2) Гарантируем каталоги
pathlib.Path(TEMP).mkdir(parents=True, exist_ok=True)
pathlib.Path(RESULTS).mkdir(parents=True, exist_ok=True)
pathlib.Path(os.path.dirname(LOGFILE) or '.').mkdir(parents=True, exist_ok=True)

# 3) Совместимость для legacy-кода, который смотрит в os.environ
os.environ['TEMP'] = TEMP
os.environ['OUT'] = RESULTS
os.environ['LOGS'] = os.path.dirname(LOGFILE)

# 4) Тихий лог: корневой логгер приглушаем, отдельный файл-логгер 'vision'
root = logging.getLogger()
for h in list(root.handlers):
    root.removeHandler(h)
root.setLevel(logging.WARNING)

vision = logging.getLogger('vision')
for h in list(vision.handlers):
    vision.removeHandler(h)
vision.setLevel(logging.INFO)  # пишем INFO и ERROR
fh = logging.FileHandler(LOGFILE, encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
fh.setLevel(logging.INFO)
vision.addHandler(fh)

vision.info(f"Entry started. TEMP={TEMP} OUT={RESULTS} LOGS={os.path.dirname(LOGFILE)}")

# 5) Запускаем исходный файл как __main__
SCRIPT = '/app/ClientCards/vision_parse.py'
if not os.path.isfile(SCRIPT):
    vision.error(f'File not found: {SCRIPT}')
    sys.exit(2)

try:
    runpy.run_path(SCRIPT, run_name='__main__')
except SystemExit:
    raise
except Exception as e:
    vision.error(f'vision_parse.py crashed: {e}', exc_info=True)
    sys.exit(1)
