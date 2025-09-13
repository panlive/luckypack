#!/usr/bin/env python3
import os, json, numpy as np, faiss, torch, open_clip
from pathlib import Path
from PIL import Image
from skimage.color import rgb2lab

PROJ = Path("/srv/luckypack/App")
DATA = Path("/app/data/photos")
EMB  = PROJ/"AI/embeddings"
P_PROD = PROJ/"LuckyPricer/products.json"
P_PIDX = DATA/"photos_index.json"

MODEL="ViT-B-32"; PRETRAINED="laion2b_s34b_b79k"; DEVICE="cpu"
W_IMG=float(os.getenv("W_IMG","0.6"))
W_TXT=float(os.getenv("W_TXT","0.3"))
W_COL=float(os.getenv("W_COLOR","0.1"))
K=int(os.getenv("SHORT_K","200"))
N=int(os.getenv("TOP_N","6"))

def load_indexes():
    fa_img = faiss.read_index(str(EMB/"faiss_img.index"))
    img_ids = np.load(EMB/"img_ids.npy", allow_pickle=True)
    img_lab = np.load(EMB/"img_lab.npy")
    fa_txt = faiss.read_index(str(EMB/"faiss_txt.index"))
    txt_ids = np.load(EMB/"txt_ids.npy", allow_pickle=True)
    return (fa_img,img_ids,img_lab),(fa_txt,txt_ids)

def encode_image(path):
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL, pretrained=PRETRAINED, device=DEVICE)
    im = Image.open(path).convert("RGB")
    with torch.no_grad():
        x = preprocess(im).unsqueeze(0)
        v = model.encode_image(x).float().cpu().numpy()[0]
        v /= (np.linalg.norm(v)+1e-9)
    # avg Lab
    sm = im.copy(); sm.thumbnail((256,256))
    arr = np.asarray(sm.convert("RGB"), dtype=np.float32)/255.0
    lab = rgb2lab(arr); q_lab = np.array([lab[...,0].mean(), lab[...,1].mean(), lab[...,2].mean()], dtype=np.float32)
    return v, q_lab

def color_sim(q_lab, c_lab):
    d = float(np.linalg.norm(q_lab - c_lab))
    return np.exp(-d/20.0)

def pick_auto_query():
    # берём первый артикул из image-индекса и его путь из photos_index.json
    pidx = json.load(open(P_PIDX,"r",encoding="utf-8"))
    ids = np.load(EMB/"img_ids.npy", allow_pickle=True)
    for art in ids:
        rec = pidx.get(str(art))
        if rec:
            path = rec.get("vectorized") or rec.get("original")
            if path and Path(path).exists():
                return str(art), path
    raise SystemExit("Не нашёл подходящее фото для авто-теста")

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", help="Путь к фото для запроса")
    ap.add_argument("--auto", action="store_true", help="Взять любое фото из индекса")
    args = ap.parse_args()

    (fa_img,img_ids,img_lab),(fa_txt,txt_ids) = load_indexes()
    if args.auto:
        art, qpath = pick_auto_query()
        print(f"[auto] Взял фото артикула {art}: {qpath}")
    elif args.query:
        qpath = args.query
    else:
        raise SystemExit("Укажи --query /путь/к/фото.jpg или --auto")

    q_vec, q_lab = encode_image(qpath)

    # shortlist по image->image
    D, I = fa_img.search(q_vec.reshape(1,-1), min(K, fa_img.ntotal))
    cand_ids = img_ids[I[0]]
    cand_img_sim = D[0]

    # подготовим словари для быстрого доступа
    # карта: артикул -> позиция в txt_ids (если есть в текстовом индексе)
    txt_pos = { str(code): i for i,code in enumerate(txt_ids.tolist()) }
    products = { str(it.get("Артикул","")).strip(): it for it in json.load(open(P_PROD,"r",encoding="utf-8")) }
    pidx = json.load(open(P_PIDX,"r",encoding="utf-8"))

    # считаем финальный скор для кандидатов
    results=[]
    for sim_i, art, lab in zip(cand_img_sim, cand_ids, img_lab[I[0]]):
        art = str(art)
        sim_t = 0.0
        j = txt_pos.get(art)
        if j is not None:
            # реконструируем текстовый вектор по индексу
            tv = np.zeros((fa_txt.d,), dtype=np.float32)
            fa_txt.reconstruct(j, tv)
            sim_t = float(np.dot(q_vec, tv))  # cos/IP, т.к. нормированы
        sim_c = color_sim(q_lab, lab)
        score = W_IMG*float(sim_i) + W_TXT*sim_t + W_COL*sim_c

        prod = products.get(art, {})
        name = prod.get("Наименование","")
        cat  = prod.get("Категория","")
        price= prod.get("Цена (коробка)","")
        thumb= (pidx.get(art) or {}).get("thumb","")

        results.append((score, art, name, cat, price, thumb))

    results.sort(key=lambda x: x[0], reverse=True)
    top = results[:N]

    print("\nTOP-N:")
    for i,(s,art,name,cat,price,thumb) in enumerate(top, start=1):
        print(f"{i:02d}. {art} | {name} | [{cat}] | цена:{price} | score={s:.4f}")
    print("\nПодсказка: можно вызвать с --query /путь/к/фото.jpg для произвольного фото.")

if __name__=="__main__":
    main()
