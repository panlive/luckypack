#!/usr/bin/env python3
import os, json, argparse, asyncio, numpy as np, faiss, torch, open_clip
from pathlib import Path
from PIL import Image
from skimage.color import rgb2lab
from aiogram import Bot
from aiogram.types import InputMediaPhoto, InputFile
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from dotenv import load_dotenv

PROJ = Path("/srv/luckypack/App")
load_dotenv(PROJ/".env")  # подхватываем TELEGRAM_BOT_TOKEN и SUPERADMIN_ID из .env

DATA = Path("/app/data/photos")
EMB  = PROJ/"AI/embeddings"
P_PROD = PROJ/"LuckyPricer/products.json"
P_PIDX = DATA/"photos_index.json"
OUTDIR = Path("/app/data/PhotoPicks"); OUTDIR.mkdir(parents=True, exist_ok=True)
TMPPNG = OUTDIR/"_png"; TMPPNG.mkdir(parents=True, exist_ok=True)

MODEL="ViT-B-32"; PRETRAINED="laion2b_s34b_b79k"; DEVICE="cpu"
W_IMG=float(os.getenv("W_IMG","0.6")); W_TXT=float(os.getenv("W_TXT","0.3")); W_COL=float(os.getenv("W_COLOR","0.1"))
K=int(os.getenv("SHORT_K","200")); N=int(os.getenv("TOP_N","6")); THRESH=float(os.getenv("THRESH","0.32"))

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
    sm = im.copy(); sm.thumbnail((256,256))
    arr = np.asarray(sm.convert("RGB"), dtype=np.float32)/255.0
    lab = rgb2lab(arr); q_lab = np.array([lab[...,0].mean(), lab[...,1].mean(), lab[...,2].mean()], dtype=np.float32)
    return v, q_lab

def color_sim(q_lab, c_lab):
    import numpy as np
    d = float(np.linalg.norm(q_lab - c_lab))
    return np.exp(-d/20.0)

def pick_auto_query():
    pidx = json.load(open(P_PIDX,"r",encoding="utf-8"))
    ids = np.load(EMB/"img_ids.npy", allow_pickle=True)
    for art in ids:
        rec = pidx.get(str(art))
        if rec:
            path = rec.get("vectorized") or rec.get("original")
            if path and Path(path).exists():
                return str(art), path
    raise SystemExit("Нет подходящего фото для авто-теста")

def build_excel(rows, out_path):
    wb=Workbook(); ws=wb.active; ws.title="Подбор по фото"
    ws.append(["Фото","Наименование","Артикул","Категория","Цена (коробка)","Спец. цена","Ваш заказ"])
    for r in rows:
        ws.append(["", r["Наименование"], r["Артикул"], r.get("Категория",""), r.get("Цена (коробка)",""), r.get("Спец. цена",""), ""])
        thumb = r.get("_thumb")
        if thumb and Path(thumb).exists():
            base = Path(thumb).stem; out_png = TMPPNG / f"{base}.png"
            try:
                Image.open(thumb).convert("RGBA").save(out_png, "PNG")
                img = XLImage(str(out_png)); img.width=96; img.height=96
                ws.add_image(img, f"A{ws.max_row}")
            except Exception as e:
                print(f"⚠️ PNG для XLSX не вставлен ({r.get('Артикул')}): {e}")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True); wb.save(out_path)

def search_top(query_path, n=N):
    (fa_img,img_ids,img_lab),(fa_txt,txt_ids) = load_indexes()
    products = { str(it.get("Артикул","")).strip(): it for it in json.load(open(P_PROD,"r",encoding="utf-8")) }
    pidx = json.load(open(P_PIDX,"r",encoding="utf-8"))
    q_vec, q_lab = encode_image(query_path)

    D, I = fa_img.search(q_vec.reshape(1,-1), min(K, fa_img.ntotal))
    cand_ids = img_ids[I[0]]; cand_img_sim = D[0]; txt_pos = { str(code): i for i,code in enumerate(txt_ids.tolist()) }

    results=[]
    for sim_i, art, lab in zip(cand_img_sim, cand_ids, img_lab[I[0]]):
        art = str(art)
        prod = dict(products.get(art, {}))
        if not prod: continue
        sim_t = 0.0
        j = txt_pos.get(art)
        if j is not None:
            tv = np.zeros((fa_txt.d,), dtype=np.float32); fa_txt.reconstruct(j, tv)
            sim_t = float(np.dot(q_vec, tv))
        sim_c = color_sim(q_lab, lab)
        score = W_IMG*float(sim_i) + W_TXT*sim_t + W_COL*sim_c

        rec = pidx.get(art, {})
        prod["_thumb"] = rec.get("thumb",""); prod["_score"] = float(score)
        results.append(prod)

    results.sort(key=lambda r: r["_score"], reverse=True)
    return results[:n]

async def send_to_telegram(results, excel_path, query_path):
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat = os.getenv("CHAT_ID") or os.getenv("SUPERADMIN_ID")
    if not token:
        raise SystemExit("Не найден TELEGRAM_BOT_TOKEN (ни в .env, ни в окружении)")
    if not chat:
        raise SystemExit("Не найден CHAT_ID/SUPERADMIN_ID (ни в .env, ни в окружении)")
    bot = Bot(token=token, parse_mode=None)

    # 1) альбом фото (конвертация webp -> png)
    media=[]
    for r in results:
        t = r.get("_thumb")
        if not t or not Path(t).exists(): continue
        png = TMPPNG / f"{Path(t).stem}.png"
        try:
            Image.open(t).convert("RGB").save(png, "PNG")
        except Exception as e:
            print(f"⚠️ PNG для Telegram не создан ({r.get('Артикул')}): {e}"); continue
        media.append(InputMediaPhoto(media=InputFile(str(png))))
    if media:
        await bot.send_media_group(chat_id=int(chat), media=media)

    # 2) документ XLSX
    if excel_path and Path(excel_path).exists():
        await bot.send_document(chat_id=int(chat), document=InputFile(str(excel_path)), caption="Подбор по фото")

    # 3) список подписей
    lines=[]
    for i,r in enumerate(results, start=1):
        n=f"{i:02d}"
        lines.append(f"[{n}] Артикул: {r.get('Артикул','')}\n{r.get('Наименование','')}\nЦена (коробка): {r.get('Цена (коробка)','')}")
    text="\n\n".join(lines)
    await bot.send_message(chat_id=int(chat), text=text[:4000])

    await bot.session.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", help="Путь к фото клиента")
    ap.add_argument("--auto", action="store_true", help="Взять авто-пример из индекса")
    ap.add_argument("--n", type=int, default=N)
    args = ap.parse_args()

    if args.auto:
        art, qpath = pick_auto_query()
        print(f"[auto] Фото артикула {art}: {qpath}")
    elif args.query:
        qpath = args.query
    else:
        raise SystemExit("Укажи --query /путь/к/фото.jpg или --auto")

    results = search_top(qpath, n=args.n)
    if not results:
        raise SystemExit("Пустой результат")

    excel_path = OUTDIR / "Подбор_по_фото.xlsx"
    build_excel(results, str(excel_path))
    print(f"XLSX: {excel_path}")

    asyncio.run(send_to_telegram(results, str(excel_path), qpath))
    print("Отправлено в Telegram.")

if __name__=="__main__":
    main()
