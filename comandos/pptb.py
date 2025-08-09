# comandos/pptb.py
from secrets import choice as randchoice
from typing import Optional
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
EMOJI = {"pedra":"🪨","papel":"📄","tesoura":"✂️","bomba":"💣"}

def resultado(a: str, b: str) -> str:
    if a == b: return "empate"
    if b in WINS[a]: return "jogador"
    if a in WINS[b]: return "bot"
    return "empate"

class EscolhaView(discord.ui.View):
    def __init__(self, user_id: int, timeout: float = 90):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Só quem iniciou o teste pode usar esses botões.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children: c.disabled = True
        if self.message:
            try: await self.message.edit(content="⏰ **Tempo esgotado (90s)**", view=self)
            except Exception: pass

    async def _resolver(self, interaction: discord.Interaction, jogada: str):
        await interaction.response.defer()  # evita 10062

        if jogada == "aleatoria":
            jogada = randchoice(OPCOES_PPTB)  # aleatória pode sair 💣
        bot_escolha = randchoice(OPCOES_PPTB)

        r = resultado(jogada, bot_escolha)
        texto = (
            f"**Você**: {EMOJI[jogada]} **{jogada.capitalize()}**\n"
            f"**Bot**: {EMOJI[bot_escolha]} **{bot_escolha.capitalize()}**\n\n"
        )
        texto += "🟨 **Empate!**" if r=="empate" else ("🟩 **Você venceu!**" if r=="jogador" else "🟥 **O bot venceu!**")

        for c in self.children: c.disabled = True
        await interaction.edit_original_response(content=texto, view=self)

    @discord.ui.button(label="Pedra",   style=discord.ButtonStyle.secondary, emoji="🪨")
    async def pedra(self, i: discord.Interaction, _):   await self._resolver(i, "pedra")

    @discord.ui.button(label="Papel",   style=discord.ButtonStyle.secondary, emoji="📄")
    async def papel(self, i: discord.Interaction, _):   await self._resolver(i, "papel")

    @discord.ui.button(label="Tesoura", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def tesoura(self, i: discord.Interaction, _): await self._resolver(i, "tesoura")

    @discord.ui.button(label="Bomba",   style=discord.ButtonStyle.danger,    emoji="💣")
    async def bomba(self, i: discord.Interaction, _):   await self._resolver(i, "bomba")

    @discord.ui.button(label="Aleatória", style=discord.ButtonStyle.primary)
    async def aleatoria(self, i: discord.Interaction, _): await self._resolver(i, "aleatoria")

class PPTB(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pptb", description="Jogue Pedra, Papel, Tesoura e Bomba (com botões ou parâmetro).")
    @app_commands.describe(escolha="(opcional) pedra/papel/tesoura/bomba/aleatoria")
    @app_commands.choices(escolha=[
        app_commands.Choice(name="Pedra", value="pedra"),
        app_commands.Choice(name="Papel", value="papel"),
        app_commands.Choice(name="Tesoura", value="tesoura"),
        app_commands.Choice(name="Bomba", value="bomba"),
        app_commands.Choice(name="Aleatória (pode sair 💣)", value="aleatoria"),
    ])
    async def pptb(self, interaction: discord.Interaction, escolha: Optional[app_commands.Choice[str]] = None):
        # Se veio por parâmetro, resolve direto
        if escolha is not None:
            jog = randchoice(OPCOES_PPTB) if escolha.value == "aleatoria" else escolha.value
            bot_escolha = randchoice(OPCOES_PPTB)
            r = resultado(jog, bot_escolha)
            msg = (
                f"**Você**: {EMOJI[jog]} **{jog.capitalize()}**\n"
                f"**Bot**: {EMOJI[bot_escolha]} **{bot_escolha.capitalize()}**\n\n"
            )
            msg += "🟨 **Empate!**" if r=="empate" else ("🟩 **Você venceu!**" if r=="jogador" else "🟥 **O bot venceu!**")
            await interaction.response.send_message(msg)
            return

        # Sem parâmetro → abre os botões
        view = EscolhaView(user_id=interaction.user.id, timeout=90)
        await interaction.response.defer(thinking=True)
        await interaction.edit_original_response(content="Escolha sua jogada:", view=view)
        try: view.message = await interaction.original_response()
        except Exception: pass

async def setup(bot: commands.Bot):
    await bot.add_cog(PPTB(bot))
