# comandos/check.py
from discord.ext import commands
from discord import app_commands, Interaction
import discord
from datetime import datetime, timezone
from util.pino_anon import get_pin, parse_entries
from util.hmac_utils import token_anonimo

ALLOWED_NONE = discord.AllowedMentions.none()

class CheckRetiradas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="check",
        description="Mostra todas as vezes que você baixou o log neste canal."
    )
    @app_commands.guild_only()
    async def check(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "❌ Use este comando em um **canal de texto**.",
                ephemeral=True, allowed_mentions=ALLOWED_NONE
            )
            return

        pin = await get_pin(channel)  # <- NÃO cria pino
        if not pin:
            await interaction.followup.send(
                (
                    f"🔎 **Nenhuma retirada registrada em {channel.mention}.**\n\n"
                    "Você **ainda não obteve** nenhum log deste canal ou ainda **não há registros** aqui.\n"
                    "Quando quiser, execute **/obter_log** neste canal. Depois, volte com **/check**."
                ),
                ephemeral=True, allowed_mentions=ALLOWED_NONE
            )
            return

        entries = parse_entries(pin.content or "")
        if not entries:
            await interaction.followup.send(
                (
                    f"🔎 **Nenhuma retirada registrada em {channel.mention}.**\n\n"
                    "Este canal **ainda não possui** registros de retirada.\n"
                    "Use **/obter_log** para gerar o primeiro."
                ),
                ephemeral=True, allowed_mentions=ALLOWED_NONE
            )
            return

        retiradas: list[str] = []
        for iso_min, tok in entries:
            exp = token_anonimo(channel.guild.id, channel.id, interaction.user.id, iso_min)
            if exp == tok:
                dt = datetime.strptime(iso_min, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
                unix = int(dt.timestamp())
                retiradas.append(f"- <t:{unix}:F> (<t:{unix}:R>)")

        if not retiradas:
            await interaction.followup.send(
                (
                    f"🔎 **Você ainda não obteve nenhum log de {channel.mention}.**\n\n"
                    "Para obter o primeiro, execute **/obter_log** aqui. "
                    "Depois, use **/check** para ver seu histórico."
                ),
                ephemeral=True, allowed_mentions=ALLOWED_NONE
            )
            return

        MAX_MOSTRAR = 25
        msg = f"🧾 **Suas retiradas registradas em {channel.mention}:**\n" + "\n".join(retiradas[:MAX_MOSTRAR])
        if len(retiradas) > MAX_MOSTRAR:
            msg += f"\n… e mais {len(retiradas) - MAX_MOSTRAR} antigas."

        await interaction.followup.send(msg, ephemeral=True, allowed_mentions=ALLOWED_NONE)

async def setup(bot: commands.Bot):
    await bot.add_cog(CheckRetiradas(bot))
