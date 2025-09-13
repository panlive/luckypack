#!/usr/bin/env python3
# pull_missing_to_vectorized.py
# Назначение: из разницы (Я.Диск ∩ products.json) − vectorized докачать только недостающее
# Входы: config.py (YANDEX_DISK_LINK_PHOTOS, LOGS_DIR), products.json, /app/data/photos/vectorized
# Выходы: .webp в vectorized; временные оригиналы в temp (удаляются после конверта)
# Логи: LOGS_DIR/photos_pull.log
import os, sys, re, json, shutil, subprocess, time, pathlib, requests

# --- конфиг и пути ---
PR = "/srv/luckypack/project"
sys.path[:0] = [PR, os.path.join(PR, "LuckyDownloader")]
from config import YANDEX_DISK_LINK_PHOTOS, LOGS_DIR
from photo_sync.yandex_api import extract_public_key_from_url, get_all_files_recursive

VEC_DIR = "/app/data/photos/vectorized"
TEMP_DIR = "/app/data/photos/temp"
PJSON   = "/srv/luckypack/project/LuckyPricer/products.json"
LOGF    = os.path.join(LOGS_DIR or "/srv/luckypack/logs", "photos_pull.log")

def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    os.makedirs(os.path.dirname(LOGF), exist_ok=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(msg)

def is_ean13(s): return bool(re.fullmatch(r"\d{13}", (s or "").strip()))
def stem13(name):
    base = os.path.splitext(name)[0]
    return base if is_ean13(base) else None

def load_products():
    try:
        with open(PJSON,"r",encoding="utf-8") as f:
            data=json.load(f)
        items = data if isinstance(data,list) else data.get("items",[])
        s=set()
        for it in items:
            a=(it.get("Артикул") or "").strip()
            if is_ean13(a): s.add(a)
        return s
    except Exception as e:
        log(f"ERR read products.json: {e}")
        return set()

def list_vectorized():
    s=set()
    if os.path.isdir(VEC_DIR):
        for n in os.listdir(VEC_DIR):
            if n.startswith("_"): continue
            if n.lower().endswith(".webp"):
                st=stem13(n)
                if st: s.add(st)
    return s

def list_cloud_eans():
    link=(os.getenv("YANDEX_DISK_LINK_PHOTOS") or YANDEX_DISK_LINK_PHOTOS or "").strip()
    key=extract_public_key_from_url(link)
    files=get_all_files_recursive(link)
    eans={}
    for it in files or []:
        n=(it.get("name") or "").strip()
        if re.fullmatch(r"\d{13}\.(jpg|jpeg|png|webp)", n, re.I):
            e=stem13(n)
            if e and e not in eans:
                eans[e]=it  # первая подходящая
    return eans  # dict ean->filemeta

def have_cwebp():
    try:
        subprocess.run(["cwebp","-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except FileNotFoundError:
        return False

def convert_to_webp(src_path, dst_path):
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if have_cwebp():
        # cwebp качество 90, без экзотики
        res = subprocess.run(["cwebp", "-q", "90", src_path, "-o", dst_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode==0
    # Fallback: Pillow
    try:
        from PIL import Image
        with Image.open(src_path) as im:
            im.save(dst_path, "WEBP", quality=90, method=6)
        return True
    except Exception as e:
        log(f"ERR convert Pillow: {e}")
        return False

def download_one(public_key, path, dst_file):
    url="https://cloud-api.yandex.net/v1/disk/public/resources/download"
    r=requests.get(url, params={"public_key": public_key, "path": path}, timeout=30)
    if r.status_code!=200:
        log(f"ERR get href {path}: {r.status_code}")
        return False
    href=r.json().get("href")
    if not href:
        log(f"ERR empty href for {path}")
        return False
    with requests.get(href, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
        with open(dst_file,"wb") as out:
            for chunk in resp.iter_content(8192): out.write(chunk)
    return True

def main():
    do = ("--do" in sys.argv)
    products = load_products()
    vec = list_vectorized()
    cloud_map = list_cloud_eans()
    cloud = set(cloud_map.keys())

    todo = (cloud & products) - vec

    print(f"products_ean: {len(products)}")
    print(f"cloud_ean   : {len(cloud)}")
    print(f"vectorized  : {len(vec)}")
    print(f"to_pull     : {len(todo)}")
    print("sample      :", sorted(list(todo))[:30])

    if not do:
        print("\nDRY-RUN (ничего не качаю). Запусти с --do для выполнения.")
        return 0

    if len(todo)==0:
        log("No work: nothing to pull")
        return 0

    link=(os.getenv("YANDEX_DISK_LINK_PHOTOS") or YANDEX_DISK_LINK_PHOTOS or "").strip()
    public_# key not needed; pass link as-is

    ok=0; fail=0
    for i,ean in enumerate(sorted(todo),1):
        meta = cloud_map.get(ean)
        path = meta["path"]
        ext = os.path.splitext(meta["name"])[1].lower()
        tmp = os.path.join(TEMP_DIR, f"{ean}{ext}")
        dst = os.path.join(VEC_DIR, f"{ean}.webp")

        try:
            if os.path.exists(dst):
                log(f"Skip exists: {dst}")
                continue
            if not download_one(public_key, path, tmp):
                fail += 1; continue
            if not convert_to_webp(tmp, dst):
                fail += 1; continue
            ok += 1
            log(f"OK {i}/{len(todo)}: {ean} -> vectorized")
        except Exception as e:
            log(f"ERR {ean}: {e}"); fail += 1
        finally:
            try:
                if os.path.exists(tmp): os.remove(tmp)
            except Exception:
                pass
    log(f"DONE: ok={ok}, fail={fail}")
    return 0 if fail==0 else 2

if __name__=="__main__":
    sys.exit(main())
