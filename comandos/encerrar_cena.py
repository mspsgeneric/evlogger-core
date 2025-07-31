from discord import app_commands
from discord.ext import commands
import discord
from util.log_utils import coletar_e_enviar_log

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
    @bot.tree.command(name="encerrar_cena", description="Encerra a cena atual e envia o log por e-mail e DM.")
    @apenas_admin()
    async def encerrar_cena(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        print("DEBUG: /encerrar_cena foi acionado!")

        resultado = await coletar_e_enviar_log(
            channel=interaction.channel,
            user=interaction.user,
            guild_id=str(interaction.guild.id)
        )

        if resultado["email"] or resultado["dm"]:
            await interaction.followup.send("✅ Cena encerrada! Log enviado por e-mail e/ou DM.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Falha ao enviar o log por e-mail e DM.", ephemeral=True)
