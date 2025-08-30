# scraper_owbnwiki.py (produção: incremental por lastrevid, com retry/backoff)

import os
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

# ================== CONFIG ==================
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("❌ Missing SUPABASE_URL / SUPABASE_KEY in environment")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://camarilla.owbn.net"
API_URL = f"{BASE_URL}/api.php"

BATCH_SIZE_META = 50            # quantos pageids por chamada (info)
REQUEST_SLEEP = float(os.getenv("SCRAPER_SLEEP", "0.2"))  # pausa entre chamadas
HEADERS = {
    "User-Agent": os.getenv(
        "SCRAPER_UA",
        "evlogger-bio-scraper (contact: seu-email@dominio)"
    )
}
FETCH_REVID_TS_FOR_CHANGED = os.getenv("FETCH_REVID_TS", "1") == "1"
DEBUG_LOG = os.getenv("SCRAPER_DEBUG", "0") == "1"

# ================== HTTP SESSION (retry/backoff) ==================
def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=0.5,            # 0.5s, 1s, 2s, 4s, 8s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(HEADERS)
    return s

SESSION = make_session()


# ================== HELPERS ==================
def supa_get_by_url(url: str) -> Optional[Dict]:
    try:
        data = (
            supabase.table("owbn_characters")
            .select("pageid,lastrevid,hash_conteudo")
            .ilike("url", url)
            .limit(1)
            .execute()
            .data or []
        )
        return data[0] if data else None
    except Exception:
        return None


def _to_int_or_none(v):
    try:
        if v is None:
            return None
        return int(str(v))
    except Exception:
        return None

def gerar_hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()

def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]

def supa_get_existing_meta(pageids: List[int]) -> Dict[int, Dict]:
    out: Dict[int, Dict] = {}
    if not pageids:
        return out

    pids = sorted(set(int(pid) for pid in pageids if pid is not None))

    for chunk in chunked(pids, 500):
        # 👇 FORÇA STRING para casar com coluna pageid TEXT no PostgREST
        str_chunk = [str(x) for x in chunk]

        resp = (
            supabase.table("owbn_characters")
            .select("pageid,lastrevid,hash_conteudo")
            .in_("pageid", str_chunk)
            .limit(len(str_chunk))
            .execute()
        )
        for row in resp.data or []:
            # row["pageid"] vem como string — normalizamos para int
            try:
                pid = int(row["pageid"])
            except Exception:
                continue
            out[pid] = {
                "lastrevid": row.get("lastrevid"),
                "hash_conteudo": row.get("hash_conteudo"),
            }
        time.sleep(0.01)

    return out


    pids = sorted(set(int(pid) for pid in pageids if pid is not None))

    for chunk in chunked(pids, 500):
        resp = (
            supabase.table("owbn_characters")
            .select("pageid,lastrevid,hash_conteudo")
            .in_("pageid", chunk)
            .limit(len(chunk))
            .execute()
        )
        for row in resp.data or []:
            pid = int(row["pageid"])
            out[pid] = {
                "lastrevid": row.get("lastrevid"),
                "hash_conteudo": row.get("hash_conteudo"),
            }
        time.sleep(0.01)  # gentileza mínima
    return out

def salvar_personagem(item: dict):
    """
    1) Tenta mesclar por URL (case-insensitive). Se existir, faz UPDATE só dos campos não-nulos
       e garante o pageid correto no registro.
    2) Se não existir por URL, faz UPSERT por pageid.
    3) Se o UPSERT falhar por UNIQUE(url), recupera por URL e faz UPDATE.
    """
    url = (item.get("url") or "").strip()
    # sanitiza pageid
    pid = item.get("pageid")
    try:
        pid = int(pid) if pid is not None else None
    except Exception:
        pid = None
    if pid is not None:
        item["pageid"] = pid  # normaliza para int

    def _non_nulls(d: dict) -> dict:
        # evita rebaixar valores válidos para NULL
        return {k: v for k, v in d.items() if v is not None}

    # 1) tenta mesclar por URL
    if url:
        try:
            found = (
                supabase.table("owbn_characters")
                .select("id,pageid,lastrevid,hash_conteudo")
                .ilike("url", url)
                .limit(1)
                .execute()
                .data or []
            )
        except Exception:
            found = []

        if found:
            rid = found[0]["id"]
            # preserva lastrevid/hash se o novo vier None
            merged = dict(found[0])  # base no que há no DB
            merged.update(_non_nulls(item))  # só sobrepõe não-nulos
            # garante pageid correto
            if pid is not None:
                merged["pageid"] = pid
            supabase.table("owbn_characters").update(merged).eq("id", rid).execute()
            return

    # 2) upsert por pageid (fallback)
    try:
        supabase.table("owbn_characters").upsert(item, on_conflict="pageid").execute()
        return
    except Exception as e:
        # 3) se colidiu no UNIQUE lower(url), resolve por URL
        emsg = str(getattr(e, "args", [e])[0]).lower()
        if "23505" in emsg or "url_uidx" in emsg or "unique constraint" in emsg:
            if url:
                try:
                    found = (
                        supabase.table("owbn_characters")
                        .select("id,pageid,lastrevid,hash_conteudo")
                        .ilike("url", url)
                        .limit(1)
                        .execute()
                        .data or []
                    )
                except Exception:
                    found = []
                if found:
                    rid = found[0]["id"]
                    merged = dict(found[0])
                    merged.update(_non_nulls(item))
                    if pid is not None:
                        merged["pageid"] = pid
                    supabase.table("owbn_characters").update(merged).eq("id", rid).execute()
                    return
        # se não foi colisão por URL, propaga o erro
        raise

DEBUG_PIDS = {903, 3161, 5176, 5190, 2335}  # Alexei, Lex, MIDOR, MIDORI, Peter

def supa_get_by_url(url: str):
    try:
        data = (
            supabase.table("owbn_characters")
            .select("id,pageid,lastrevid,url")
            .ilike("url", url)
            .limit(1)
            .execute()
            .data or []
        )
        return data[0] if data else None
    except Exception:
        return None

def _canon_url_from_title(title: str) -> str:
    return f"{BASE_URL}/index.php?title={title.replace(' ', '_')}"


# ================== MEDIAWIKI API ==================
def get_all_pages(limit=500) -> List[Dict]:
    out = []
    apcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "aplimit": limit,
            "format": "json",
            "apnamespace": 0,
            "apfilterredir": "nonredirects",  # 👈 NÃO traga redirects
        }
        if apcontinue:
            params["apcontinue"] = apcontinue
        r = requests.get(API_URL, params=params, headers=HEADERS, timeout=40)
        r.raise_for_status()
        j = r.json()
        pages = j.get("query", {}).get("allpages", [])
        for p in pages:
            out.append({"pageid": int(p["pageid"]), "title": p["title"]})
        if "continue" in j:
            apcontinue = j["continue"]["apcontinue"]
        else:
            break
        time.sleep(REQUEST_SLEEP)
    return out


def get_meta_batch(pageids: List[int]) -> Dict[int, Dict]:
    """
    Busca APENAS info.lastrevid em lote (prop=info).
    Isso é suficiente para decidir se mudou.
    """
    if not pageids:
        return {}
    params = {
        "action": "query",
        "prop": "info",
        "format": "json",
        "pageids": "|".join(str(pid) for pid in pageids),
    }
    r = SESSION.get(API_URL, params=params, timeout=40)
    r.raise_for_status()
    j = r.json()
    out: Dict[int, Dict] = {}
    pages = j.get("query", {}).get("pages", {})
    it = pages.values() if isinstance(pages, dict) else pages
    for pdata in it:
        pid = int(pdata.get("pageid"))
        lastrevid = pdata.get("lastrevid")
        out[pid] = {"lastrevid": lastrevid, "revid_ts": None}
    return out

def get_revid_ts_single(pageid: int) -> Optional[str]:
    """
    Busca o timestamp ISO (Z) da revisão atual para 1 página.
    Chamar somente para páginas marcadas como 'changed'.
    """
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions",
        "pageids": str(pageid),   # 1 por vez (rvlimit permitido)
        "rvprop": "ids|timestamp",
        "rvlimit": 1,
    }
    r = SESSION.get(API_URL, params=params, timeout=40)
    r.raise_for_status()
    j = r.json()
    pages = (j.get("query") or {}).get("pages") or []
    if not pages:
        return None
    revs = pages[0].get("revisions") or []
    if not revs:
        return None
    return revs[0].get("timestamp")  # ex: "2024-11-20T20:41:13Z"


# ================== PARSE HTML ==================
def parse_quadrinho(soup: BeautifulSoup) -> Dict:
    table = soup.find("table")
    if not table:
        return {}
    data = {"extra": {}}
    for row in table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        campo = th.get_text(strip=True).lower()
        valor = td.get_text(" ", strip=True)
        if campo == "clan":
            data["clan"] = valor
        elif campo == "position":
            data["position"] = valor
        elif campo == "status":
            data["status"] = valor
        elif campo == "domain":
            data["domain"] = valor
        elif campo == "coterie":
            data["coterie"] = valor
        elif campo == "society":
            data["society"] = valor
        elif campo == "path":
            data["path"] = valor
        elif campo == "player":
            data["player"] = valor
        else:
            data["extra"][campo] = valor
    return data

def fetch_and_build_item(pageid: int, title: str) -> dict | None:
    """
    Baixa o HTML, parseia o quadrinho e monta o dict para salvar.
    Se não houver quadrinho, retorna None (mas o caller grava meta mesmo assim).
    """
    r = SESSION.get(
        f"{BASE_URL}/index.php",
        params={"title": title.replace(" ", "_")},   # deixa o requests encodar (& -> %26)
        allow_redirects=True,
        timeout=40,
    )
    url_req = r.url
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code} for {url_req}")

    soup = BeautifulSoup(r.text, "html.parser")
    info = parse_quadrinho(soup)
    if not info:
        return None

    # HTML footer "last edited" é opcional; mantemos só como display
    lastmod_txt = None
    lastmod_li = soup.find("li", id="footer-info-lastmod")
    if lastmod_li:
        t = lastmod_li.get_text(strip=True)
        try:
            t2 = t.replace("This page was last edited on ", "")
            t2 = t2.replace(".", "").replace("at ", "")
            lastmod_txt = t2
        except Exception:
            lastmod_txt = t

    data = {
        "pageid": pageid,
        "title": title,
        "url": r.url,
        "lastmod": lastmod_txt,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **info,
    }

    concat = (
        f"{data.get('title','')}{data.get('url','')}{data.get('clan','')}"
        f"{data.get('position','')}{data.get('status','')}{data.get('domain','')}"
        f"{data.get('coterie','')}{data.get('society','')}{data.get('path','')}"
        f"{data.get('player','')}{data.get('lastmod','')}{data.get('extra',{})}"
    )
    data["hash_conteudo"] = gerar_hash(concat)
    return data


# ================== MAIN ==================
def main():
    start_ts = datetime.utcnow().isoformat() + "Z"

    all_pages = get_all_pages()
    print(f"📦 Total de páginas (NS0): {len(all_pages)}")

    # meta (lastrevid) de todas as páginas (rápido)
    meta_cache: Dict[int, Dict] = {}
    for batch in chunked(all_pages, BATCH_SIZE_META):
        pids = [p["pageid"] for p in batch]
        try:
            meta_cache.update(get_meta_batch(pids))
        except Exception as e:
            print(f"⚠️ Erro buscando meta (lote {len(pids)}): {e}")
        time.sleep(REQUEST_SLEEP)

    existing = supa_get_existing_meta([p["pageid"] for p in all_pages])


    print("🔍 Diagnóstico dirigido (5 recorrentes)")
    for p in all_pages:
        pid, title = p["pageid"], p["title"]
        if pid not in DEBUG_PIDS:
            continue
        api_last = (meta_cache.get(pid) or {}).get("lastrevid")
        db_row   = existing.get(pid) or {}
        db_last  = db_row.get("lastrevid")
        url_guess = _canon_url_from_title(title)
        by_url   = supa_get_by_url(url_guess) or {}
        url_last = by_url.get("lastrevid")
        print(f" • pid={pid:<5} title={title}")
        print(f"    API.lastrevid={api_last} (type={type(api_last).__name__})")
        print(f"    DB[lastrevid by pageid]={db_last} (type={type(db_last).__name__}) present_in_DB={'yes' if pid in existing else 'no'}")
        print(f"    DB[lastrevid by URL   ]={url_last} url={by_url.get('url') or url_guess}")


    if DEBUG_LOG:
        db_missing = [pid for pid in [p["pageid"] for p in all_pages] if pid not in existing]
        null_in_db = sum(1 for v in existing.values() if v.get("lastrevid") in (None, ""))
        null_in_api = sum(1 for v in meta_cache.values() if v.get("lastrevid") in (None, ""))
        print(
            f"📊 Debug lastrevid — existentes no DB: {len(existing)} | "
            f"sem lastrevid no DB: {null_in_db} | sem lastrevid na API: {null_in_api} | "
            f"sem match de pageid no DB: {len(db_missing)}"
        )

    changed = []
    unchanged = 0

    for p in all_pages:
        pid = p["pageid"]
        m = meta_cache.get(pid) or {}
        new_lastrevid = _to_int_or_none(m.get("lastrevid"))

        # 1) tenta por pageid
        old_lastrevid = _to_int_or_none((existing.get(pid) or {}).get("lastrevid"))

        # 2) fallback por URL se não achou via pageid
        if old_lastrevid is None:
            url_guess = f"{BASE_URL}/index.php?title={p['title'].replace(' ', '_')}"
            by_url = supa_get_by_url(url_guess)
            if by_url:
                old_lastrevid = _to_int_or_none(by_url.get("lastrevid"))

        if new_lastrevid is not None and old_lastrevid is not None and new_lastrevid == old_lastrevid:
            unchanged += 1
        else:
            changed.append(p)


    print(f"🔎 A atualizar: {len(changed)} | sem mudança: {unchanged}")

    ok, errs = 0, 0
    for i, p in enumerate(changed, start=1):
        pid, title = p["pageid"], p["title"]
        print(f"[{i}/{len(changed)}] ➡️ {title}")
        try:
            item = fetch_and_build_item(pid, title)

            # sempre grava meta para “marcar” a revisão atual
            m = meta_cache.get(pid, {}) or {}
            if item is None:
                item = {
                    "pageid": pid,
                    "title": title,
                    "url": f"{BASE_URL}/index.php?title={title.replace(' ', '_')}",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }

            if m.get("lastrevid"):
                item["lastrevid"] = m["lastrevid"]

            if FETCH_REVID_TS_FOR_CHANGED:
                try:
                    ts = get_revid_ts_single(pid)
                    if ts:
                        item["revid_ts"] = datetime.fromisoformat(ts.replace("Z", "+00:00")).isoformat()
                    else:
                        item["revid_ts"] = None
                except Exception:
                    item["revid_ts"] = None

            salvar_personagem(item)
            ok += 1
            time.sleep(REQUEST_SLEEP)
        except Exception as e:
            print(f"⚠️ Erro processando {title}: {e}")
            errs += 1

    print(f"✅ Concluído. Atualizados: {ok} | Sem mudança: {unchanged} | Erros: {errs}")
    print(f"[OWBN] ok={ok} unchanged={unchanged} err={errs} start={start_ts} end={datetime.utcnow().isoformat()}Z")


if __name__ == "__main__":
    main()
