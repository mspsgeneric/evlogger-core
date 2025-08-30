# ver_wiki.py
from __future__ import annotations
import os
from typing import List, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from supabase import create_client

# ========= Supabase =========
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("❌ Missing SUPABASE_URL / SUPABASE_KEY in environment")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE = "owbn_characters_public"  # view recomendada

# ========= Helpers =========
FIELDS = [
    "pageid", "title", "url", "lastmod", "lastrevid", "revid_ts",
    "clan", "position", "status", "domain", "coterie", "society", "path", "player", "extra"
]

def _fmt(val: Optional[str]) -> str:
    # Só trata null/vazio => "-"
    if val is None:
        return "-"
    v = str(val).strip()
    return "-" if not v else v

def _row_to_embed(row: Dict) -> discord.Embed:
    # monta cada linha "Campo: valor"
    linhas = []
    linhas.append(f"Clan: { _fmt(row.get('clan')) }")
    linhas.append(f"Position: { _fmt(row.get('position')) }")
    linhas.append(f"Status: { _fmt(row.get('status')) }")
    linhas.append(f"Domain: { _fmt(row.get('domain')) }")
    linhas.append(f"Coterie: { _fmt(row.get('coterie')) }")
    linhas.append(f"Society: { _fmt(row.get('society')) }")
    linhas.append(f"Path: { _fmt(row.get('path')) }")
    linhas.append(f"Player: { _fmt(row.get('player')) }")

    desc = "\n".join(linhas)

    e = discord.Embed(
        title=row.get("title") or "-",
        url=row.get("url"),
        description=desc,
        color=discord.Color.blurple()
    )
    if row.get("lastmod"):
        e.set_footer(text=f"Last edited: {row['lastmod']}")
    return e



def _dedup_keep_order(rows: List[Dict], key="title") -> List[Dict]:
    seen = set()
    out = []
    for r in rows:
        k = r.get(key)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out

def _select_fields(q):
    # pequeno helper porque o client do supabase precisa do .select string
    return q.select(",".join(FIELDS))

def search_candidates(term: str, limit: int = 10) -> List[Dict]:
    """
    Estratégia simples e eficiente no Supabase:
      1) match exato (case-insensitive)
      2) prefixo
      3) substring
    Junta e de-duplica preservando ordem.
    """
    term = term.strip()
    results: List[Dict] = []

    # 1) match exato (ILIKE 'term')
    if term:
        r1 = _select_fields(supabase.table(TABLE)).ilike("title", term).limit(limit).execute().data or []
    else:
        r1 = []

    # 2) prefixo (ILIKE 'term%')
    r2 = _select_fields(supabase.table(TABLE)).ilike("title", f"{term}%").limit(limit).execute().data or []

    # 3) substring (ILIKE '%term%')
    r3 = _select_fields(supabase.table(TABLE)).ilike("title", f"%{term}%").limit(limit).execute().data or []

    combined = r1 + r2 + r3
    combined = _dedup_keep_order(combined, key="title")
    return combined[:limit]

def fetch_by_title_exact(title: str) -> Optional[Dict]:
    """Busca 1 registro por match exato de título (case-insensitive)."""
    data = _select_fields(
        supabase.table(TABLE)
    ).ilike("title", title).limit(1).execute().data or []
    return data[0] if data else None

# ========= UI (Select) =========
class WikiSelect(discord.ui.Select):
    def __init__(self, candidates: List[Dict]):
        options = [
            discord.SelectOption(
                label=(c.get("title") or "-")[:100],
                description=(c.get("clan") or "-")[:100],
                value=c.get("title") or ""
            )
            for c in candidates[:25]  # limite do Discord
        ]
        super().__init__(placeholder="Selecione o personagem...", min_values=1, max_values=1, options=options)
        self._candidates = {c["title"]: c for c in candidates if c.get("title")}

    async def callback(self, interaction: discord.Interaction):
        chosen_title = self.values[0]
        row = self._candidates.get(chosen_title)
        # fallback: busca exata no banco se não estiver no cache
        if row is None:
            row = fetch_by_title_exact(chosen_title)
        if row is None:
            await interaction.response.edit_message(content="Não encontrei esse registro. Tente novamente.", view=None)
            return
        embed = _row_to_embed(row)
        await interaction.response.edit_message(content=None, embed=embed, view=None)

class WikiView(discord.ui.View):
    def __init__(self, candidates: List[Dict], *, timeout: int | None = 60):
        super().__init__(timeout=timeout)
        self.add_item(WikiSelect(candidates))






# ========= Command =========
class WikiCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="wiki", description="Consulta um personagem na OWBN Wiki e exibe o quadrinho.")
    @app_commands.describe(nome="Nome do personagem (use o autocomplete)")
    async def wiki(self, interaction: discord.Interaction, nome: str):
        termo = (nome or "").strip()
        await interaction.response.defer(thinking=True, ephemeral=True)


        candidates = search_candidates(termo, limit=10)
        if not candidates:
            await interaction.followup.send("Nada encontrado. Tente outro nome (ex.: parte do primeiro e último).", ephemeral=True)
            return

        # 1 resultado: mostra direto
        if len(candidates) == 1:
            embed = _row_to_embed(candidates[0])
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 4+ caracteres: já usa dropdown também
        if len(termo) >= 4:
            view = WikiView(candidates)
            await interaction.followup.send(
                content=f"Encontrei {len(candidates)} resultados para **{nome}**. Selecione abaixo:",
                view=view
            )
            return




        # termo curto (<5): usa Select (dropdown) para ajudar a refinar
        view = WikiView(candidates)
        await interaction.followup.send(
            content=f"Encontrei {len(candidates)} resultados para **{nome}**. Selecione abaixo:",
            view=view
        )


    @wiki.autocomplete("nome")
    async def wiki_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            raw = current or ""           # conta espaço
            if len(raw) < 4:
                return []                 # nada para < 4 chars

            term = raw.strip()
            if not term:
                return []

            # queremos no máx 4 sugestões
            need = 4
            cands: List[Dict] = []

            # 1) match exato
            if term:
                r1 = _select_fields(supabase.table(TABLE)) \
                    .ilike("title", term).limit(need).execute().data or []
                cands.extend(r1)
                need = 4 - len(cands)

            # 2) prefixo
            if need > 0:
                r2 = _select_fields(supabase.table(TABLE)) \
                    .ilike("title", f"{term}%").limit(need).execute().data or []
                cands.extend(r2)
                need = 4 - len(cands)

            # 3) substring (fallback)
            if need > 0:
                r3 = _select_fields(supabase.table(TABLE)) \
                    .ilike("title", f"%{term}%").limit(need).execute().data or []
                cands.extend(r3)

            # de-dup por título e corta em 4
            cands = _dedup_keep_order(cands, key="title")[:4]

            # rótulo seguro
            def _label(t: str) -> str:
                t = (t or "").replace("\n", " ").replace("\r", " ").strip()
                return t[:100] or "-"

            return [
                app_commands.Choice(name=_label(c["title"]), value=c["title"])
                for c in cands if c.get("title")
            ]
        except Exception:
            return []


async def setup(bot: commands.Bot):
    await bot.add_cog(WikiCog(bot))
