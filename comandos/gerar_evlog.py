from discord.ext import commands
from discord import app_commands, Interaction
import discord
import json
from datetime import datetime
import os
import re
import logging

logger = logging.getLogger(__name__)
MENTION_PATTERN = re.compile(r"<@!?(\d+)>")  # captura <@123> ou <@!123>

class GerarEvlog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="gerar_evlog",
        description="Exporta o log completo do canal atual como .evlog (somente administradores)"
    )
    async def gerar_evlog(self, interaction: Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "🚫 Apenas administradores podem usar este comando.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        mensagens = []
        canal = interaction.channel
        apelido_cache = {}

        logger.info(
            f"[GERAR_EVLOG] Comando acionado por {interaction.user} (ID: {interaction.user.id}) no canal '{canal.name}' do servidor '{interaction.guild.name}' (ID: {interaction.guild.id})"
        )

        try:
            async for msg in canal.history(limit=None, oldest_first=True):
                autor_id = msg.author.id

                if autor_id in apelido_cache:
                    autor = apelido_cache[autor_id]
                else:
                    try:
                        autor = await interaction.guild.fetch_member(autor_id)
                    except discord.NotFound:
                        autor = msg.author
                    apelido_cache[autor_id] = autor

                apelido = autor.display_name
                nome_completo = str(autor)

                conteudo = msg.content or ""
                if not conteudo and msg.embeds:
                    embed = msg.embeds[0]
                    partes = []
                    if embed.title:
                        partes.append(f"**{embed.title}**")
                    if embed.description:
                        partes.append(embed.description)
                    conteudo = "\n".join(partes)

                matches = list(MENTION_PATTERN.finditer(conteudo))
                for match in reversed(matches):
                    user_id = int(match.group(1))
                    if user_id in apelido_cache:
                        nome = apelido_cache[user_id].display_name
                    else:
                        membro = interaction.guild.get_member(user_id)
                        if not membro:
                            try:
                                membro = await interaction.guild.fetch_member(user_id)
                            except discord.NotFound:
                                nome = f"{user_id}"
                            else:
                                nome = membro.display_name
                        else:
                            nome = membro.display_name
                        apelido_cache[user_id] = membro or user_id
                    inicio, fim = match.span()
                    conteudo = conteudo[:inicio] + f"@{nome}" + conteudo[fim:]

                mensagens.append({
                    "autor": nome_completo,
                    "id_autor": autor_id,
                    "apelido": apelido,
                    "avatar_url": str(getattr(autor.display_avatar, "url", "")),
                    "data": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "conteudo": conteudo,
                    "anexos": [a.url for a in msg.attachments]
                })

            if not mensagens:
                await interaction.followup.send("⚠️ Nenhuma mensagem encontrada neste canal.", ephemeral=True)
                return

            nome_base = re.sub(r'\W+', '_', canal.name)
            nome_arquivo = f"{nome_base}_{canal.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.evlog"

            with open(nome_arquivo, "w", encoding="utf-8") as f:
                json.dump(mensagens, f, ensure_ascii=False, indent=2)

            logger.info(f"[GERAR_EVLOG] Log gerado: {nome_arquivo} com {len(mensagens)} mensagens")

            await interaction.followup.send(
                f"✅ Exportação finalizada com sucesso. `{nome_arquivo}` está pronto para uso no aplicativo EVlogger.",
                ephemeral=True,
                file=discord.File(nome_arquivo)
            )
            os.remove(nome_arquivo)

        except Exception as e:
            logger.error("[GERAR_EVLOG] Erro inesperado ao gerar .evlog:", exc_info=True)
            await interaction.followup.send("❌ Ocorreu um erro ao gerar o log.", ephemeral=True)

    @gerar_evlog.error
    async def gerar_evlog_error(self, interaction: Interaction, error):
        msg = "❌ Ocorreu um erro inesperado."
        if isinstance(error, commands.MissingPermissions):
            msg = "🚫 Este comando é restrito a administradores."

        logger.error("[GERAR_EVLOG] Erro inesperado fora do corpo do comando:", exc_info=True)

        # ✅ Evita 40060: se já houve ack (send_message/defer), use followup
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GerarEvlog(bot))
