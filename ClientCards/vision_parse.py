#!/usr/bin/env python3
from __future__ import annotations
"""
vision_parse.py — сервис визуального разбора (отдельный контейнер).
• Принимает изображения/документы, распознаёт, нормализует, логирует.
• Конфигурация через .env/docker-compose; результаты в data/.
Не изменять без необходимости: используется сервисом luckypack_vision.
"""
# -*- coding: utf-8 -*-
"""
vision_parse.py — вотчер карточек (PNG/JPG/JPEG) для LuckyPackBot.

Фокус:
  • Извлекаем ТОЛЬКО 4 поля: company_name, inn, phone, email.
  • ИНН — приоритет: OCR (Tesseract) → затем Vision, при расходе берём OCR.
  • Телефон нормализуем к +7XXXXXXXXXX (если это российский номер).
  • E-mail валидируем; если невалиден — null.
  • Имя файла результата = <ИНН>.json; при дубле → (1), (2), …
  • Если ИНН не найден — исходник не удаляем, создаём …__error_no_inn.json.

Запуск:
  docker-compose run --rm luckypack_universal python3 -u AI/vision_parse.py --once
"""


import os
import time
import json
import base64
import hashlib
import logging
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List

from openai import OpenAI

# ========= ENV/paths/logs =========

LOGS_DIR = Path(os.getenv("LOGS_DIR", "/app/logs"))
VISION_TEMP = Path(os.getenv("VISION_TEMP_DIR", "/app/data/cards/vision_temp"))
PARSE_RESULTS = Path(os.getenv("PARSE_RESULTS_DIR", "/app/data/cards/parse_results"))

LOGS_DIR.mkdir(parents=True, exist_ok=True)
VISION_TEMP.mkdir(parents=True, exist_ok=True)
PARSE_RESULTS.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOGS_DIR / "vision.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("vision")

API_KEY = os.getenv("OPENAI_API_KEY", "")
if not API_KEY:
    log.error("OPENAI_API_KEY is empty — exiting")
    raise SystemExit(1)

MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=API_KEY)

SUPPORTED_EXTS: Dict[str, str] = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
REQUIRED_KEYS = ["company_name", "inn", "phone", "email"]

SYSTEM_PROMPT = (
    "Ты — парсер бизнес-карточек. "
    "Извлекай с максимальной точностью: "
    "1) inn — ИНН (10 или 12 цифр, только цифры), "
    "2) company_name — название компании/ФИО, "
    "3) phone — телефон (международный или РФ-формат), "
    "4) email — адрес электронной почты. "
    "Если поле отсутствует — укажи null. "
    "Верни строго JSON с ключами company_name, inn, phone, email."
)

# ========= helpers =========

def only_digits(s: Any) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())

def valid_inn(d: str) -> bool:
    return d.isdigit() and len(d) in (10, 12)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def validate_email(val: Optional[str]) -> Optional[str]:
    if not val or not isinstance(val, str):
        return None
    v = val.strip()
    return v if EMAIL_RE.match(v) else None

def normalize_phone_ru(val: Optional[str]) -> Optional[str]:
    """
    Приводит российские номера к E.164: +7XXXXXXXXXX.
    Правила:
      +7XXXXXXXXXX       → ок
      8XXXXXXXXXX (11)   → +7XXXXXXXXXX
      7XXXXXXXXXX (11)   → +7XXXXXXXXXX
      XXXXXXXXXX (10)    → +7XXXXXXXXXX
    Иначе: чистим от мусора, если остаётся <6 цифр — null, иначе возвращаем как есть (без форматирования).
    """
    if not val or not isinstance(val, str):
        return None
    digits = only_digits(val)
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if digits.startswith("7") and len(digits) == 12 and val.strip().startswith("+"):
        # уже +7XXXXXXXXXX
        return "+" + digits
    # fallback: если это что-то иное; отбрасываем совсем короткое
    return None if len(digits) < 6 else val.strip()

def sha256_of_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def file_to_b64_and_mime(path: Path) -> Tuple[str, str]:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported extension: {ext}")
    return base64.b64encode(path.read_bytes()).decode("ascii"), SUPPORTED_EXTS[ext]

def guess_nnn_from_name(p: Path) -> Optional[str]:
    stem = p.stem
    digits = "".join(ch for ch in stem if ch.isdigit())
    if digits and stem.startswith(digits) and len(digits) >= 3:
        return digits
    return None

def ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")

def next_available_filename(base_name: str) -> Path:
    cand = PARSE_RESULTS / f"{base_name}.json"
    i = 1
    while cand.exists():
        cand = PARSE_RESULTS / f"{base_name} ({i}).json"
        i += 1
    return cand

# ========= OCR first (ИНН) =========

def ocr_extract_inn(image_path: Path) -> Optional[str]:
    """Достаём ИНН из картинки через Tesseract (rus+eng)."""
    try:
        txt = subprocess.check_output(
            ["tesseract", str(image_path), "stdout", "-l", "rus+eng"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="ignore")
        matches = re.findall(r"\b\d{10}\b|\b\d{12}\b", txt)
        return matches[0] if matches else None
    except Exception as e:
        log.warning(f"OCR failed for {image_path}: {e}")
        return None

# ========= Vision + tiny-retry =========

def call_vision_once(img_b64: str, mime: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Извлеки ИНН, название компании/ФИО, телефон и email."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ],
            },
        ],
        temperature=0,
    )
    return (resp.choices[0].message.content or "").strip()

def call_vision_with_retry(img_b64: str, mime: str, attempts: int = 2, pause_sec: float = 0.6) -> Dict[str, Any]:
    """
    Tiny-retry: до 2 попыток, если:
      • исключение API,
      • пустой ответ,
      • невалидный JSON.
    """
    last_err = None
    for i in range(1, attempts + 1):
        try:
            raw = call_vision_once(img_b64, mime)
            if not raw:
                raise RuntimeError("empty response")
            try:
                return json.loads(raw)
            except Exception as e_json:
                last_err = e_json
                log.warning(f"Vision returned non-JSON (try {i}): {e_json}; raw_head={raw[:200]!r}")
        except Exception as e:
            last_err = e
            log.warning(f"Vision API error (try {i}): {e}")
        if i < attempts:
            time.sleep(pause_sec)
    log.error(f"Vision failed after {attempts} tries: {last_err}")
    return {}

def ensure_min_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in REQUIRED_KEYS:
        v = d.get(k) if isinstance(d, dict) else None
        if isinstance(v, str) and not v.strip():
            v = None
        out[k] = v
    return out

# ========= core parse =========

def parse_image(path: Path) -> Dict[str, Any]:
    """
    Алгоритм:
      1) OCR → ИНН (источник правды №1).
      2) Vision (tiny-retry) → 4 поля.
      3) Если Vision-ИНН невалиден/отличается — подменяем на OCR.
      4) Нормализуем phone, валидируем email.
      5) Собираем минимальный JSON + source_*.
    """
    # OCR первым
    ocr_inn = ocr_extract_inn(path)
    if ocr_inn and valid_inn(ocr_inn):
        log.info(f"[OCR inn] {path.name}: {ocr_inn}")
    else:
        log.info(f"[OCR inn] {path.name}: not found")

    # Vision с tiny-retry
    img_b64, mime = file_to_b64_and_mime(path)
    vdata_raw = call_vision_with_retry(img_b64, mime)
    data = ensure_min_schema(vdata_raw)

    log.info(
        f"[Vision] {path.name}: "
        f"company_name={repr(data.get('company_name'))}, "
        f"inn={repr(data.get('inn'))}, phone={repr(data.get('phone'))}, "
        f"email={repr(data.get('email'))}"
    )

    # Коррекция ИНН по OCR
    v_inn_digits = only_digits(data.get("inn") or "")
    if ocr_inn and valid_inn(ocr_inn):
        if not valid_inn(v_inn_digits):
            data["inn"] = ocr_inn
            log.info(f"[INN use OCR] {path.name}: insert {ocr_inn}")
        elif v_inn_digits != ocr_inn:
            log.info(f"[INN override OCR] {path.name}: {v_inn_digits} -> {ocr_inn}")
            data["inn"] = ocr_inn

    # Нормализация телефона и валидация e-mail
    data["phone"] = normalize_phone_ru(data.get("phone"))
    data["email"] = validate_email(data.get("email"))

    # Итоговый минимум + источник
    stat = path.stat()
    mtime_utc = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    result = {
        "company_name": data.get("company_name"),
        "inn": data.get("inn"),
        "phone": data.get("phone"),
        "email": data.get("email"),
        "source_filename": path.name,
        "source_filetime_utc": mtime_utc,
    }
    return result

# ========= errors =========

def write_error_notify(fallback: str, src_path: Path) -> Path:
    """Пишем уведомление для бота и НЕ удаляем исходник."""
    basename = f"{fallback}__error_no_inn"
    out_path = next_available_filename(basename)
    payload = {
        "_error": "no_inn",
        "_msg_ru": (
            "Не удалось распознать ИНН в карточке. "
            "Отправьте документ в другом формате или лучшего качества, "
            "либо введите ИНН вручную в поле диалога."
        ),
        "source_filename": src_path.name,
        "source_filetime_utc": datetime.fromtimestamp(src_path.stat().st_mtime, tz=timezone.utc).isoformat(),
    }
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    return out_path

# ========= loop =========

def process_one(path: Path) -> bool:
    try:
        if path.suffix.lower() not in SUPPORTED_EXTS:
            log.info(f"Skip (unsupported ext): {path.name}")
            return True

        log.info(f"Processing: {path.name} (size={path.stat().st_size})")
        fallback = guess_nnn_from_name(path) or ts()

        data = parse_image(path)

        inn_digits = only_digits(data.get("inn") or "")
        if not valid_inn(inn_digits):
            notify_path = write_error_notify(fallback, path)
            log.error(f"[no_inn] {path.name} -> {notify_path.name}")
            return False

        out_path = next_available_filename(inn_digits)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out_path)
        path.unlink(missing_ok=True)
        log.info(f"Saved: {out_path.name}; removed: {path.name}")
        return True

    except Exception as e:
        log.exception(f"Failed {path}: {e}")
        return False

def list_inputs() -> List[Path]:
    files: List[Path] = []
    for ext in SUPPORTED_EXTS.keys():
        files.extend(VISION_TEMP.glob(f"*{ext}"))
    files.sort(key=lambda p: p.stat().st_mtime)
    return files

def main_loop(once: bool = False, to_console: bool = False) -> None:
    log.info(f"Watcher started. Model={MODEL} TEMP={VISION_TEMP} OUT={PARSE_RESULTS} LOGS={LOGS_DIR}")

    if to_console:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        log.addHandler(console)

    while True:
        files = list_inputs()
        if not files:
            if once:
                log.info("Once mode: nothing to do, exit.")
                return
            time.sleep(2)
            continue
        for f in files:
            process_one(f)
        if once:
            return

# ========= entry =========

if __name__ == "__main__":
    import sys
    once = ("--once" in sys.argv) or ("--debug" in sys.argv)
    to_console = ("--once" in sys.argv) or ("--debug" in sys.argv)
    if "--debug" in sys.argv:
        log.setLevel(logging.DEBUG)
    main_loop(once=once, to_console=to_console)
