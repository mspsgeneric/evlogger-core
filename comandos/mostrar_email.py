from discord import app_commands, Interaction
from discord.ext import commands
from util.supabase import get_supabase

supabase = get_supabase()

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
    @bot.tree.command(name="mostrar_email", description="Mostra o e-mail definido para este servidor")
    @apenas_admin()
    async def mostrar_email(interaction: Interaction):
        guild_id = str(interaction.guild.id)

        result = supabase.table("emails").select("email").eq("guild_id", guild_id).execute()

        if result.data:
            email = result.data[0]["email"]
            await interaction.response.send_message(
                f"📨 E-mail configurado neste servidor: {email}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Nenhum e-mail definido para este servidor.",
                ephemeral=True
            )
