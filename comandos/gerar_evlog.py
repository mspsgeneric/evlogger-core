from discord.ext import commands
from discord import app_commands, Interaction
import discord
import json
from datetime import datetime
import os
import re

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

        await interaction.response.send_message(
            "📦 Iniciando exportação... isso pode demorar em canais grandes.",
            ephemeral=True
        )

        mensagens = []
        canal = interaction.channel
        apelido_cache = {}

        try:
            async for msg in canal.history(limit=None, oldest_first=True):
                autor_id = msg.author.id

                # Usa cache para nome/apelido
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

                # Captura conteúdo da mensagem ou do embed
                conteudo = msg.content
                if not conteudo and msg.embeds:
                    embed = msg.embeds[0]
                    partes = []
                    if embed.title:
                        partes.append(f"**{embed.title}**")
                    if embed.description:
                        partes.append(embed.description)
                    conteudo = "\n".join(partes)

                # Substitui menções no conteúdo
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
                    "avatar_url": str(autor.display_avatar.url),
                    "data": msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "conteudo": conteudo,
                    "anexos": [a.url for a in msg.attachments]
                })

            # Cria nome de arquivo
            nome_base = re.sub(r'\W+', '_', canal.name)
            nome_arquivo = f"{nome_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.evlog"

            with open(nome_arquivo, "w", encoding="utf-8") as f:
                json.dump(mensagens, f, ensure_ascii=False, indent=2)

            await interaction.followup.send(
                f"✅ Exportação finalizada com sucesso. `{nome_arquivo}` está pronto para uso no aplicativo EVlogger.",
                ephemeral=True,
                file=discord.File(nome_arquivo)
            )
            os.remove(nome_arquivo)

        except Exception as e:
            await interaction.followup.send("❌ Ocorreu um erro ao gerar o log.", ephemeral=True)
            raise e

    @gerar_evlog.error
    async def gerar_evlog_error(self, interaction: Interaction, error):
        if isinstance(error, commands.MissingPermissions):
            await interaction.response.send_message(
                "🚫 Este comando é restrito a administradores.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Ocorreu um erro inesperado.",
                ephemeral=True
            )
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(GerarEvlog(bot))
