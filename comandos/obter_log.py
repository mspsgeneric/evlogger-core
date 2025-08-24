# comandos/obter_log.py
from discord.ext import commands
from discord import app_commands, Interaction
import discord
import logging
from datetime import datetime, timezone

from util.log_utils import coletar_e_enviar_log
from util.hmac_utils import ts_min_iso, token_anonimo
from util.pino_anon import registrar_retirada_anonima

logger = logging.getLogger(__name__)

class ObterLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="obter_log", description="Receba o log do canal atual por DM (e registra retirada de forma anônima no canal).")
    @app_commands.guild_only()
    async def obter_log(self, interaction: Interaction):
        user = interaction.user
        channel = interaction.channel
        guild = interaction.guild

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "❌ Este comando funciona apenas em canais de texto ou threads.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none()
            )
            return

        try:
            await interaction.response.defer(ephemeral=True)

            # Coleta e envia o log (sua função atual)
            resultado = await coletar_e_enviar_log(
                channel=channel,
                user=user,
                guild_id=str(guild.id),
                enviar_email_ativo=False
            )

            dm_ok = bool(resultado.get("dm"))
            if dm_ok:
                await interaction.followup.send(
                    "✅ Log enviado por DM.",
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none()
                )
            else:
                await interaction.followup.send(
                    "❌ Não consegui enviar por DM. Verifique suas configurações de privacidade.",
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none()
                )

            # 🔒 Registro ANÔNIMO no pino do canal (minuto exato da retirada)
            # Obs: usamos o minuto do momento da coleta/envio como "momento da retirada"
            agora = datetime.now(timezone.utc)
            iso_min = ts_min_iso(agora)
            tok = token_anonimo(guild.id, channel.id, user.id, iso_min)
            # Registra apenas em canais de texto (thread tem pino próprio, mas geralmente quer-se no canal pai)
            if isinstance(channel, discord.Thread):
                # Se quiser registrar no canal pai:
                parent = channel.parent
                if isinstance(parent, discord.TextChannel):
                    await registrar_retirada_anonima(parent, iso_min, tok)
            else:
                await registrar_retirada_anonima(channel, iso_min, tok)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão suficiente neste canal (preciso ler histórico e escrever mensagens).",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            logger.exception("[obter_log] erro inesperado")
            await interaction.followup.send(
                "❌ Ocorreu um erro inesperado ao gerar o log.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none()
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(ObterLog(bot))
