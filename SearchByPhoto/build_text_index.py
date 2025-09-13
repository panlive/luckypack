#!/usr/bin/env python3
"""
build_text_index.py — построение CLIP-индекса для текстов.
• Читает LuckyPricer/products.json (Артикул, Наименование, Категория).
• Кодирует тексты (open-clip), пишет FAISS: AI/embeddings/faiss_txt.index + txt_ids.npy/txt_cats.npy.
Требует: open-clip-torch, faiss-cpu, torch (CPU).
"""
import json, os, numpy as np, faiss, torch, open_clip
from pathlib import Path

ROOT = Path("/srv/luckypack/project")
PROD = ROOT/"LuckyPricer/products.json"
DOUT = ROOT/"AI/embeddings"
DOUT.mkdir(parents=True, exist_ok=True)

# ЛЁГКАЯ модель (вместо тяжёлой ViT-L/14)
MODEL="ViT-B-32"
PRETRAINED="laion2b_s34b_b79k"
DEVICE="cpu"
BATCH=int(os.getenv("TXT_BATCH","64"))

def load_products():
    if not PROD.exists():
        raise SystemExit(f"Нет файла: {PROD}")
    data = json.load(open(PROD, "r", encoding="utf-8"))
    items=[]
    for it in data:
        art = str(it.get("Артикул","")).strip()
        name = str(it.get("Наименование","")).strip()
        cat  = str(it.get("Категория","")).strip()
        if not art or not name:
            continue
        text = f"{name}. Категория: {cat}" if cat else name
        items.append((art, text, cat))
    if not items:
        raise SystemExit("products.json пуст или без нужных полей")
    return items

def build_text_emb(texts, batch=BATCH):
    model, _, _ = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED, device=DEVICE)
    tok = open_clip.get_tokenizer(MODEL)
    embs=[]
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            t = tok(texts[i:i+batch])
            v = model.encode_text(t).float().cpu().numpy()
            v /= (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
            embs.append(v)
    return np.vstack(embs)

def main():
    items = load_products()
    arts = [a for a,_,_ in items]
    texts= [t for _,t,_ in items]
    cats = [c for *_,c in items]

    emb = build_text_emb(texts)
    index = faiss.IndexFlatIP(emb.shape[1]); index.add(emb)

    (DOUT/"faiss_txt.index").unlink(missing_ok=True)
    faiss.write_index(index, str(DOUT/"faiss_txt.index"))
    np.save(DOUT/"txt_ids.npy",  np.array(arts, dtype=object))
    np.save(DOUT/"txt_cats.npy", np.array(cats, dtype=object))
    print(f"OK: текстовый индекс построен: {index.ntotal} записей")
    print("Файлы:", DOUT/"faiss_txt.index", DOUT/"txt_ids.npy", DOUT/"txt_cats.npy")

if __name__ == "__main__":
    main()
