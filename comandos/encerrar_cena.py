from discord import app_commands
from discord.ext import commands
import discord
from util.log_utils import coletar_e_enviar_log
import logging

logger = logging.getLogger(__name__)

# Decorador para permitir apenas administradores
def apenas_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        else:
            await interaction.response.send_message(
                "🚫 Você precisa ser administrador para usar este comando.",
                ephemeral=True
            )
            return False
    return app_commands.check(predicate)

async def setup(bot: commands.Bot):
    @bot.tree.command(
        name="encerrar_cena",
        description="Encerra a cena atual e envia o log por e-mail e DM. (somente administradores)"
    )
    @app_commands.guild_only()
    @apenas_admin()
    async def encerrar_cena(interaction: discord.Interaction):
        user = interaction.user
        channel = interaction.channel
        guild = interaction.guild

        logger.info(
            f"[ENCERRAR_CENA] Comando acionado por {user.name}#{user.discriminator} (ID: {user.id}) "
            f"no canal '{channel.name}' do servidor '{guild.name}' (ID: {guild.id})"
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
                enviar_email_ativo=True  # <- importante garantir que isso esteja ativado
            )

            if resultado["email"] or resultado["dm"]:
                logger.info(
                    f"[ENCERRAR_CENA] Log enviado com sucesso (email: {resultado['email']}, dm: {resultado['dm']})"
                )
                await interaction.followup.send(
                    "✅ Cena encerrada! Log enviado por e-mail e/ou DM e armazenado em Memória Eidética.",
                    ephemeral=True
                )
            else:
                logger.warning(
                    f"[ENCERRAR_CENA] Falha no envio do log (email: {resultado['email']}, dm: {resultado['dm']})"
                )
                await interaction.followup.send(
                    "❌ Falha ao enviar o log por e-mail e DM.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error("[ENCERRAR_CENA] Erro inesperado ao processar comando:", exc_info=True)
            await interaction.followup.send(
                "❌ Ocorreu um erro inesperado ao tentar encerrar a cena.",
                ephemeral=True
            )
