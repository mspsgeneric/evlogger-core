from discord import app_commands
from discord.ext import commands
import discord
from util.log_utils import coletar_e_enviar_log
import logging

logger = logging.getLogger(__name__)

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

class ConfirmarArquivo(discord.ui.View):
    def __init__(self, bot, interaction):
        super().__init__(timeout=60)
        self.bot = bot
        self.interaction = interaction

    @discord.ui.button(label="Confirmar arquivamento", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Apenas o autor do comando pode confirmar.", ephemeral=True)
            return

        user = self.interaction.user
        canal_original = self.interaction.channel
        guild = self.interaction.guild

        logger.info(
            f"[ARQUIVAR_CANAL] Confirmação recebida por {user} (ID: {user.id}) "
            f"no canal '{canal_original.name}' do servidor '{guild.name}' (ID: {guild.id})"
        )

        await interaction.response.send_message("🕯️ EVlogger está registrando o passado antes do arquivamento…", ephemeral=True)

        # 🔐 Verificação de segurança
        if not isinstance(canal_original, discord.TextChannel):
            logger.warning(f"[ARQUIVAR_CANAL] Canal '{canal_original}' não é um canal de texto. Abortado.")
            await self.interaction.followup.send(
                "❌ Este comando só pode ser usado em canais de texto.",
                ephemeral=True
            )
            return

        try:
            resultado = await coletar_e_enviar_log(
                channel=canal_original,
                user=user,
                guild_id=str(guild.id)
            )
        except Exception:
            logger.error("[ARQUIVAR_CANAL] Erro ao coletar/enviar log:", exc_info=True)
            await self.interaction.followup.send("❌ Erro ao coletar ou enviar o log. Canal **não** foi arquivado.", ephemeral=True)
            return

        if not (resultado["email"] or resultado["dm"]):
            logger.warning(f"[ARQUIVAR_CANAL] Falha ao enviar log (email: {resultado['email']}, dm: {resultado['dm']}).")
            await self.interaction.followup.send("❌ Falha ao enviar o log. Canal **não** foi arquivado.", ephemeral=True)
            return

        try:
            await self.interaction.followup.send(
                "✅ Canal arquivado com sucesso! O log foi enviado com segurança.",
                ephemeral=True
            )
            self.stop()

            await canal_original.delete()

        except Exception:
            logger.error("[ARQUIVAR_CANAL] Erro ao deletar canal:", exc_info=True)
            await self.interaction.followup.send(
                "❌ Ocorreu um erro ao tentar arquivar o canal.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    @bot.tree.command(
        name="arquivar_canal",
        description="Salva o log e remove este canal permanentemente. (somente administradores)"
    )
    @app_commands.guild_only()
    @apenas_admin()
    async def arquivar_canal(interaction: discord.Interaction):
        view = ConfirmarArquivo(bot, interaction)
        await interaction.response.send_message(
            "⚠️ Tem certeza que deseja **arquivar este canal permanentemente**? O log será salvo antes.",
            view=view,
            ephemeral=True
        )
