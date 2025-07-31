from discord import app_commands
from discord.ext import commands
import discord

async def setup(bot: commands.Bot):
    @bot.tree.command(name="ajuda", description="Lista os comandos disponíveis do EVlogger")
    async def ajuda(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📘 Comandos do EVlogger",
            description="Veja abaixo os comandos disponíveis para administrar suas cenas:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="/definir_email [email]",
            value="Define ou redefine o e-mail que receberá os logs das cenas neste servidor.",
            inline=False
        )

        embed.add_field(
            name="/mostrar_email",
            value="Mostra o e-mail atualmente configurado para este servidor.",
            inline=False
        )

        embed.add_field(
            name="/encerrar_cena",
            value="Salva o log completo da cena atual, envia por e-mail e por DM (em .txt).",
            inline=False
        )

        embed.add_field(
            name="/limpar_canal",
            value="(⚠️ Apaga o canal atual e cria um novo vazio com as mesmas permissões.)\n"
                  "O log será salvo e enviado antes da limpeza, se possível.",
            inline=False
        )

        embed.set_footer(text="Apenas administradores podem usar os comandos acima.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
