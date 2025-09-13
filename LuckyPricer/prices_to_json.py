#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, json, logging
import pandas as pd
import numpy as np

try:
    from admin_notify import notify_admin
except Exception:
    def notify_admin(message: str, module: str = "prices_to_json"): pass

BASE = os.path.dirname(os.path.abspath(__file__))
PRICES_DIR = os.path.join(BASE, "data", "prices")
JSONS_DIR  = os.path.join(BASE, "data", "jsons")
LOGS_DIR = os.getenv("LOGS_DIR", "/srv/luckypack/logs")
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(JSONS_DIR, exist_ok=True); os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "/srv/luckypack/logs/prices_to_json.log")
logging.basicConfig(filename=LOG_FILE, filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO, encoding='utf-8')
def log(msg, level="info"): print(msg); getattr(logging, level)(msg)

REQUIRED = [
    "Артикул",
    "Номенклатура, Характеристика, Упаковка",
    "ШТ/КОР",
    "ОПТ с НДС",
    "ОПТ с НДС от 150 000 руб.",
    "СПЕЦ ЦЕНА",
]

def nz(x)->str:
    s=str(x if x is not None else "").strip()
    return "" if s.lower() in {"nan","none"} else s

def norm(s:str)->str:
    s=nz(s).lower().replace("ё","е")
    s=re.sub(r"[^\w\s/\.]", " ", s)
    s=re.sub(r"\s+", " ", s).strip()
    return s

HINTS = ["артик","штрих","barcode","ean","наимен","номенклат","характер",
         "упаков","колич","короб","упак","опт","спец","цена","ндс","шт/кор"]
EAN_RE = re.compile(r"^\d{8,14}$")

def find_header_base(raw: pd.DataFrame) -> int:
    for r in range(min(60, len(raw))):
        vals = [norm(v) for v in raw.iloc[r].tolist()]
        if any(v == "артикул" for v in vals):
            if r>0 and any(bool(nz(x)) for x in raw.iloc[r-1].tolist()):
                return r-1
            return r
    for r in range(min(60, len(raw))):
        vals = [norm(v) for v in raw.iloc[r].tolist()]
        hits = sum(any(h in v for h in HINTS) for v in vals)
        if hits >= 1: return r
    for r in range(len(raw)):
        if raw.iloc[r].notna().any(): return r
    return 0

def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join([nz(x) for x in t]) for t in df.columns.to_list()]
    df.columns = [nz(c) for c in df.columns]
    return df

def read_excel_robust(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    engine = "openpyxl" if ext == ".xlsx" else None
    raw = pd.read_excel(path, header=None, dtype=str, engine=engine)
    hdr = find_header_base(raw)
    tried = ([hdr, hdr+1], [hdr+1], [hdr, hdr+1, hdr+2])
    df_ok = None; last = None
    for header in tried:
        try:
            tmp = pd.read_excel(path, header=header, dtype=str, engine=engine)
        except Exception:
            continue
        last = tmp
        tmp = tmp.dropna(how="all")
        if not tmp.empty: tmp = tmp.loc[:, tmp.notna().any()]
        tmp = flatten_columns(tmp)
        cols_norm = [norm(c) for c in tmp.columns]
        if any(any(k in c for k in ["артик","штрих","barcode","ean"]) for c in cols_norm):
            df_ok = tmp; break
    if df_ok is None:
        df_ok = flatten_columns(last if last is not None else pd.read_excel(path, header=None, dtype=str, engine=engine).fillna(""))
        if list(df_ok.columns) == list(range(len(df_ok.columns))):
            df_ok.columns = [f"c{i}" for i in range(df_ok.shape[1])]
    return df_ok

def guess_by_pattern(df: pd.DataFrame) -> dict:
    m = {}
    # артикул — колонка с макс. EAN-подобных
    best_i, best_cnt = None, -1
    for c in df.columns:
        vals = df[c].astype(str).map(lambda s: 1 if EAN_RE.fullmatch(s.strip()) else 0)
        cnt = int(vals.sum()); 
        if cnt > best_cnt: best_cnt, best_i = cnt, c
    if best_i and best_cnt>0: m["Артикул"] = best_i
    # имя — самая «текстовая» (много букв), не цена/не артикул
    longest_i, longest_len = None, -1
    for c in df.columns:
        if c == m.get("Артикул"): continue
        s = df[c].astype(str)
        letters = s.map(lambda x: 1 if re.search(r"[A-Za-zА-Яа-я]", str(x)) else 0).mean()
        avglen  = s.map(lambda x: len(str(x))).mean()
        # не брать чисто числовые столбцы
        numeric_ratio = s.map(lambda x: 1 if re.fullmatch(r"\s*[\d\s.,]+\s*", str(x) or "") else 0).mean()
        score = letters*2 + avglen*0.01 - numeric_ratio*2
        if score > longest_len:
            longest_len, longest_i = score, c
    if longest_i: m["Номенклатура, Характеристика, Упаковка"] = longest_i
    return m

def guess_mapping(df: pd.DataFrame) -> dict:
    cols = list(df.columns); ncols = [norm(c) for c in cols]
    def best(pred, anti=None):
        best_i, best_score = None, -1
        for i, nc in enumerate(ncols):
            score = pred(nc)
            if anti and anti(nc): score = -999
            if score > best_score: best_score, best_i = score, i
        return cols[best_i] if best_score > 0 else None

    art_col = best(lambda c: 5 if re.search(r"\b(артик|штрих|barcode|ean)\b", c) else 0)

    def name_score(c):
        if "номенклатура, характеристика, упаковка" in c: return 10
        s=0
        if "наимен" in c or "характер" in c or "номенклат" in c: s+=3
        return s
    name_col = best(name_score, anti=lambda c: any(k in c for k in ["колич","короб","упак"]))

    def qty_score(c):
        if "шт/кор" in c or "шт / кор" in c or "шт кор" in c: return 10
        if "колич" in c and ("короб" in c or "упак" in c): return 8
        if "в упаковке" in c and "шт" in c: return 6
        if "колич" in c: return 4
        return 0
    qty_col = best(qty_score)

    def p1_score(c):
        s=0
        if "опт" in c: s+=3
        if "ндс" in c: s+=2
        if "цена" in c: s+=1
        if "150" in c or "спец" in c: s=0
        return s
    def p150_score(c):
        s=0
        if "опт" in c: s+=2
        if "150" in c: s+=3
        if "цена" in c: s+=1
        return s
    def pspec_score(c):
        return 5 if ("спец" in c and "цена" in c) else 0

    price1_col    = best(p1_score)
    price150_col  = best(p150_score)
    price_speccol = best(pspec_score)

    m = {k:v for k,v in {
        "Артикул": art_col,
        "Номенклатура, Характеристика, Упаковка": name_col,
        "ШТ/КОР": qty_col,
        "ОПТ с НДС": price1_col,
        "ОПТ с НДС от 150 000 руб.": price150_col,
        "СПЕЦ ЦЕНА": price_speccol,
    }.items() if v}

    # если критичных нет — добираем по данным
    if ("Артикул" not in m) or ("Номенклатура, Характеристика, Упаковка" not in m):
        m = {**guess_by_pattern(df), **m}
    return m

def to_price(x)->str:
    s=nz(x).replace("руб","").replace("rub","").replace(" ", "").replace(",",".")
    try: return f"{float(s):.2f}".replace(".",",")
    except: return nz(x)

def filter_rows(df: pd.DataFrame)->pd.DataFrame:
    if "Артикул" in df.columns:
        df = df.loc[df["Артикул"].map(lambda x: bool(nz(x)))]
    return df

def pick_text_from_row(src_row: pd.Series, exclude_cols:set) -> str:
    best = ""
    for col, val in src_row.items():
        if col in exclude_cols: continue
        s = nz(val)
        if not s: continue
        # брать только «текстовые» значения
        if re.search(r"[A-Za-zА-Яа-я]", s) and not re.fullmatch(r"\s*[\d\s.,]+\s*", s):
            if len(s) > len(best):
                best = s
    return best

def process_file(src: str, dst: str)->bool:
    df = read_excel_robust(src)
    m = guess_mapping(df)
    if "Артикул" not in m: raise RuntimeError("Не найден столбец для 'Артикул'")
    if "Номенклатура, Характеристика, Упаковка" not in m: raise RuntimeError("Не найден столбец для 'Номенклатура, Характеристика, Упаковка'")

    # собираем базу
    out = pd.DataFrame()
    for need in REQUIRED:
        col = m.get(need)
        out[need] = df[col].map(nz) if col in df.columns else ""
    # индексы out совпадают с исходным df; сохраним ссылку
    src_df = df

    # приведение цен
    for pcol in ["ОПТ с НДС","ОПТ с НДС от 150 000 руб.","СПЕЦ ЦЕНА"]:
        if pcol in out.columns:
            out[pcol] = out[pcol].map(to_price)

    # чистим пустые артикула
    out = filter_rows(out).applymap(nz)

    # ФИКС ИМЁН ПО СТРОКЕ: если имя пусто/как артикул/как EAN -> добираем из исходной строки
    name_col = "Номенклатура, Характеристика, Упаковка"
    art_col  = "Артикул"
    exclude = {m.get("Артикул"), m.get("ШТ/КОР"), m.get("ОПТ с НДС"),
               m.get("ОПТ с НДС от 150 000 руб."), m.get("СПЕЦ ЦЕНА")}
    for i in out.index:
        name = nz(out.at[i, name_col]); art = nz(out.at[i, art_col])
        bad = (not name) or (name == art) or bool(EAN_RE.fullmatch(name))
        if bad:
            src_row = src_df.loc[i] if i in src_df.index else None
            cand = pick_text_from_row(src_row, exclude_cols=set([c for c in exclude if c])) if src_row is not None else ""
            if cand: out.at[i, name_col] = cand

    with open(dst,"w",encoding="utf-8") as f:
        json.dump(out.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    return True

def main():
    files = [f for f in os.listdir(PRICES_DIR) if f.lower().endswith((".xls",".xlsx")) and not f.startswith("~$")]
    if not files:
        msg="❗ Нет Excel-файлов в data/prices"; log(msg,"warning"); notify_admin(msg); return
    ok=0
    for fname in files:
        src=os.path.join(PRICES_DIR,fname)
        dst=os.path.join(JSONS_DIR, f"{os.path.splitext(fname)[0]}.json")
        try:
            if process_file(src,dst):
                log(f"✅ {fname} → {os.path.basename(dst)}"); ok+=1
        except Exception as e:
            log(f"❌ Ошибка конвертации {fname}: {e}", "error"); notify_admin(f"{fname}: {e}")
    log(f"🏁 Готово. Успешно: {ok} из {len(files)}")
if __name__=="__main__": main()
