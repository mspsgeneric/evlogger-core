# bylaws/fetch_character.py
import sys
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
import re

import requests

# ------------------ Config "hardcoded" mas portável ------------------
BASE_DIR = Path(__file__).resolve().parent  # pasta 'bylaws' onde está este arquivo
URL = "https://www.owbn.net/bylaws/character"

DEST_HTML = BASE_DIR / "bylaws_character.html"
DEST_META = BASE_DIR / "bylaws_character.meta.json"
DEST_CSV  = BASE_DIR / "bylaws_output.csv"

USER_AGENT = "evlogger-bylaws-fetcher/1.0"
TIMEOUT = 20          # segundos
RETRIES = 3
BACKOFF_BASE = 1.8
# ---------------------------------------------------------------------

def normalize_for_hash(html: str) -> str:
    html = html.replace("\r", "")
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"\s+", " ", html)
    return html.strip()

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_meta() -> dict:
    if DEST_META.exists():
        try:
            return json.loads(DEST_META.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_meta(meta: dict):
    tmp = DEST_META.with_suffix(".meta.json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DEST_META)

def validate_response(resp: requests.Response) -> str | None:
    if resp.status_code != 200:
        print(f"[bylaws] HTTP {resp.status_code} ao baixar.")
        return None
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "text/html" not in ctype:
        print(f"[bylaws] Content-Type inesperado: {ctype}")
        return None
    try:
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
    except Exception as e:
        print(f"[bylaws] Falha ao decodificar HTML: {e}")
        return None

    if not html or "<html" not in html.lower():
        print("[bylaws] Resposta não parece conter HTML válido.")
        return None
    if len(html) < 2000:
        print("[bylaws] HTML muito curto; pode ser queda da página.")
        return None
    return html

def http_get_with_retries(url: str, headers: dict) -> requests.Response | None:
    for attempt in range(1, RETRIES + 1):
        try:
            return requests.get(url, headers=headers, timeout=TIMEOUT)
        except Exception as e:
            if attempt == RETRIES:
                print(f"[bylaws] Falha definitiva: {e}")
                return None
            wait = BACKOFF_BASE ** (attempt - 1)
            print(f"[bylaws] Erro de rede (tentativa {attempt}/{RETRIES}): {e} — novo teste em {wait:.1f}s")
            time.sleep(wait)
    return None

def fetch_once() -> tuple[str, str | None]:
    """
    Retorna (status, detalhe)
      status ∈ {"updated","not-modified","no-change-hash","error"}
    """
    meta = load_meta()
    etag = meta.get("etag")
    last_mod = meta.get("last_modified")

    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_mod:
        headers["If-Modified-Since"] = last_mod

    resp = http_get_with_retries(URL, headers)
    if resp is None:
        return ("error", "rede/timeout")

    if resp.status_code == 304:
        print("[bylaws] 304 Not Modified — remoto inalterado.")
        return ("not-modified", None)

    html = validate_response(resp)
    if html is None:
        return ("error", f"resposta inválida (HTTP {resp.status_code})")

    norm = normalize_for_hash(html)
    new_hash = sha256_text(norm)
    old_hash = meta.get("sha256")

    if old_hash and new_hash == old_hash:
        meta["checked_at"] = datetime.utcnow().isoformat() + "Z"
        meta["last_http_status"] = resp.status_code
        meta["last_url"] = str(resp.url)
        meta["etag"] = resp.headers.get("ETag") or etag
        meta["last_modified"] = resp.headers.get("Last-Modified") or last_mod
        save_meta(meta)
        print("[bylaws] Hash idêntico — nenhuma alteração real.")
        return ("no-change-hash", None)

    # grava atômico
    tmpfile = DEST_HTML.with_suffix(".html.tmp")
    tmpfile.write_text(html, encoding="utf-8")
    tmpfile.replace(DEST_HTML)

    meta.update({
        "sha256": new_hash,
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "last_http_status": resp.status_code,
        "last_url": str(resp.url),
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "content_length": len(html),
    })
    save_meta(meta)

    print(f"[bylaws] ✅ HTML atualizado: {DEST_HTML} ({len(html)} bytes)")
    return ("updated", None)

def run_parser():
    # Import local: mesmo diretório
    sys.path.insert(0, str(BASE_DIR))
    from bylaws_parser import parse_html
    try:
        parse_html(str(DEST_HTML), str(DEST_CSV))
        print(f"[bylaws] ✅ CSV regenerado: {DEST_CSV}")
    except Exception as e:
        print(f"[bylaws] ⚠️ Falha ao rodar parser: {e}")

def main() -> int:
    status, info = fetch_once()
    if status == "updated":
        run_parser()
        return 0
    elif status in ("not-modified", "no-change-hash"):
        print("[bylaws] Sem mudanças — nada a fazer.")
        return 0
    else:
        print(f"[bylaws] Falha ao atualizar: {info}")
        # saída “suave”: reexecuta amanhã sem quebrar o processo
        return 2

if __name__ == "__main__":
    sys.exit(main())
