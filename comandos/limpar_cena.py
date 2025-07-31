from discord import app_commands
from discord.ext import commands
import discord
from util.log_utils import coletar_e_enviar_log

# Decorador para administradores
def apenas_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message(
            "🚫 Você precisa ser administrador para usar este comando.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)

class ConfirmarLimpeza(discord.ui.View):
    def __init__(self, bot, interaction):
        super().__init__(timeout=60)
        self.bot = bot
        self.interaction = interaction

    @discord.ui.button(label="Confirmar limpeza", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Apenas o autor do comando pode confirmar.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        canal_original = self.interaction.channel
        guild_id = str(self.interaction.guild.id)
        user = self.interaction.user

        resultado = await coletar_e_enviar_log(canal_original, user, guild_id)

        if not (resultado["email"] or resultado["dm"]):
            await self.interaction.followup.send("❌ Falha ao enviar o log por e-mail e DM. Canal **não** foi limpo.", ephemeral=True)
            return

        # Recriar canal com as mesmas permissões e nome
        categoria = canal_original.category
        posicao = canal_original.position
        overwrites = canal_original.overwrites
        nome = canal_original.name
        tipo = type(canal_original)

        novo_canal = await canal_original.guild.create_text_channel(
            name=nome,
            category=categoria,
            position=posicao,
            overwrites=overwrites
        )

        await canal_original.delete()
        await self.interaction.followup.send("✅ Canal limpo com sucesso! O log foi enviado com segurança.", ephemeral=True)

async def setup(bot: commands.Bot):
    @bot.tree.command(name="limpar_canal", description="Salva o log e limpa este canal completamente.")
    @apenas_admin()
    async def limpar_canal(interaction: discord.Interaction):
        view = ConfirmarLimpeza(bot, interaction)
        await interaction.response.send_message(
            "⚠️ Tem certeza que deseja **limpar completamente** este canal? O log será salvo antes.",
            view=view,
            ephemeral=True
        )
