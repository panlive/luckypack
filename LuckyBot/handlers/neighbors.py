#!/usr/bin/env python3
# neighbors.py — техническая проверка проводки хендлеров (aiogram v2).
from aiogram import types
from aiogram.dispatcher.filters import Command

def register(dp):
    @dp.message_handler(Command("neighbors"))
    async def neighbors_cmd(m: types.Message):
        parts = (m.text or "").split()
        if len(parts) < 2:
            await m.reply("Формат: /neighbors <EAN13>")
            return
        art = parts[1].strip()
        if not (art.isdigit() and len(art) == 13):
            await m.reply("Нужен 13-значный EAN13. Пример: /neighbors 4610027750756")
            return
        await m.reply(f"Ок, принял артикул {art}. (технический тест)")
