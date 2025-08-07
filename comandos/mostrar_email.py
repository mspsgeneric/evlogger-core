from discord import app_commands, Interaction
from discord.ext import commands
from util.supabase import get_supabase
import logging

supabase = get_supabase()

# Setup de logging
logger = logging.getLogger(__name__)

# Decorador para permitir apenas administradores
def apenas_admin():
    async def predicate(interaction: Interaction) -> bool:
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
        name="mostrar_email",
        description="Mostra o e-mail definido para este servidor. (somente administradores)"
    )
    @app_commands.guild_only()
    @apenas_admin()
    async def mostrar_email(interaction: Interaction):
        guild_id = str(interaction.guild.id)
        user = interaction.user
        guild_name = interaction.guild.name

        logger.info(
            f"[EMAIL CONSULTA] Comando executado por {user.name}#{user.discriminator} (ID: {user.id}) "
            f"no servidor '{guild_name}' (ID: {guild_id})"
        )

        try:
            result = supabase.table("emails").select("email").eq("guild_id", guild_id).execute()

            if result.data:
                email = result.data[0]["email"]
                logger.info(f"[EMAIL CONSULTA] E-mail retornado: {email}")
                await interaction.response.send_message(
                    f"📨 E-mail configurado neste servidor: {email}",
                    ephemeral=True
                )
            else:
                logger.info("[EMAIL CONSULTA] Nenhum e-mail encontrado para este servidor.")
                await interaction.response.send_message(
                    "❌ Nenhum e-mail definido para este servidor.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error("Erro ao buscar e-mail na Supabase", exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao buscar o e-mail deste servidor.",
                ephemeral=True
            )
