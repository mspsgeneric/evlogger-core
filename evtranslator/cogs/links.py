from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
from evtranslator.db import link_pair, unlink_pair, unlink_all, list_links, get_link_info
from evtranslator.config import DB_PATH

class LinksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ⬇️ RENOMEADO: /linkar
    @app_commands.command(name="linkar", description="Liga dois canais em PT↔EN (canal_pt ↔ canal_en).")
    @app_commands.describe(canal_pt="Canal em Português", canal_en="Canal em Inglês")
    async def linkar_cmd(
        self,
        inter: discord.Interaction,
        canal_pt: discord.TextChannel,
        canal_en: discord.TextChannel
    ):
        if not inter.user.guild_permissions.manage_guild:  # type: ignore[union-attr]
            return await inter.response.send_message("🚫 Requer permissão: Gerenciar Servidor.", ephemeral=True)

        if canal_pt.id == canal_en.id:
            return await inter.response.send_message("🚫 Escolha **dois canais diferentes**.", ephemeral=True)

        await link_pair(DB_PATH, inter.guild.id, canal_pt.id, canal_en.id)  # type: ignore[arg-type]
        await inter.response.send_message(
            f"🔗 Link criado: {canal_pt.mention} (pt) ⇄ {canal_en.mention} (en)",
            ephemeral=True
        )

    # ⬇️ RENOMEADO: /deslinkar (sem parâmetros; roda no canal atual)
    @app_commands.command(name="deslinkar", description="Remove o link do canal atual com seu par.")
    async def deslinkar_cmd(self, inter: discord.Interaction):
        if not inter.user.guild_permissions.manage_guild:  # type: ignore[union-attr]
            return await inter.response.send_message("🚫 Requer permissão: Gerenciar Servidor.", ephemeral=True)

        current_ch = inter.channel
        if not isinstance(current_ch, discord.TextChannel):
            return await inter.response.send_message("🚫 Use em um canal de texto.", ephemeral=True)

        info = await get_link_info(DB_PATH, inter.guild.id, current_ch.id)
        if not info:
            return await inter.response.send_message("ℹ️ Nenhum link encontrado para este canal.", ephemeral=True)

        target_id, src_lang, tgt_lang = info
        await unlink_pair(DB_PATH, inter.guild.id, current_ch.id, target_id)  # type: ignore[arg-type]

        target_ch = inter.guild.get_channel(target_id)
        if target_ch:
            return await inter.response.send_message(
                f"❌ Link removido: {current_ch.mention} ({src_lang}) ⇄ {target_ch.mention} ({tgt_lang})",
                ephemeral=True
            )
        else:
            return await inter.response.send_message("❌ Link removido.", ephemeral=True)

    # mantém /unlink_all? vamos “aportuguesar” a descrição
    @app_commands.command(name="deslinkar_todos", description="Remove todos os links deste servidor.")
    async def unlink_all_cmd(self, inter: discord.Interaction):
        if not inter.user.guild_permissions.manage_guild:  # type: ignore[union-attr]
            return await inter.response.send_message("🚫 Requer permissão: Gerenciar Servidor.", ephemeral=True)

        await unlink_all(DB_PATH, inter.guild.id)  # type: ignore[arg-type]
        await inter.response.send_message("🧹 Todos os links foram removidos.", ephemeral=True)

    # /links já em PT, agora com contador e limpeza de pares inválidos
    @app_commands.command(name="links", description="Lista todos os pares de canais linkados neste servidor.")
    async def links_cmd(self, inter: discord.Interaction):
        if not inter.user.guild_permissions.manage_guild:  # type: ignore[union-attr]
            return await inter.response.send_message("🚫 Requer permissão: Gerenciar Servidor.", ephemeral=True)

        pairs = await list_links(DB_PATH, inter.guild.id)  # type: ignore[arg-type]
        if not pairs:
            return await inter.response.send_message("Nenhum link configurado.", ephemeral=True)

        linhas = []
        skips = 0  # apenas informativo, caso algum canal não esteja no cache/visível
        for a, la, b, lb in pairs:
            ch_a = inter.guild.get_channel(a)
            ch_b = inter.guild.get_channel(b)
            if not ch_a or not ch_b:
                skips += 1
                continue
            linhas.append(f"🔗 {ch_a.mention} ({la})  ⇄  {ch_b.mention} ({lb})")

        if not linhas:
            return await inter.response.send_message("Nenhum link válido para exibir.", ephemeral=True)

        total = len(linhas)
        msg = "\n".join(linhas)
        nota = f"\nℹ️ {skips} par(es) não exibido(s) (canais não encontrados no cache)." if skips else ""
        await inter.response.send_message(
            f"**Pares de canais linkados ({total}):**\n{msg}{nota}",
            ephemeral=True
        )

