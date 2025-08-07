from discord.ext import commands
from discord import app_commands, Interaction
from util.log_utils import coletar_e_enviar_log
import discord
import logging

logger = logging.getLogger(__name__)

class ObterLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="obter_log", description="Receba o log do canal atual por DM.")
    @app_commands.guild_only()
    async def obter_log(self, interaction: Interaction):
        user = interaction.user
        channel = interaction.channel
        guild = interaction.guild

        logger.info(
            f"[OBTER_LOG] Comando acionado por {user.name}#{user.discriminator} "
            f"(ID: {user.id}) no canal '{channel.name}' do servidor '{guild.name}' (ID: {guild.id})"
        )

        await interaction.response.send_message(
            "🕯️ EVlogger está usando Olhos do Passado…",
            ephemeral=True
        )

        try:
            resultado = await coletar_e_enviar_log(
                channel=channel,
                user=user,
                guild_id=str(guild.id),
                enviar_email_ativo=False  # ✅ aqui está a correção
            )

            if resultado["dm"]:
                logger.info(f"[OBTER_LOG] Log enviado com sucesso por DM para {user.name}#{user.discriminator} (ID: {user.id})")
                await interaction.followup.send(
                    "✅ Log enviado por DM e armazenado em Memória Eidética",
                    ephemeral=True
                )
            else:
                logger.warning(f"[OBTER_LOG] Falha ao enviar DM para {user.name}#{user.discriminator} (ID: {user.id}) — DM fechada?")
                await interaction.followup.send(
                    "❌ Não consegui enviar o log por DM. Verifique suas configurações de privacidade.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error("[OBTER_LOG] Erro inesperado ao processar comando:", exc_info=True)
            await interaction.followup.send(
                "❌ Ocorreu um erro inesperado ao gerar o log.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(ObterLog(bot))
