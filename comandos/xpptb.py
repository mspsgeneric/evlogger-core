# comandos/pptbd.py
from secrets import choice as randchoice
import discord
from discord import app_commands
from discord.ext import commands

# opções e lógica
OPCOES_PPT = ("pedra", "papel", "tesoura")
OPCOES_PPTB = ("pedra", "papel", "tesoura", "bomba")

WINS = {
    "pedra":   {"tesoura"},
    "papel":   {"pedra"},
    "tesoura": {"papel", "bomba"},
    "bomba":   {"pedra", "papel"},
}
EMOJI = {"pedra": "🪨", "papel": "📄", "tesoura": "✂️", "bomba": "💣"}

def resultado(a: str, b: str) -> str:
    if a == b:
        return "empate"
    if b in WINS[a]:
        return "jogador1"
    if a in WINS[b]:
        return "jogador2"
    return "empate"

class PPTBD(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="pptbd",
        description="Duelo rápido de Pedra, Papel, Tesoura (com opção de Bomba)."
    )
    @app_commands.describe(
        jogador1="Jogador 1",
        jogador2="Jogador 2",
        pc1_bomba="PC 1 pode usar bomba?",
        pc2_bomba="PC 2 pode usar bomba?",
    )
    @app_commands.choices(
        pc1_bomba=[
            app_commands.Choice(name="🚫 Sem bomba", value="sem"),
            app_commands.Choice(name="💣 Com bomba", value="bomba"),
        ],
        pc2_bomba=[
            app_commands.Choice(name="🚫 Sem bomba", value="sem"),
            app_commands.Choice(name="💣 Com bomba", value="bomba"),
        ],
    )
    async def pptbd(
        self,
        interaction: discord.Interaction,
        jogador1: discord.User,
        jogador2: discord.User,
        pc1_bomba: app_commands.Choice[str] = None,
        pc2_bomba: app_commands.Choice[str] = None,
    ):
        if jogador1.id == jogador2.id:
            await interaction.response.send_message("⚠️ Os jogadores devem ser diferentes.", ephemeral=True)
            return

        # usa "sem" como default se não selecionado
        j1_b = pc1_bomba.value if pc1_bomba else "sem"
        j2_b = pc2_bomba.value if pc2_bomba else "sem"

        opcoes_j1 = OPCOES_PPTB if j1_b == "bomba" else OPCOES_PPT
        opcoes_j2 = OPCOES_PPTB if j2_b == "bomba" else OPCOES_PPT

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
    await bot.add_cog(PPTBD(bot))
