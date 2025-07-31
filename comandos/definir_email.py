from discord import app_commands
from discord.ext import commands
from discord import Interaction
from util.supabase import get_supabase
import traceback

supabase = get_supabase()

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
    @bot.tree.command(name="definir_email", description="Define o e-mail para receber logs")
    @app_commands.describe(email="E-mail para receber logs neste servidor")
    @apenas_admin()
    async def definir_email(interaction: Interaction, email: str):
        print("✅ Comando /definir_email foi acionado")

        try:
            guild_id = str(interaction.guild.id)

            data = {
                "guild_id": guild_id,
                "email": email
            }

            print(f"🔧 Enviando para Supabase: {data}")

            supabase.table("emails").upsert(
                data,
                on_conflict=["guild_id"]
            ).execute()

            print("✅ Supabase: upsert executado com sucesso")

            await interaction.response.send_message(
                f"📬 E-mail definido para este servidor como: {email}",
                ephemeral=True
            )

        except Exception as e:
            print("❌ Ocorreu um erro:")
            traceback.print_exc()
            await interaction.response.send_message(
                "❌ Erro ao definir e-mail.",
                ephemeral=True
            )
