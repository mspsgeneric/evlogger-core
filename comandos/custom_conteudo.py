from __future__ import annotations
import re
import discord
from discord import app_commands, Interaction
from discord.ext import commands
from typing import List

from util.db_supabase import get_supabase
supabase = get_supabase()

EMBED_COLOR = discord.Color.blue()
PAGE_SIZE = 5

# coluna de busca real por cada opção do slash
SEARCH_COLUMN_MAP = {
    "nome": "nome",
    "descricao": "descricao",
    "requisitos": "requisitos_str",  # JSONB foi normalizado pra string no scraper
}

# ----------------- Utils -----------------
def _truncate(txt: str | None, limit: int) -> str:
    if not txt:
        return ""
    return txt if len(txt) <= limit else txt[: limit - 1] + "…"

def _format_requisitos(reqs) -> str:
    """
    reqs pode vir como lista de dicts [{'disciplina': 'Auspex','nivel':'4'}, ...]
    ou, se algo vier torto, string. Trato ambos.
    """
    if not reqs:
        return "-"
    if isinstance(reqs, str):
        return _truncate(reqs, 300)
    try:
        parts = [f"{x.get('disciplina','?')} {x.get('nivel','?')}" for x in reqs if isinstance(x, dict)]
        s = ", ".join(parts)
        return _truncate(s, 300) if s else "-"
    except Exception:
        return "-"

def _split_long_text(txt: str, max_chunk: int = 3500) -> List[str]:
    """
    Divide texto longo em pedaços <= max_chunk preservando quebras de linha quando possível.
    """
    if not txt:
        return [""]
    out, buf = [], ""
    for line in txt.splitlines(keepends=True):
        if len(buf) + len(line) > max_chunk:
            out.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        out.append(buf)
    # fallback bruto se ainda estourar por linhas enormes
    final = []
    for chunk in out:
        while len(chunk) > max_chunk:
            final.append(chunk[:max_chunk])
            chunk = chunk[max_chunk:]
        final.append(chunk)
    return final or [""]

def _col_text(row: dict, col: str) -> str:
    """Extrai texto da coluna para aplicar regex no pós-filtro."""
    val = row.get(col)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return str(val)

# ----------------- Embeds -----------------
def build_short_embed(r: dict, campo: str, termo: str) -> discord.Embed:
    nome = r.get("nome") or "(sem nome)"
    value_parts = []
    if r.get("categoria"):
        value_parts.append(f"**Categoria:** {r['categoria']}")
    if r.get("origem"):
        value_parts.append(f"**Origem:** {r['origem']}")
    reqs_fmt = _format_requisitos(r.get("requisitos"))
    if reqs_fmt != "-":
        value_parts.append(f"**Requisitos:** {reqs_fmt}")
    if r.get("data_archival"):
        value_parts.append(f"**Data:** {r['data_archival']}")

    # 300 p/ evitar extrapolar 4096 quando somado às outras linhas
    desc = (r.get("descricao") or "").strip()
    if desc:
        value_parts.append(f"**Descrição:** {_truncate(desc, 300)}")

    embed = discord.Embed(
        title=f"✔️ {nome}",
        description="\n".join(value_parts) or "-",
        color=EMBED_COLOR,
        url=r.get("url") or None,
    )
    embed.set_footer(text=f"Busca em {campo}: {termo}")
    return embed

def build_full_embed(r: dict, chunk: str | None = None, part_idx: int | None = None, total_parts: int | None = None) -> discord.Embed:
    nome = r.get("nome") or "(sem nome)"
    head = []
    if r.get("categoria"):
        head.append(f"**Categoria:** {r['categoria']}")
    if r.get("origem"):
        head.append(f"**Origem:** {r['origem']}")
    reqs_fmt = _format_requisitos(r.get("requisitos"))
    if reqs_fmt != "-":
        head.append(f"**Requisitos:** {reqs_fmt}")
    if r.get("data_archival"):
        head.append(f"**Data:** {r['data_archival']}")

    if chunk is None:
        chunk = (r.get("descricao") or "").strip()

    parts_note = f" (parte {part_idx}/{total_parts})" if part_idx and total_parts else ""
    body = "\n".join(head)
    if body:
        body += "\n\n"

    # garantir <= 4096
    body += f"**Descrição completa{parts_note}:**\n{_truncate(chunk, 3800)}"

    embed = discord.Embed(
        title=f"📖 {nome}",
        description=body or "-",
        color=EMBED_COLOR,
        url=r.get("url") or None,
    )
    return embed

# ----------------- Views -----------------
class ItemView(discord.ui.View):
    def __init__(self, item: dict, user_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.item = item
        self.user_id = user_id

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Você não pode usar este botão.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ver mais", style=discord.ButtonStyle.primary)
    async def ver_mais(self, interaction: Interaction, button: discord.ui.Button):
        full = (self.item.get("descricao") or "").strip()
        chunks = _split_long_text(full, max_chunk=3500)
        # primeira resposta da interação do botão
        first_embed = build_full_embed(
            self.item,
            chunk=chunks[0],
            part_idx=1 if len(chunks) > 1 else None,
            total_parts=len(chunks) if len(chunks) > 1 else None,
        )
        await interaction.response.send_message(embed=first_embed, ephemeral=True)
        # demais partes (se houver)
        for i, c in enumerate(chunks[1:], start=2):
            emb = build_full_embed(self.item, chunk=c, part_idx=i, total_parts=len(chunks))
            await interaction.followup.send(embed=emb, ephemeral=True)

class PageController(discord.ui.View):
    def __init__(self, campo: str, termo: str, matches: List[dict], page_size: int, user_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.campo = campo
        self.termo = termo
        self.matches = matches
        self.page_size = page_size
        self.user_id = user_id
        self.page = 0
        self.total = len(matches)
        self.total_pages = max(1, (self.total + page_size - 1) // page_size)

    def slice(self):
        a = self.page * self.page_size
        b = min(a + self.page_size, self.total)
        return self.matches[a:b]

    def _update_buttons_state(self):
        # habilita/desabilita conforme a página atual
        if hasattr(self, "prev"):
            self.prev.disabled = (self.page == 0)
        if hasattr(self, "next"):
            self.next.disabled = (self.page >= self.total_pages - 1)

    async def render_page(self, interaction: Interaction):
        """
        - Envia os cards da página atual (ephemeral).
        - Se houver só 1 página, NÃO anexa view (sem botões).
        - Se houver mais de 1, anexa a view e ajusta os estados dos botões.
        """
        items = self.slice()
        responded = interaction.response.is_done()

        # cards
        for idx, item in enumerate(items):
            embed = build_short_embed(item, self.campo, self.termo)
            view = ItemView(item, self.user_id)
            if not responded and idx == 0:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                responded = True
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        # navegação (texto)
        nav = f"Página {self.page+1}/{self.total_pages} — {self.total} resultados"

        # se só tem 1 página: não manda a view -> sem botões
        if self.total_pages == 1:
            if responded:
                await interaction.followup.send(content=nav, ephemeral=True)
            else:
                await interaction.response.send_message(content=nav, ephemeral=True)
            return

        # mais de 1 página: manda com a view e atualiza estado dos botões
        self._update_buttons_state()
        if responded:
            await interaction.followup.send(content=nav, view=self, ephemeral=True)
        else:
            await interaction.response.send_message(content=nav, view=self, ephemeral=True)

    @discord.ui.button(label="◀️ Anterior", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await self.render_page(interaction)

    @discord.ui.button(label="Próximo ▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
        await self.render_page(interaction)


# ----------------- Registro do comando -----------------
async def setup(bot: commands.Bot):
    @bot.tree.command(name="custom", description="Consulta poderes custom da OWBN")
    @app_commands.describe(
        campo="Onde pesquisar (nome, descricao, requisitos)",
        termo="Palavra/frase (mín. 4 letras). Ex.: erato blessing",
    )
    @app_commands.choices(campo=[
        app_commands.Choice(name="Nome", value="nome"),
        app_commands.Choice(name="Descrição", value="descricao"),
        app_commands.Choice(name="Requisitos", value="requisitos"),
    ])
    async def custom(interaction: Interaction, campo: app_commands.Choice[str], termo: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        termo = (termo or "").strip()
        if len(termo) < 4:
            return await interaction.followup.send("Forneça pelo menos 4 caracteres.", ephemeral=True)

        try:
            col = SEARCH_COLUMN_MAP.get(campo.value, campo.value)

            # 1) Busca ampla no Supabase
            resp = (
                supabase.table("owbn_custom_content")
                .select("*")
                .ilike(col, f"%{termo}%")
                .order("data_archival", desc=True)
                .execute()
            )
            matches = resp.data or []

            # 2) Pós-filtro em Python:
            #    - se o usuário digitou várias palavras, tratamos como frase exata (na ordem)
            #    - sempre exigimos "word boundaries" pra evitar 'operator' quando busca é 'erato'
            phrase = termo  # frase exata como digitada
            regex = rf"\b{re.escape(phrase)}\b"
            pattern = re.compile(regex, re.IGNORECASE)
            matches = [m for m in matches if pattern.search(_col_text(m, col))]

        except Exception as e:
            return await interaction.followup.send(f"Erro consultando Supabase: {e!r}", ephemeral=True)

        if not matches:
            return await interaction.followup.send(f"Nada encontrado para “{termo}”.", ephemeral=True)

        view = PageController(campo.value, termo, matches, page_size=PAGE_SIZE, user_id=interaction.user.id)
        await view.render_page(interaction)
