import discord
from discord import app_commands, Interaction
from discord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo
from evtranslator.supabase_client import get_quota

class Quota(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="quota", description="Mostra a cota de tradução do servidor")
    async def quota(self, interaction: Interaction):
        try:
            q = get_quota(interaction.guild_id)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erro ao consultar a cota: {e}", ephemeral=True
            )
            return

        def fmt(n): return f"{int(n):,}".replace(",", ".")
        enabled = "Sim ✅" if q["translate_enabled"] else "Não ❌"
        tz = q.get("cycle_tz") or "UTC"

        # converte next_reset para timezone configurado
        try:
            dt = datetime.fromisoformat(str(q["next_reset"]).replace("Z", "+00:00"))
            next_reset_local = dt.astimezone(ZoneInfo(tz))
            next_reset_str = next_reset_local.strftime("%Y-%m-%d %H:%M")
        except Exception:
            next_reset_str = str(q["next_reset"])

        embed = discord.Embed(
            title="EVTranslator — Quota do Servidor",
            color=0x5865F2,
            description=f"**Habilitado:** {enabled}\n**Dia do reset:** {q['billing_day']} (fuso {tz})"
        )
        embed.add_field(name="Limite (mês)", value=fmt(q["char_limit"]), inline=True)
        embed.add_field(name="Usado", value=fmt(q["used_chars"]), inline=True)
        embed.add_field(name="Restante", value=fmt(q["remaining"]), inline=True)
        embed.add_field(name="Último reset", value=str(q["cycle_start"]).replace("T", " ")[:19], inline=False)
        embed.add_field(name="Próximo reset", value=next_reset_str, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Quota(bot))
