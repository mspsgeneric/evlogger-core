# comandos/pptb.py
from secrets import choice as randchoice
import discord
from discord import app_commands
from discord.ext import commands

OPCOES_PPT  = ("pedra", "papel", "tesoura")
OPCOES_PPTB = ("pedra", "papel", "tesoura", "bomba")

WINS = {
    "pedra":   {"tesoura"},
    "papel":   {"pedra"},
    "tesoura": {"papel", "bomba"},
    "bomba":   {"pedra", "papel"},
}

def resultado(a: str, b: str) -> str:
    if a == b:
        return "empate"
    if b in WINS[a]:
        return "jogador"
    if a in WINS[b]:
        return "bot"
    return "empate"

class EscolhaView(discord.ui.View):
    def __init__(self, user_id: int, timeout: float = 90):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Só quem chamou o comando pode clicar
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Só quem iniciou o teste pode usar esses botões.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ **Tempo esgotado (90s)**", view=self)
            except Exception:
                pass

    async def _resolver(self, interaction: discord.Interaction, jogada: str):
        # Aleatório do JOGADOR nunca inclui bomba
        if jogada == "aleatoria":
            jogada = randchoice(OPCOES_PPT)

        # BOT sempre pode usar bomba
        bot_escolha = randchoice(OPCOES_PPTB)

        r = resultado(jogada, bot_escolha)
        emojis = {"pedra":"🪨","papel":"📄","tesoura":"✂️","bomba":"💣"}

        texto = (
            f"**Você**: {emojis[jogada]} **{jogada.capitalize()}**\n"
            f"**Bot**: {emojis[bot_escolha]} **{bot_escolha.capitalize()}**\n\n"
        )
        if r == "empate":
            texto += "🟨 **Empate!**"
        elif r == "jogador":
            texto += "🟩 **Você venceu!**"
        else:
            texto += "🟥 **O bot venceu!**"

        # Desabilita os botões e mostra o resultado
        for c in self.children:
            c.disabled = True

        await interaction.response.edit_message(content=texto, view=self)

    @discord.ui.button(label="Pedra", style=discord.ButtonStyle.secondary, emoji="🪨")
    async def pedra(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolver(interaction, "pedra")

    @discord.ui.button(label="Papel", style=discord.ButtonStyle.secondary, emoji="📄")
    async def papel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolver(interaction, "papel")

    @discord.ui.button(label="Tesoura", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def tesoura(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolver(interaction, "tesoura")

    @discord.ui.button(label="Bomba", style=discord.ButtonStyle.danger, emoji="💣")
    async def bomba(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolver(interaction, "bomba")

    @discord.ui.button(label="Aleatória (sem bomba)", style=discord.ButtonStyle.primary)
    async def aleatoria(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolver(interaction, "aleatoria")

class PPTB(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="pptb",
        description="Jogue Pedra, Papel, Tesoura e Bomba contra o bot (com botões)."
    )
    async def pptb(self, interaction: discord.Interaction):
        view = EscolhaView(user_id=interaction.user.id, timeout=90)
        await interaction.response.send_message("Escolha sua jogada:", view=view)
        # pega a mensagem para que o View possa editá-la no timeout
        view.message = await interaction.original_response()

async def setup(bot: commands.Bot):
    await bot.add_cog(PPTB(bot))
