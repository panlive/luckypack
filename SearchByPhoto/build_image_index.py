#!/usr/bin/env python3
"""
build_image_index.py — построение CLIP-индекса для изображений.
• Читает photos_index.json + products.json, отбирает артикулы с картинками.
• Кодирует в эмбеддинги (open-clip), нормализует, пишет FAISS: AI/embeddings/faiss_img.index.
• Сохраняет маппинги: img_ids.npy (артикулы), img_lab.npy (средний Lab-цвет).
Требует: open-clip-torch, faiss-cpu, torch (CPU).
"""
import json, os, numpy as np, faiss, torch, open_clip
from pathlib import Path
from PIL import Image

# Пути
PROJ = Path("/srv/luckypack/project")
DATA = Path("/app/data/photos")
P_IDX = DATA/"photos_index.json"                    # индекс фоток (из image_opt.py)
P_PROD= PROJ/"LuckyPricer/products.json"           # товары (с «Артикул»)
DOUT  = PROJ/"SearchByPhoto/index"                       # сюда сложим faiss и *.npy
DOUT.mkdir(parents=True, exist_ok=True)

# Модель — лёгкая
MODEL="ViT-B-32"
PRETRAINED="laion2b_s34b_b79k"
DEVICE="cpu"
BATCH=int(os.getenv("IMG_BATCH","32"))

def load_lists():
    # товары
    prod = json.load(open(P_PROD, "r", encoding="utf-8"))
    arts = { str(r.get("Артикул","")).strip() for r in prod if str(r.get("Артикул","")).strip() }
    # индекс фото
    pidx = json.load(open(P_IDX, "r", encoding="utf-8"))
    # берём только те записи, где ключ совпадает с артикулом и есть файл
    items=[]
    misses_art=0; misses_file=0
    for key, rec in pidx.items():
        art = str(key).strip()
        if art not in arts:
            misses_art += 1
            continue
        path = rec.get("vectorized") or rec.get("original")
        if not path or not Path(path).exists():
            misses_file += 1
            continue
        lab = rec.get("avg_lab",[50.0,0.0,0.0])
        items.append((art, path, lab))
    return items, misses_art, misses_file

def encode_paths(items, batch=BATCH):
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED, device=DEVICE)
    ids, labs, embs = [], [], []
    def flush(buf_imgs, buf_ids, buf_labs):
        if not buf_imgs: return
        with torch.no_grad():
            x = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in buf_imgs], dim=0)
            v = model.encode_image(x).float().cpu().numpy()
            v /= (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        embs.append(v); ids.extend(buf_ids); labs.extend(buf_labs)
    buf_imgs, buf_ids, buf_labs = [], [], []
    for i,(art, path, lab) in enumerate(items, start=1):
        buf_imgs.append(path); buf_ids.append(art); buf_labs.append(np.array(lab, dtype=np.float32))
        if len(buf_imgs) >= batch:
            flush(buf_imgs, buf_ids, buf_labs); buf_imgs.clear(); buf_ids.clear(); buf_labs.clear()
            if i % (batch*10) == 0: print(f"[encode] {i}/{len(items)}", flush=True)
    flush(buf_imgs, buf_ids, buf_labs)
    E = np.vstack(embs) if embs else np.zeros((0,512), dtype=np.float32)  # ViT-B/32 → 512
    I = np.array(ids, dtype=object)
    L = np.vstack(labs) if labs else np.zeros((0,3), dtype=np.float32)
    return E, I, L

def main():
    if not P_IDX.exists(): raise SystemExit(f"Нет {P_IDX}, сперва запусти image_opt.py")
    if not P_PROD.exists(): raise SystemExit(f"Нет {P_PROD}")
    items, miss_art, miss_file = load_lists()
    if not items: raise SystemExit("Нет пересечения фото с артикулами из products.json")

    print(f"Готовим эмбеддинги: фото к индексации: {len(items)} (пропущено без артикула: {miss_art}, без файла: {miss_file})", flush=True)
    E, I, L = encode_paths(items)
    index = faiss.IndexFlatIP(E.shape[1]); index.add(E)

    # Сохраняем
    faiss.write_index(index, str(DOUT/"faiss_img.index"))
    np.save(DOUT/"img_ids.npy", I)
    np.save(DOUT/"img_lab.npy", L)

    print(f"OK: image-индекс построен. Векторов: {index.ntotal}")
    print("Файлы:", DOUT/"faiss_img.index", DOUT/"img_ids.npy", DOUT/"img_lab.npy")

if __name__ == "__main__":
    main()
