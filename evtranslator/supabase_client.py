# evtranslator/supabase_client.py
import os
import requests
from dotenv import load_dotenv
from pathlib import Path

# Carrega .env do diretório atual e, adicionalmente, do root do projeto
load_dotenv()  # tenta CWD
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)  # tenta raiz do projeto

def _get_env():
    base = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not base or not key:
        raise RuntimeError(
            "Faltam SUPABASE_URL e/ou SUPABASE_KEY. "
            "Defina no .env na raiz do projeto (ou export no ambiente)."
        )
    return base.rstrip("/"), key

def _rpc(name: str, payload: dict):
    base, key = _get_env()
    url = f"{base}/rest/v1/rpc/{name}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

def consume_chars(guild_id, amount) -> tuple[bool, int]:
    row = _rpc("rpc_emails_consume_chars", {
        "p_guild_id": str(guild_id),
        "p_amount": int(amount),
    })[0]
    return row["allowed"], row["remaining"]

def get_quota(guild_id) -> dict:
    return _rpc("rpc_emails_get_quota", {"p_guild_id": str(guild_id)})[0]

def ensure_guild_row(guild_id: str):
    base, key = _get_env()
    url = f"{base}/rest/v1/emails?on_conflict=guild_id"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    payload = {"guild_id": str(guild_id)}  # defaults da tabela cuidam do resto
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()
