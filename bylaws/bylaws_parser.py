# bylaws_parser.py
import csv
import re
from bs4 import BeautifulSoup

# ---------- Normalização de texto ----------
def normalize(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u00ad", "")           # soft hyphen
    s = s.replace("\u00a0", " ")          # NBSP -> espaço
    s = s.replace("\u2010", "-")          # hyphen
    s = s.replace("\u2011", "-")          # non-breaking hyphen
    s = s.replace("\u2012", "-")          # figure dash
    s = s.replace("\u2013", "-")          # en dash
    s = s.replace("\u2014", "-")          # em dash
    s = s.replace("\u2015", "-")          # horizontal bar
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def direct_text(li) -> str:
    """Texto direto do <li> (sem descer em sub-<li>)."""
    return "".join(li.find_all(string=True, recursive=False)).strip()

# ---------- Detectores e helpers ----------
# Atenção: para detectar linhas com rótulos, exigimos dois pontos após o rótulo.
LABEL_COLON = re.compile(r"\b(PC|NPC|Coordinator|Coord)\s*:", re.I)
SEG_SPLIT   = re.compile(r"\s*-\s*")
VERBY       = re.compile(r"\b(may|must|can|should|shall|allowed|prohibited|require|requires|cannot|won't|will)\b", re.I)
LORE_FLAG   = re.compile(r"\b(lore|lores|guild lore|clan lores|vampire clan lores)\b", re.I)
CLAN_LORE_FLAG = re.compile(r"\b(vampire\s+clan\s+lores?|clan\s+lores?)\b", re.I)

# Itens que não devem virar "Lore" por terem cara de sentença/regra
SENTENCEY = re.compile(
    r'\b(PC|NPC|Coordinator|Coordinators?)\b|["“”()]+|(?:\bwith\b|\bcom\b)|^\s*The\b',
    re.I
)

# Frases descritivas muito longas
LONG_SENTENCE_RE = re.compile(r"[.!?]")

def should_prefix_lore(text: str) -> bool:
    return not re.search(r"\blore\b", text, re.I)

def is_explanatory_child(text: str) -> bool:
    """Heurística para pular filhos que são frases explicativas (curto-circuito existente)."""
    t = normalize(text)
    if not t:
        return True
    if re.search(r"[.!?]$", t):
        return True
    if VERBY.search(t):
        return True
    if len(t) >= 120:
        return True
    if t.count(",") >= 2:
        return True
    return False

def is_long_sentence(text: str) -> bool:
    """Filtra textos que parecem frases completas/descritivas demais (pais e filhos)."""
    t = normalize(text)
    if not t:
        return False
    if len(t) > 140:
        return True
    if LONG_SENTENCE_RE.search(t) and len(t.split()) > 15:
        return True
    return False

def is_lore_candidate(text: str, *, clan_lore: bool = False) -> bool:
    """
    Verdadeiro se o texto parece 'nome' curto apto a receber prefixo Lore.
    - Sempre barra: with/com, PC/NPC/Coord, aspas/parênteses, 'The ...', verbos modais, muito longo.
    - Em Clan Lores: aceita nomes curtos com vírgula/níveis (ex.: 'Brujah 4, Non-Brujah').
    """
    t = normalize(text)
    if not t:
        return False
    if len(t.split()) > 12:
        return False
    if VERBY.search(t):
        return False
    if re.search(r'\b(with|com)\b', t, re.I):
        return False
    if re.search(r'["“”()]+', t):
        return False
    if not clan_lore:
        if ',' in t or t.strip().lower().startswith('the '):
            return False
    return True

def is_header_without_labels(text: str) -> bool:
    """
    Cabeçalho que NÃO é 'linha de regras'.
    Considera 'linha de regras' somente se houver PC/NPC/Coordinator/Coord seguidos de ':'.
    """
    if not text:
        return False
    if LABEL_COLON.search(text):
        return False
    return True

def is_lore_context(li_tag):
    """
    Retorna (tem_lore, em_clan_lore) se houver 'Lore' em até DOIS <li> ancestrais acima,
    sem atravessar um cabeçalho que já tenha PC/NPC/Coord com ':'.
    """
    hops = 0
    for p in li_tag.parents:
        if getattr(p, "name", None) != "li":
            continue
        head = normalize(direct_text(p))
        if not is_header_without_labels(head):
            return (False, False)  # bloqueia propagação por cabeçalho de regras
        low = head.lower()
        if LORE_FLAG.search(low):
            return (True, bool(CLAN_LORE_FLAG.search(low)))
        hops += 1
        if hops >= 2:  # até o “avô”
            break
    return (False, False)

# --- Âncora para iniciar o parsing (ignora tudo acima de GENERAL CONTROLLED ITEMS) ---
ANCHOR_RE = re.compile(r'^\s*general\s+controlled\s+items\s*$', re.I)

def find_anchor_li(root):
    """Retorna o <li> cujo texto direto é 'GENERAL CONTROLLED ITEMS' (case-insensitive)."""
    for li in root.find_all("li"):
        if ANCHOR_RE.search(normalize(direct_text(li))):
            return li
    return None

# ---------- Normalizadores de segmentos ----------
def strip_pc(seg: str) -> str:
    return re.sub(r"^PC(?:\s+Approval)?\s*:?\s*", "", seg, flags=re.I).strip()

def strip_npc(seg: str) -> str:
    return re.sub(r"^NPC(?:\s+Approval)?\s*:?\s*", "", seg, flags=re.I).strip()

def strip_coord(seg: str) -> str:
    return re.sub(r"^(?:Coordinator|Coord)\s*:?\s*", "", seg, flags=re.I).strip()

CTRL_RE  = re.compile(r"\bCoordinator\s+Controlled\b", re.I)

# Coord herdado do cabeçalho ancestral "X Coordinator"
COORD_HEAD_RE = re.compile(r"(.+?)\s+Coordinator\b", re.I)

def coord_from_ancestors(li_tag) -> str or None:
    """Se algum <li> ancestral tiver 'X Coordinator', retorna 'X' normalizado."""
    for anc in li_tag.parents:
        if getattr(anc, "name", None) != "li":
            continue
        head = normalize(direct_text(anc))
        m = COORD_HEAD_RE.search(head)
        if m:
            return m.group(1).strip(" -:")
    return None

def extract_rules_from_head(raw_head: str):
    """
    Extrai (categoria, pc, npc, coord) do texto cabeçalho do <li> pai.
    Normaliza -> acha o 1º marcador -> segmenta por '-' -> lê só segmentos que começam
    com PC/NPC/Coordinator (com ':').
    """
    head = normalize(raw_head)
    m = LABEL_COLON.search(head)
    if not m:
        return None

    categoria = head[:m.start()].strip(" -:")
    tail = head[m.start():]

    pc = npc = coord = ""

    segments = SEG_SPLIT.split(tail)
    if segments:
        m0 = LABEL_COLON.search(segments[0])
        if m0:
            segments[0] = segments[0][m0.start():].strip()

    for seg in segments:
        if not seg:
            continue
        seg_norm = normalize(seg)
        low = seg_norm.lower()
        if low.startswith("pc"):
            pc = strip_pc(seg_norm)
        elif low.startswith("npc"):
            npc = strip_npc(seg_norm)
        elif low.startswith("coordinator") or low.startswith("coord"):
            coord = strip_coord(seg_norm)

    if CTRL_RE.search(head):
        if not pc:
            pc = "Coordinator Controlled"
        if not npc:
            npc = "Coordinator Controlled"

    return categoria, pc.strip(" -:"), npc.strip(" -:"), coord.strip(" -:")

# ---------- Processamento recursivo de <li> ----------
def collect_from_li(parent_li, rows, seen):
    """
    Processa um <li> que tenha marcadores (PC/NPC/Coordinator), gerando linhas:
    - Registra o próprio pai como item (categoria) — desde que não seja frase longa.
    - Se tiver sublista: filhos simples viram 'item' herdando regras do pai;
      filhos que TAMBÉM têm marcadores são processados recursivamente (novo bloco).
    """
    # deduplicação: não reprocessa o mesmo <li> com rótulos
    key = id(parent_li)
    if key in seen:
        return
    seen.add(key)

    head_raw = direct_text(parent_li)
    if not head_raw or not LABEL_COLON.search(head_raw):
        return

    extracted = extract_rules_from_head(head_raw)
    if not extracted:
        return
    categoria, pc, npc, coord = extracted

    if not coord:
        inherited = coord_from_ancestors(parent_li)
        if inherited:
            coord = inherited

    lore_ctx, in_clan_lore = is_lore_context(parent_li)

    # Procura sublista (ol/ul) direta ou em wrapper simples
    inner_list = (parent_li.find(["ol", "ul"], recursive=False)
                  or parent_li.find(["ol", "ul"], recursive=True))

    # --- Registra o próprio pai como item (categoria), se não for frase longa ---
    parent_item = categoria
    if lore_ctx and should_prefix_lore(parent_item) and is_lore_candidate(parent_item, clan_lore=in_clan_lore):
        parent_item = f"Lore {parent_item}"
    if parent_item and not is_long_sentence(parent_item):
        rows.append([parent_item, pc, npc, coord, categoria])

    if inner_list:
        # Examina filhos de primeiro nível
        for child_li in inner_list.find_all("li", recursive=False):
            child_head = direct_text(child_li)
            child_head_norm = normalize(child_head)

            if LABEL_COLON.search(child_head_norm):
                # Filho com marcadores -> processa recursivamente como novo bloco
                collect_from_li(child_li, rows, seen)
                continue

            # Filho sem marcadores: vira item simples, herdando regras do pai
            item_text = child_li.get_text(" ", strip=True)
            item_text = normalize(item_text).strip(" -:")
            if not item_text:
                continue
            if is_explanatory_child(item_text):
                continue
            if is_long_sentence(item_text):
                continue

            final_item = item_text
            if lore_ctx and should_prefix_lore(final_item) and is_lore_candidate(final_item, clan_lore=in_clan_lore):
                final_item = f"Lore {final_item}"
            rows.append([final_item, pc, npc, coord, categoria])

# ---------- Parser principal ----------
def parse_html(in_path: str = "bylaws_character.html", out_csv: str = "bylaws_output.csv"):
    with open(in_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    # Foca no corpo; se não achar, usa documento inteiro
    content = soup.select_one("div.node__content div.field--name-body div.field__item") or soup

    rows = []
    seen = set()  # deduplicação de <li> com rótulos

    # Encontra a âncora "GENERAL CONTROLLED ITEMS"
    anchor_li = find_anchor_li(content)

    def li_iterator():
        """
        Itera todos os <li> a partir da âncora (incluindo ela), em ordem de documento.
        Se não houver âncora, cai no comportamento antigo (todo o conteúdo).
        """
        if anchor_li:
            yield anchor_li
            for el in anchor_li.next_elements:
                if getattr(el, "name", None) == "li":
                    yield el
        else:
            for li in content.find_all("li"):
                yield li

    # Percorre a partir da âncora
    for li in li_iterator():
        head = normalize(direct_text(li))
        if LABEL_COLON.search(head):
            if id(li) in seen:
                continue
            collect_from_li(li, rows, seen)

    # Grava CSV simples
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "pc", "npc", "coord", "categoria"])
        w.writerows(rows)

    print(f"✅ Arquivo gerado: {out_csv} com {len(rows)} linhas")

if __name__ == "__main__":
    parse_html("bylaws_character.html", "bylaws_output.csv")
