#!/usr/bin/env python3
import os, re, time, sys
from datetime import datetime, timedelta

# === Самодостаточный запуск ===
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
except Exception:
    pass
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from admin_notify import notify_admin
from config import LOGS_DIR, PHOTO_DOWNLOAD_PATH

# МСК
try:
    os.environ['TZ'] = 'Europe/Moscow'
    time.tzset()
except Exception:
    pass

PHOTOS_LOG = os.path.join(LOGS_DIR, "photos.log")
PRICES_LOG = os.path.join(LOGS_DIR, "prices.log")  # исправлено: не передаём абсолют в join
CLIENTS_LOG = os.path.join(LOGS_DIR, "clients.log")

EAN = re.compile(r'^\d{13}\.(jpg|jpeg|png)$', re.IGNORECASE)
TS_LINE = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})]')

NOW = datetime.now()
AGO = NOW - timedelta(days=1)

def read_tail(path, max_bytes=400000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes), os.SEEK_SET)
            return f.read().decode("utf-8", "ignore")
    except Exception:
        return ""

def recent_lines(path):
    txt = read_tail(path)
    for line in txt.splitlines():
        m = TS_LINE.match(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts >= AGO:
            yield ts, line

def detect_photos_dir():
    # Надёжный выбор каталога с фото: первый из кандидатов, где больше всего валидных файлов.
    candidates = [
        PHOTO_DOWNLOAD_PATH or "",
        "/app/data/photos/original",
        "/srv/luckypack/project/data/photos/original",
        "/app/data/photos/original",
    ]
    best = ""
    best_cnt = -1
    for d in candidates:
        if not d or not os.path.isdir(d):
            continue
        try:
            cnt = sum(1 for n in os.listdir(d) if EAN.match(n))
        except Exception:
            cnt = -1
        if cnt > best_cnt:
            best_cnt, best = cnt, d
    return best, max(best_cnt, 0)

def block_prices():
    import glob
    # кандидаты путей к логам и каталогам прайсов (хост)
    log_candidates = [
        "/srv/luckypack/logs/prices.log",
        "/srv/luckypack/logs/prices.log",
    ]
    dir_candidates = [
        "/app/data/Prices",
        "/app/data/prices",
        "/srv/luckypack/project/data/Prices",
        "/srv/luckypack/project/data/prices",
    ]

    # 1) сначала пытаемся вытащить число из лога по фразе "успешно: N/N"
    count = None
    for lp in log_candidates:
        if os.path.exists(lp):
            try:
                with open(lp,'r',encoding='utf-8') as f:
                    for line in reversed(f.readlines()):
                        m = re.search(r"успешно:\s*(\d+)\s*/", line)
                        if m:
                            count = int(m.group(1)); break
            except Exception:
                pass
        if count is not None:
            break

    # 2) если в логе не нашли — считаем XLS/XLSX в каталоге прайсов
    if count is None:
        total = 0
        for d in dir_candidates:
            if os.path.isdir(d):
                total += len(glob.glob(os.path.join(d, "**", "*.xls"), recursive=True))
                total += len(glob.glob(os.path.join(d, "**", "*.xlsx"), recursive=True))
        if total > 0:
            count = total

    if count is not None:
        return f"• <b>Прайсы</b>: обновлены, количество {count}"
    return "• <b>Прайсы</b>: данных нет"

def last_new_downloaded():
    """Последнее значение 'New files downloaded: N' за сутки (а не сумма)."""
    pat = re.compile(r'New files downloaded:\s*(\d+)', re.I)
    last = 0
    for _, ln in recent_lines(PHOTOS_LOG):
        m = pat.search(ln)
        if m:
            last = int(m.group(1))
    return last

def block_photos():
    _photos_dir, current_total = detect_photos_dir()  # X (все валидные сейчас в original)
    Y = last_new_downloaded()                         # последние скачанные за сутки
    return f"• <b>Фото</b>: новых {Y} / всего {current_total}"

def block_index():
    """
    Индекс фото по фактическому img_ids.npy.
    • всего  = len(img_ids.npy)
    • новых  = max(всего - было, 0)
    • было   = значение прошлого запуска (держим одно число в /app/data/state/)
    """
    try:
        import numpy as np
        ids_path = "/srv/luckypack/project/SearchByPhoto/index/img_ids.npy"
        if not os.path.exists(ids_path):
            return "• <b>Индекс фото</b>: данных нет"
        total = int(len(np.load(ids_path, allow_pickle=True)))
    except Exception:
        return "• <b>Индекс фото</b>: данных нет"

    state_path = "/app/data/state/img_index.count"
    prev = total
    try:
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                prev = int(f.read().strip() or total)
    except Exception:
        prev = total
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            f.write(str(total))
    except Exception:
        pass

    new = total - prev
    if new < 0:
        new = 0  # на случай чисток/регрессий

    return f"• <b>Индекс фото</b>: новых {new} / всего {total} / было {prev}"

def block_clients():
    if not os.path.exists(CLIENTS_LOG):
        return "• <b>Карточки</b>: данных нет"
    cnt = 0
    pat = re.compile(r'\bNEW_CLIENT\b', re.I)
    for _, ln in recent_lines(CLIENTS_LOG):
        if pat.search(ln):
            cnt += 1
    if cnt == 0:
        return "• <b>Карточки</b>: данных нет"
    return f"• <b>Карточки</b>: новые клиенты за сутки — {cnt}"

def main():
    msg = "\n".join([block_prices(), block_photos(), block_index(), block_clients()])
    notify_admin("\n" + msg, module="daily_report")
    print(msg)

if __name__ == "__main__":
    main()
