from discord import app_commands, Interaction
from discord.ext import commands
from util.supabase import get_supabase
import logging
import traceback
import re

supabase = get_supabase()

# Setup de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Decorador para verificar se o usuário é administrador
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
    @bot.tree.command(name="definir_email", description="Define o e-mail para receber logs (somente administradores)")
    @app_commands.guild_only()
    @app_commands.describe(email="E-mail para receber logs neste servidor")
    @apenas_admin()
    async def definir_email(interaction: Interaction, email: str):
        logger.info("Comando /definir_email acionado")

        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            await interaction.response.send_message("❌ E-mail inválido.", ephemeral=True)
            return

        try:
            guild_id = str(interaction.guild.id)
            data = {"guild_id": guild_id, "email": email}

            logger.debug(f"Enviando dados para Supabase: {data}")
            supabase.table("emails").upsert(data, on_conflict=["guild_id"]).execute()
            logger.info(
                f"[EMAIL CONFIGURADO] '{email}' por {interaction.user.name}#{interaction.user.discriminator} "
                f"(user_id={interaction.user.id}) no servidor '{interaction.guild.name}' (guild_id={guild_id})"
            )




            await interaction.response.send_message(
                f"📬 E-mail definido como: {email}",
                ephemeral=True
            )

        except Exception as e:
            logger.error("Erro ao definir e-mail", exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao definir e-mail.",
                ephemeral=True
            )
