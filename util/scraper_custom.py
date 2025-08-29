# util/scraper_custom.py
import os
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://www.owbn.net"
CUSTOM_CONTENT_URL = f"{BASE_URL}/resources/custom-content"

# ---------- HTTP session (User-Agent + timeout) ----------
session = requests.Session()
session.headers.update({
    "User-Agent": "OWBN-Custom-Scraper (contact: your-email@example.com)"
})
REQ_TIMEOUT = 20


# ---------- Helpers ----------
def gerar_hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()

def make_requisitos_str(requisitos) -> str:
    """Converte a lista de requisitos em texto simples para busca (ex.: 'auspex 4, presence 3')."""
    if not requisitos:
        return ""
    try:
        parts = []
        for x in requisitos:
            if isinstance(x, dict):
                disc = (x.get("disciplina") or "").strip()
                lvl = (x.get("nivel") or "").strip()
                if disc or lvl:
                    parts.append(f"{disc} {lvl}".strip())
        return ", ".join(parts).lower()
    except Exception:
        return ""

def get_last_success_date():
    """Busca a última data processada no Supabase."""
    # Tabela foi criada com 1 linha; pegamos a primeira
    resp = supabase.table("scraper_status").select("id,last_success_date").limit(1).execute()
    if resp.data:
        return datetime.strptime(resp.data[0]["last_success_date"], "%Y-%m-%d").date()
    return datetime(2024, 1, 1).date()  # fallback

def update_last_success_date(nova_data):
    """Atualiza o checkpoint (assumindo id=1)."""
    supabase.table("scraper_status").update(
        {"last_success_date": nova_data.strftime("%Y-%m-%d")}
    ).eq("id", 1).execute()

def salvar_item(item):
    """Upsert pelo campo único URL."""
    supabase.table("owbn_custom_content").upsert(item, on_conflict="url").execute()

def extrair_requisitos(container):
    requisitos = []
    table = container.find("table", class_="views-table")
    if table:
        rows = table.find_all("tr")[1:]  # pula cabeçalho
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) == 2:
                requisitos.append({"disciplina": cols[0], "nivel": cols[1]})
    return requisitos

def processar_item(item_div):
    nome = item_div.find("div", class_="views-field-field-vine-cc-name").get_text(strip=True)
    url_rel = item_div.find("a")["href"]
    url = BASE_URL + url_rel

    categoria = item_div.find("div", class_="views-field-field-vine-cc-category").get_text(strip=True).replace("Custom Content Category:", "").strip()

    origem_div = item_div.find("div", class_="views-field-php")
    origem = origem_div.get_text(strip=True) if origem_div else None

    data_archival_div = item_div.find("div", class_="views-field-field-vine-cc-date-archival")
    data_archival_txt = data_archival_div.get_text(strip=True).replace("Date of Archival:", "").strip() if data_archival_div else None
    data_archival = None
    if data_archival_txt:
        try:
            data_archival = datetime.strptime(data_archival_txt, "%d-%b-%Y").date()
        except Exception:
            data_archival = None

    descricao_div = item_div.find("div", class_="views-field-field-vine-cc-met-mechanics")
    descricao = descricao_div.get_text(" ", strip=True) if descricao_div else None

    requisitos = []
    req_div = item_div.find("div", class_="views-field-field-cc-custom-disc-req")
    if req_div:
        requisitos = extrair_requisitos(req_div)

    requisitos_str = make_requisitos_str(requisitos)

    conteudo_concat = f"{nome}{descricao}{categoria}{origem}{data_archival}{requisitos}"
    hash_conteudo = gerar_hash(conteudo_concat)

    return {
        "nome": nome,
        "descricao": descricao,
        "categoria": categoria,
        "origem": origem,
        "data_archival": data_archival.isoformat() if data_archival else None,  # string "YYYY-MM-DD" (compatível com DATE)
        "url": url,
        "requisitos": requisitos,               # JSONB
        "requisitos_str": requisitos_str,       # TEXT (novo)
        "hash_conteudo": hash_conteudo,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
    }

def processar_pagina(url, data_inicio, data_fim):
    try:
        resp = session.get(url, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"   ⚠️ Falha ao baixar {url}: {e!r}")
        return 0, True

    soup = BeautifulSoup(resp.text, "html.parser")

    itens = soup.find_all("div", class_="views-row")
    novos = 0
    for item_div in itens:
        item = processar_item(item_div)

        if not item["data_archival"]:
            continue

        data_item = datetime.strptime(item["data_archival"], "%Y-%m-%d").date()

        if data_inicio <= data_item <= data_fim:
            salvar_item(item)
            novos += 1
        elif data_item < data_inicio:
            # todos os próximos tendem a ser mais antigos → pode parar
            return novos, False

    # paginação
    next_link = soup.find("a", title="Go to next page")
    if next_link:
        next_url = BASE_URL + next_link["href"]
        # pequena pausa educada
        time.sleep(0.5)
        novos2, continuar = processar_pagina(next_url, data_inicio, data_fim)
        return novos + novos2, continuar

    return novos, True

def listar_categorias():
    resp = session.get(CUSTOM_CONTENT_URL, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    for a in soup.select("div.view-content a"):
        href = a.get("href")
        if href and href.startswith("/resources/custom-content/"):
            links.append(BASE_URL + href)
    return list(set(links))


# ---------- MAIN ----------
def main():
    last_date = get_last_success_date()
    hoje = datetime.utcnow().date()
    data_inicio = last_date + timedelta(days=1)
    data_fim = hoje

    print(f"🔍 Atualizando de {data_inicio} até {data_fim}")

    if data_inicio > data_fim:
        print("✅ Nenhuma atualização necessária.")
        return

    categorias = listar_categorias()
    total_novos = 0

    for cat_url in categorias:
        print(f"➡️ Processando {cat_url}")
        novos, _ = processar_pagina(cat_url, data_inicio, data_fim)
        total_novos += novos

    print(f"✅ Incremental concluído. {total_novos} itens novos/atualizados.")
    update_last_success_date(data_fim)

if __name__ == "__main__":
    main()
