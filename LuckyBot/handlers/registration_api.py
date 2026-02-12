# App/LuckyBot/handlers/registration_api.py
import os, json
import requests
from pathlib import Path

DATA_ROOT = Path("/srv/luckypack/data/clients_registry/raw_dadata")

DADATA_TOKEN = os.getenv("DADATA_API_TOKEN")

def fetch_company_raw(inn: str) -> dict:
    url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Token {DADATA_TOKEN}"
    }
    payload = {"query": inn}

    r = requests.post(url, json=payload, headers=headers, timeout=5)
    r.raise_for_status()

    data = r.json()

    # сохраняем RAW JSON
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    out_file = DATA_ROOT / f"{inn}.json"
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data