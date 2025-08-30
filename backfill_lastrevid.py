# backfill_lastrevid_single.py
import os, time, requests
from typing import Dict, List, Optional
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("❌ Missing SUPABASE_URL / SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

API = "https://camarilla.owbn.net/api.php"
HEADERS = {"User-Agent": "evlogger-backfill/single/1.0 (contact: you@example.com)"}

DB_PAGE = 1000      # paginação no DB
SLEEP_API = 0.08    # pausa mínima entre chamadas à wiki
SLEEP_DB  = 0.02

def fetch_missing_rows() -> List[Dict]:
    """Busca todos os registros sem lastrevid e com pageid."""
    out: List[Dict] = []
    start = 0
    while True:
        res = (
            supabase.table("owbn_characters")
            .select("id,pageid,title")
            .is_("lastrevid", "null")
            .not_.is_("pageid", "null")
            .range(start, start + DB_PAGE - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        out.extend(rows)
        start += DB_PAGE
        time.sleep(SLEEP_DB)
    return out

def fetch_meta_single(pid: int) -> Optional[Dict]:
    """Consulta meta para 1 pageid. Retorna {lastrevid, revid_ts} ou None."""
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "info|revisions",
        "pageids": str(pid),
        "rvprop": "ids|timestamp",
        "rvlimit": 1,           # <-- permitido apenas com uma página
    }
    r = requests.get(API, params=params, headers=HEADERS, timeout=40)
    r.raise_for_status()
    j = r.json()

    pages = (j.get("query") or {}).get("pages") or []
    if not pages:
        return None
    pg = pages[0]
    lastrevid = pg.get("lastrevid")
    revs = pg.get("revisions") or []
    ts = revs[0].get("timestamp") if revs else None
    if not lastrevid and revs:
        lastrevid = revs[0].get("revid")  # fallback
    if not lastrevid:
        return None
    return {"lastrevid": lastrevid, "revid_ts": ts}

def main():
    rows = fetch_missing_rows()
    print(f"🔎 Sem lastrevid (com pageid): {len(rows)}")
    if not rows:
        return

    updated = 0
    for idx, r in enumerate(rows, start=1):
        pid = r.get("pageid")
        rid = r.get("id")
        if not isinstance(pid, int) or rid is None:
            continue

        try:
            meta = fetch_meta_single(pid)
        except requests.RequestException as e:
            print(f"⚠️ pid={pid} erro de rede: {e}")
            continue

        if not meta:
            # pode ser página sem revisões ou inacessível
            continue

        # UPDATE por ID (PK). Opcional: encadear .select("*") para retornar linha.
        supabase.table("owbn_characters") \
            .update({"lastrevid": meta["lastrevid"], "revid_ts": meta.get("revid_ts")}) \
            .eq("id", rid) \
            .execute()

        updated += 1
        if idx % 25 == 0:
            print(f"  • {idx}/{len(rows)} processados (atualizados {updated})")
        time.sleep(SLEEP_API)

    left = (
        supabase.table("owbn_characters")
        .select("id", count="exact")
        .is_("lastrevid", "null")
        .execute()
        .count
    )
    print(f"✅ Backfill concluído. Atualizados: {updated} | Faltando lastrevid: {left}")

if __name__ == "__main__":
    main()
