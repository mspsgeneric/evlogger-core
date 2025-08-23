# comandos/blc_bylaws.py
import os
import csv
import re
import unicodedata
from typing import List, Dict, Tuple

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# -------- Config via .env / defaults ----------
CSV_PATH = os.getenv("BYLAWS_CSV") or str(Path(__file__).resolve().parents[1] / "bylaws" / "bylaws_output.csv")
LAST_REVISED = (os.getenv("LAST_REVISED") or "").strip()
PAGE_SIZE = int(os.getenv("BLC_PAGE_SIZE") or 5)
EMBED_COLOR = int(os.getenv("BLC_EMBED_COLOR") or "0x8e44ad", 16)
# ---------------------------------------------

# ----------------- Util: normalização -----------------
def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def fold(s: str) -> str:
    s = (s or "").strip()
    s = _strip_accents(s).lower()
    s = re.sub(r"\s+", " ", s)
    return s

# ----------------- Cache do CSV -----------------
_ROWS_CACHE = {"rows": None, "mtime": None}

def _load_rows_from_disk() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "item": (r.get("item") or "").strip(),
                "pc": (r.get("pc") or "").strip(),
                "npc": (r.get("npc") or "").strip(),
                "coord": (r.get("coord") or "").strip(),
                "categoria": (r.get("categoria") or "").strip(),
            })
    return rows

def load_rows() -> List[Dict[str, str]]:
    try:
        mtime = os.path.getmtime(CSV_PATH)
    except FileNotFoundError:
        mtime = None
    if _ROWS_CACHE["rows"] is None or _ROWS_CACHE["mtime"] != mtime:
        _ROWS_CACHE["rows"] = _load_rows_from_disk()
        _ROWS_CACHE["mtime"] = mtime
    return _ROWS_CACHE["rows"]

# ----------------- Parser da query -----------------
_Q_TOKEN = re.compile(r'"([^"]+)"|(\S+)')

def parse_query(q: str):
    """
    Entrada: string do parâmetro 'item' (ex.: 'brujah 4 | kiasyd -ritual pc:approval')
    Suporta:
      - frases: "true brujah"
      - exclusões: -ritual
      - OR: foo|bar  (ou 'foo OR bar')
      - filtros: pc:notify  npc:approval  coord:wraith
    """
    q = (q or "").strip()
    q = re.sub(r"\s+OR\s+", " | ", q, flags=re.I)
    phrases, terms, excludes = [], [], []
    any_terms = []
    filters = {"pc": None, "npc": None, "coord": None}

    for m in _Q_TOKEN.finditer(q):
        token = m.group(1) or m.group(2) or ""
        if not token:
            continue
        if token.startswith("-"):
            tok = token[1:]
            if tok:
                excludes.append(tok)
            continue
        mf = re.match(r"^(pc|npc|coord):(.+)$", token, flags=re.I)
        if mf:
            filters[mf.group(1).lower()] = mf.group(2)
            continue
        if token == "|":
            any_terms.append("|")
            continue
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            phrases.append(token[1:-1])
        elif m.group(1):
            phrases.append(token)
        else:
            terms.append(token)

    # construir grupos OR se houver '|'
    if "|" in any_terms or "|" in terms:
        seq = []
        for m in _Q_TOKEN.finditer(q):
            t = m.group(1) or m.group(2) or ""
            if not t:
                continue
            if t == "|" or re.fullmatch(r"\|+", t):
                seq.append("|")
            elif t.startswith('"') and t.endswith('"') and len(t) >= 2:
                seq.append(("P", t[1:-1]))
            else:
                seq.append(("T", t))
        group, groups = [], []
        for t in seq:
            if t == "|":
                if group:
                    groups.append(group)
                    group = []
            else:
                group.append(t)
        if group:
            groups.append(group)

        any_terms = []
        for g in groups:
            any_group = []
            for kind, val in g:
                if kind == "P":
                    any_group.append(val)
                else:
                    if re.match(r"^(pc|npc|coord):", val, flags=re.I) or val.startswith("-"):
                        continue
                    any_group.append(val)
            if any_group:
                any_terms.append(any_group)
    else:
        any_terms = []

    return {"phrases": phrases, "terms": terms, "any_terms": any_terms, "excludes": excludes, "filters": filters}

# ----------------- Fuzzy leve -----------------
def _lev1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = diff = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1; j += 1
        else:
            diff += 1
            if diff > 1:
                return False
            if la == lb:
                i += 1; j += 1
            else:
                j += 1
    if j < lb or i < la:
        diff += 1
    return diff <= 1

def _tokenize(s: str):
    return re.findall(r"[a-z0-9+]+", fold(s))

# ----------------- Scoring / matching (ITEM-ONLY) -----------------
def _match_score(row: Dict[str, str], qobj) -> Tuple[bool, int, str]:
    """
    Retorna (match?, score, highlight_title).
    Busca e ranking **apenas** em 'item'. Filtros em pc/npc/coord ainda se aplicam.
    """
    item = row["item"]
    fitem = fold(item)

    # filtros
    flt = qobj["filters"]
    if flt["pc"] and fold(flt["pc"]) not in fold(row["pc"]):
        return (False, 0, "")
    if flt["npc"] and fold(flt["npc"]) not in fold(row["npc"]):
        return (False, 0, "")
    if flt["coord"] and fold(flt["coord"]) not in fold(row["coord"]):
        return (False, 0, "")

    # exclusões
    for ex in qobj["excludes"]:
        fex = fold(ex)
        if fex in fitem:
            return (False, 0, "")

    score = 0

    # frases (AND)
    for ph in qobj["phrases"]:
        fph = fold(ph)
        if fph not in fitem:
            return (False, 0, "")
        score += 50

    # termos (AND) com fuzzy leve
    item_tokens = _tokenize(item)
    for t in qobj["terms"]:
        ft = fold(t)
        hit = False
        if ft in fitem:
            hit = True; score += 12
        else:
            if any(tok.startswith(ft) for tok in item_tokens):
                hit = True; score += 9
            elif any(_lev1(ft, tok) for tok in item_tokens):
                hit = True; score += 7
        if not hit:
            return (False, 0, "")

    # any_terms (OR): basta satisfazer um grupo
    if qobj["any_terms"]:
        any_ok = False
        for grp in qobj["any_terms"]:
            grp_ok = False
            for term in grp:
                fterm = fold(term)
                if fterm in fitem:
                    grp_ok = True; break
                if any(tok.startswith(fterm) for tok in item_tokens):
                    grp_ok = True; break
                if any(_lev1(fterm, tok) for tok in item_tokens):
                    grp_ok = True; break
            if grp_ok:
                any_ok = True; score += 7
                break
        if not any_ok:
            return (False, 0, "")

    # leve boost se tiver coord preenchido
    if row["coord"]:
        score += 1

    # highlight
    hl_terms = set(fold(ph) for ph in qobj["phrases"])
    hl_terms.update(fold(t) for t in qobj["terms"])
    for grp in qobj["any_terms"]:
        for t in grp:
            hl_terms.add(fold(t))

    title = _highlight(item, hl_terms) if hl_terms else item
    return (True, score, title)

def _highlight(text: str, fterms: set) -> str:
    if not text:
        return text
    pats = sorted([re.escape(t) for t in fterms if t], key=len, reverse=True)
    if not pats:
        return text
    def repl(m): return f"**{m.group(0)}**"
    result = text
    for p in pats:
        result = re.sub(p, repl, result, flags=re.I)
    return result[:250] + "…" if len(result) > 256 else result

# ----------------- Busca -----------------
def search_rows(item_query: str, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    qobj = parse_query(item_query)
    matches = []
    for r in rows:
        ok, score, title = _match_score(r, qobj)
        if ok:
            rr = dict(r)
            rr["_score"] = score
            rr["_hl_item"] = title
            matches.append(rr)
    matches.sort(key=lambda x: x["_score"], reverse=True)
    return matches

# ----------------- Render -----------------
def _field_value(r: Dict[str, str]) -> str:
    item = (r.get("item") or "").strip()
    categoria = (r.get("categoria") or "").strip()
    show_categoria = categoria and (categoria.lower() != item.lower())

    parts = []
    if show_categoria:
        parts.append(f"**Categoria:** {categoria}\n")
    parts.append(f"**PC:** {r['pc'] or '-'}")
    parts.append(f"**NPC:** {r['npc'] or '-'}")
    parts.append(f"**Coord:** {r['coord'] or '-'}")
    value = "\n".join(parts)
    return (value[:1020] + "…") if len(value) > 1024 else value

def make_embed(item_query: str, matches_slice: List[Dict[str, str]], total_found: int, page_idx: int, total_pages: int) -> discord.Embed:
    desc_lines = []
    if LAST_REVISED:
        desc_lines.append(f"Última revisão: {LAST_REVISED}")
    desc_lines.append("Dicas: use **aspas** (frase), `-termo` (excluir), `pc:notify`, `npc:approval`, `coord:wraith`, `foo|bar` (OR).")
    embed = discord.Embed(
        title=f"📖 Resultados para: {item_query}",
        description="\n".join(desc_lines),
        color=EMBED_COLOR,
    )

    for r in matches_slice:
        name = f"✔️ {r.get('_hl_item') or r['item'] or '(sem nome)'}"
        value = _field_value(r)
        embed.add_field(name=name, value=value, inline=False)

    suf = "resultado" if total_found == 1 else "resultados"
    footer_txt = f"{total_found} {suf}"
    if total_pages > 1:
        footer_txt += f" — página {page_idx+1}/{total_pages}"
    embed.set_footer(text=footer_txt)
    return embed

# ----------------- View / Paginação -----------------
class ResultPaginator(discord.ui.View):
    def __init__(self, item_query: str, matches, page_size: int, user_id: int | None = None, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.item_query = item_query
        self.matches = matches
        self.page_size = page_size
        self.user_id = user_id
        self.page = 0
        self.total = len(matches)
        self.total_pages = max(1, (self.total + page_size - 1) // page_size)
        if self.total_pages == 1:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

    def slice(self):
        a = self.page * self.page_size
        b = min(a + self.page_size, self.total)
        return self.matches[a:b]

    def render_embed(self) -> discord.Embed:
        return make_embed(self.item_query, self.slice(), self.total, self.page, self.total_pages)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message("Você não pode controlar esta paginação.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀️ Anterior", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    @discord.ui.button(label="Próximo ▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
        await interaction.response.edit_message(embed=self.render_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

# ----------------- Registro do comando -----------------
async def setup(bot: commands.Bot):
    @bot.tree.command(name="blc", description="Consulta ao Bylaws Character - EXPERIMENTAL")
    @app_commands.describe(item='Consulta. Ex.: "true brujah" | kiasyd -ritual pc:approval')
    async def blc(interaction: Interaction, item: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        item = (item or "").strip()
        if len(item) < 2:
            return await interaction.followup.send("Forneça pelo menos 2 caracteres.", ephemeral=True)

        try:
            rows = load_rows()
        except Exception as e:
            return await interaction.followup.send(f"Erro lendo CSV em `{CSV_PATH}`: {e!r}", ephemeral=True)

        matches = search_rows(item, rows)
        if not matches:
            return await interaction.followup.send(f"Nada encontrado para “{item}”.", ephemeral=True)

        view = ResultPaginator(item, matches, page_size=PAGE_SIZE, user_id=interaction.user.id)
        await interaction.followup.send(embed=view.render_embed(), view=view, ephemeral=True)
