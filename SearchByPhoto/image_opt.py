#!/usr/bin/env python3
"""
image_opt.py — нормализация фотобазы.
• Берёт новые файлы из data/photos/original/, валидирует EAN, считает хеш.
• Делает ресайз (MAX_DIM, по умолчанию 1600), конвертирует в WebP (WEBP_QUALITY), создаёт thumbs/.
• Обновляет data/photos/photos_index.json. Идемпотентно (повторный запуск не трогает обработанные).
Логи: /srv/luckypack/logs/photos.log; пути настраиваются через .env.
"""
import os, json, hashlib, io, sys
from pathlib import Path
from datetime import datetime
from PIL import Image
import numpy as np
from skimage.color import rgb2lab

DATA_PHOTOS = Path("/app/data/photos")
D_ORIG = DATA_PHOTOS/"original"
D_VECT = DATA_PHOTOS/"vectorized"
D_THMB = DATA_PHOTOS/"thumbs"
INDEX  = DATA_PHOTOS/"photos_index.json"

MAX_DIM = int(os.getenv("MAX_DIM", "1600"))
WEBP_Q  = int(os.getenv("WEBP_QUALITY", "80"))
THUMB   = 512
SAVE_EVERY = 50  # автосейв индекса каждые N файлов

for d in (D_VECT, D_THMB, INDEX.parent):
    d.mkdir(parents=True, exist_ok=True)

def sha1_bytes(b: bytes)->str:
    h = hashlib.sha1(); h.update(b); return h.hexdigest()

def avg_lab(im: Image.Image):
    im = im.convert("RGB")
    arr = np.asarray(im, dtype=np.float32) / 255.0
    lab = rgb2lab(arr)
    L = float(np.mean(lab[...,0])); a = float(np.mean(lab[...,1])); b = float(np.mean(lab[...,2]))
    return [round(L,3), round(a,3), round(b,3)]

def read_index():
    if INDEX.exists():
        try: return json.load(open(INDEX, "r", encoding="utf-8"))
        except: return {}
    return {}

def save_index(idx):
    tmp = INDEX.with_suffix(".tmp.json")
    json.dump(idx, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    tmp.replace(INDEX)

def iter_photos():
    for p in sorted(D_ORIG.glob("**/*")):
        if p.is_file() and p.suffix.lower() in (".jpg",".jpeg",".png",".webp"):
            yield p

def main():
    files = list(iter_photos())
    total = len(files)
    if total == 0:
        print("Нет файлов в original/", flush=True); return

    idx = read_index()
    processed = 0
    saved = 0

    try:
        for i, p in enumerate(files, start=1):
            base = p.stem
            clean_base = base.split(" (")[0].strip()

            raw = p.read_bytes()
            sha1 = sha1_bytes(raw)

            rec = idx.get(clean_base)
            if rec and rec.get("sha1")==sha1 and Path(rec.get("vectorized","")).exists() and Path(rec.get("thumb","")).exists():
                # уже обработан
                if i % 100 == 0:
                    print(f"[{i}/{total}] пропущено (уже есть): {clean_base}", flush=True)
                continue

            im = Image.open(io.BytesIO(raw)).convert("RGB")
            w,h = im.size
            scale = min(1.0, MAX_DIM/max(w,h))
            im_res = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS) if scale<1.0 else im

            vect_path = (D_VECT/f"{clean_base}.webp")
            im_res.save(vect_path, "WEBP", quality=WEBP_Q, method=6)

            im_th = im_res.copy()
            tw,th = im_th.size
            if max(tw,th)>THUMB:
                s = THUMB/max(tw,th)
                im_th = im_th.resize((int(tw*s), int(th*s)), Image.LANCZOS)
            thumb_path = (D_THMB/f"{clean_base}.webp")
            im_th.save(thumb_path, "WEBP", quality=WEBP_Q, method=6)

            lab = avg_lab(im_res)

            idx[clean_base] = {
                "original": str(p),
                "vectorized": str(vect_path),
                "thumb": str(thumb_path),
                "w": im_res.size[0], "h": im_res.size[1],
                "sha1": sha1,
                "avg_lab": lab,
                "updated": datetime.now().isoformat(timespec="seconds")
            }
            processed += 1
            if processed % SAVE_EVERY == 0:
                save_index(idx); saved += 1
                print(f"[{i}/{total}] сохранено в индекс (батч {saved}), всего обработано: {processed}", flush=True)
            elif processed % 10 == 0:
                print(f"[{i}/{total}] обработано {processed}", flush=True)

        # финальный сейв
        save_index(idx)
        print(f"OK: обработано новых файлов: {processed}, всего записей в индексе: {len(idx)}", flush=True)

    except KeyboardInterrupt:
        # сейв при прерывании руками
        save_index(idx)
        print(f"\nINTERRUPTED: автосейв индекса. Готово записей: {len(idx)}, обработано новых: {processed}", flush=True)
        sys.exit(130)

if __name__ == "__main__":
    main()
