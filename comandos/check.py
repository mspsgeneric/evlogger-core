# comandos/check.py
from discord.ext import commands
from discord import app_commands, Interaction
import discord
from datetime import datetime, timezone
from util.pino_anon import get_pin, parse_entries
from util.hmac_utils import token_anonimo

ALLOWED_NONE = discord.AllowedMentions.none()
MAX_MOSTRAR = 25


class CheckRetiradas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_no_logs(self, interaction: Interaction, channel: discord.TextChannel, motivo: str):
        """Envia mensagem padrão quando não há registros de retirada."""
        await interaction.followup.send(
            (
                f"🔎 **Nenhuma retirada registrada em {channel.mention}.**\n\n"
                f"{motivo}\n"
                "Use **/obter_log** neste canal para gerar o primeiro."
            ),
            ephemeral=True,
            allowed_mentions=ALLOWED_NONE,
        )

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
                ephemeral=True,
                allowed_mentions=ALLOWED_NONE,
            )
            return

        # Busca pino (não cria se não houver)
        pin = await get_pin(channel)
        if not pin:
            await self._send_no_logs(interaction, channel, "Você **ainda não obteve** nenhum log aqui.")
            return

        entries = parse_entries(pin.content or "")
        if not entries:
            await self._send_no_logs(interaction, channel, "Este canal **ainda não possui** registros de retirada.")
            return

        retiradas: list[str] = []
        for iso_min, tok in entries:
            exp = token_anonimo(channel.guild.id, channel.id, interaction.user.id, iso_min)
            if exp == tok:
                try:
                    # Tenta parsear ISO completo; fallback para formato reduzido
                    dt = datetime.fromisoformat(iso_min.replace("Z", "+00:00"))
                except ValueError:
                    dt = datetime.strptime(iso_min, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)

                unix = int(dt.timestamp())
                retiradas.append(f"- <t:{unix}:F> (<t:{unix}:R>)")

        if not retiradas:
            await self._send_no_logs(interaction, channel, "Você ainda não obteve nenhum log aqui.")
            return

        # Monta embed para visualização
        embed = discord.Embed(
            title=f"🧾 Suas retiradas em #{channel.name}",
            description="\n".join(retiradas[:MAX_MOSTRAR]),
            color=discord.Color.blurple(),
        )
        if len(retiradas) > MAX_MOSTRAR:
            embed.set_footer(text=f"… e mais {len(retiradas) - MAX_MOSTRAR} antigas.")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CheckRetiradas(bot))
