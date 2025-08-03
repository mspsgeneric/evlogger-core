from discord import app_commands
from discord.ext import commands
import discord
from util.log_utils import coletar_e_enviar_log

async def setup(bot: commands.Bot):
    @bot.tree.command(name="obter_log", description="Receba o log do canal atual por DM.")
    async def obter_log(interaction: discord.Interaction):
        
        await interaction.response.send_message("🕯️ EVlogger está usando Olhos do Passado…", ephemeral=True)



        print(f"DEBUG: /obter_log foi acionado por {interaction.user.name} em {interaction.channel.name}")

        resultado = await coletar_e_enviar_log(
            channel=interaction.channel,
            user=interaction.user,
            guild_id=str(interaction.guild.id)
        )

        if resultado["dm"]:
            await interaction.followup.send("✅ Log enviado por DM e armazenado em Memória Eidética", ephemeral=True)
        else:
            await interaction.followup.send("❌ Não consegui enviar o log por DM. Verifique suas configurações de privacidade.", ephemeral=True)
