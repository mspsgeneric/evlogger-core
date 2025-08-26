# comandos/xpptb.py
from secrets import choice as randchoice
import discord
from discord import app_commands
from discord.ext import commands

# mesmas opções e lógica do pptb
OPCOES_PPT = ("pedra", "papel", "tesoura")
OPCOES_PPTB = ("pedra", "papel", "tesoura", "bomba")

WINS = {
    "pedra":   {"tesoura"},
    "papel":   {"pedra"},
    "tesoura": {"papel", "bomba"},
    "bomba":   {"pedra", "papel"},
}
EMOJI = {"pedra":"🪨","papel":"📄","tesoura":"✂️","bomba":"💣"}

def resultado(a: str, b: str) -> str:
    if a == b:
        return "empate"
    if b in WINS[a]:
        return "jogador1"
    if a in WINS[b]:
        return "jogador2"
    return "empate"

class XPPTB(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="xpptb",
        description="PvP de Pedra, Papel, Tesoura (com opção de Bomba)."
    )
    @app_commands.describe(
        jogador1="Jogador 1",
        opcao1="Digite 'b' para incluir bomba (ou deixe vazio)",
        jogador2="Jogador 2",
        opcao2="Digite 'b' para incluir bomba (ou deixe vazio)",
    )
    async def xpptb(
        self,
        interaction: discord.Interaction,
        jogador1: discord.User,
        opcao1: str = "",
        jogador2: discord.User = None,
        opcao2: str = "",
    ):
        if jogador2 is None:
            await interaction.response.send_message("⚠️ Você precisa escolher o Jogador 2!", ephemeral=True)
            return

        # monta opções para cada jogador
        opcoes_j1 = OPCOES_PPTB if opcao1.lower() == "b" else OPCOES_PPT
        opcoes_j2 = OPCOES_PPTB if opcao2.lower() == "b" else OPCOES_PPT

        # sorteios
        jogada1 = randchoice(opcoes_j1)
        jogada2 = randchoice(opcoes_j2)

        # resultado
        r = resultado(jogada1, jogada2)

        texto = (
            f"👤 **{jogador1.mention}**: {EMOJI[jogada1]} **{jogada1.capitalize()}**\n"
            f"👤 **{jogador2.mention}**: {EMOJI[jogada2]} **{jogada2.capitalize()}**\n\n"
        )

        if r == "empate":
            texto += "🟨 **Empate!**"
        elif r == "jogador1":
            texto += f"🟩 **{jogador1.mention} venceu!**"
        else:
            texto += f"🟥 **{jogador2.mention} venceu!**"

        await interaction.response.send_message(texto)

async def setup(bot: commands.Bot):
    await bot.add_cog(XPPTB(bot))
