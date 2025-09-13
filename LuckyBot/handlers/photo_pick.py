#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
photo_pick.py — обработка входящих фото от клиента.
• Сохраняем фото во временный файл /tmp (в контейнере).
• Запускаем готовый подбор по фото (из AI/demos/send_pick_demo.py) на n=5.
• По завершении — удаляем временный файл.
• Никаких сохранений в data/PhotoPicks/_in.
"""
import asyncio, os, tempfile
from pathlib import Path
from aiogram import types
from aiogram.types import ContentType

# где лежит скрипт подбора (уже существует)
SEND_PICK_DEMO = Path("/app/AI/demos/send_pick_demo.py")

def register(dp):
    @dp.message_handler(content_types=[ContentType.PHOTO])
    async def on_photo(m: types.Message):
        # 1) берём лучшую (самую большую) версию фото
        photo = m.photo[-1]
        await m.reply("Запускаю подбор по фото…")

        # 2) сохраняем во временный файл внутри контейнера
        tmpdir = tempfile.mkdtemp(prefix="pick_", dir="/tmp")
        tmp_path = Path(tmpdir) / "query.jpg"
        await photo.download(destination_file=str(tmp_path))

        try:
            # 3) запускаем уже готовый скрипт подбора (он сам отправит альбом и Excel)
            #    Важно: он использует TELEGRAM_BOT_TOKEN / SUPERADMIN_ID из .env
            #    чтобы отправить результат в чат (в тот же chat_id).
            #    Передаём --query и --n 5.
            proc = await asyncio.create_subprocess_exec(
                "python3", str(SEND_PICK_DEMO),
                "--query", str(tmp_path),
                "--n", "5",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            out, err = await proc.communicate()
            code = proc.returncode

            if code == 0:
                # скрипт сам шлёт результаты (альбом + XLSX). Здесь — короткое финальное подтверждение.
                await m.reply("Готово. Я отправил вам Excel с подбором и миниатюрами.")
            else:
                # если что-то пошло не так — показываем ошибку кратко
                text = (err.decode("utf-8", "ignore") or out.decode("utf-8", "ignore"))[:800]
                await m.reply("Не удалось сформировать подбор по фото. Сообщение для техподдержки:\n" + text)
        finally:
            # 4) подчистка временных файлов — НИЧЕГО не остаётся в data/PhotoPicks/_in
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
                Path(tmpdir).rmdir()
            except Exception:
                pass