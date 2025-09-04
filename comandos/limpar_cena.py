from discord import app_commands
from discord.ext import commands
import discord
from util.log_utils import coletar_e_enviar_log
import logging

import asyncio
from discord import NotFound, Forbidden, HTTPException

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

        user = self.interaction.user
        guild = self.interaction.guild
        channel_id = interaction.channel_id
        bot = interaction.client

        # ACK cedo para evitar timeout
        await interaction.response.send_message("🕯️ EVlogger está usando Olhos do Passado…", ephemeral=True)

        # Re-resolve o canal do zero (fresco), com pequeno retry
        canal_original = None
        for attempt in range(2):
            canal_original = bot.get_channel(channel_id)
            if canal_original is None:
                try:
                    canal_original = await bot.fetch_channel(channel_id)
                except NotFound:
                    # pequeno atraso e tenta de novo
                    await asyncio.sleep(0.8)
                    continue
            break

        if canal_original is None or not isinstance(canal_original, discord.TextChannel):
            await self.interaction.followup.send("❌ Este comando só pode ser usado em canais de texto (ou o canal ficou indisponível).", ephemeral=True)
            return

        # Checa permissões necessárias
        me = canal_original.guild.get_member(bot.user.id)
        perms = canal_original.permissions_for(me) if me else discord.Permissions.none()
        if not perms.view_channel or not perms.read_message_history:
            await self.interaction.followup.send("❌ Preciso de **View Channel** e **Read Message History** aqui.", ephemeral=True)
            return

        logger.info(
            f"[LIMPAR_CANAL] Confirmação recebida por {user} (ID: {user.id}) "
            f"no canal '{canal_original.name}' do servidor '{guild.name}' (ID: {guild.id})"
        )

        try:
            resultado = await coletar_e_enviar_log(
                channel=canal_original,
                user=user,
                guild_id=str(guild.id)
            )
        except NotFound:
            await self.interaction.followup.send("❌ Canal não encontrado durante a coleta (pode ter sido removido).", ephemeral=True)
            return
        except Forbidden:
            await self.interaction.followup.send("❌ Sem permissão para ler o histórico.", ephemeral=True)
            return
        except Exception:
            logger.exception("[LIMPAR_CANAL] Erro ao coletar/enviar log:")
            await self.interaction.followup.send("❌ Erro ao coletar ou enviar o log. Canal **não** foi limpo.", ephemeral=True)
            return

        if not (resultado.get("email") or resultado.get("dm")):
            await self.interaction.followup.send("❌ Falha ao enviar o log por e-mail e DM. Canal **não** foi limpo.", ephemeral=True)
            return

        # Recriação → mensagem de sucesso ANTES de deletar
        try:
            categoria = canal_original.category
            posicao = canal_original.position
            overwrites = canal_original.overwrites
            nome = canal_original.name

            novo_canal = await canal_original.guild.create_text_channel(
                name=nome, category=categoria, position=posicao, overwrites=overwrites
            )

            await self.interaction.followup.send("✅ Canal limpo com sucesso! O log foi enviado com segurança.", ephemeral=True)

            # (Opcional) pequeno delay para garantir propagação antes de deletar
            await asyncio.sleep(0.5)

            await canal_original.delete()
            self.stop()
        except Exception:
            logger.exception("[LIMPAR_CANAL] Erro ao recriar ou deletar canal:")
            await self.interaction.followup.send("❌ Ocorreu um erro ao tentar limpar o canal. Nenhuma alteração foi feita.", ephemeral=True)


async def setup(bot: commands.Bot):
    @bot.tree.command(
        name="limpar_canal",
        description="Salva o log e limpa este canal completamente. (somente administradores)"
    )
    @app_commands.guild_only()
    @apenas_admin()
    async def limpar_canal(interaction: discord.Interaction):
        view = ConfirmarLimpeza(bot, interaction)
        await interaction.response.send_message(
            "⚠️ Tem certeza que deseja **limpar completamente** este canal? O log será salvo antes.",
            view=view,
            ephemeral=True
        )
