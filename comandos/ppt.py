# comandos/ppt.py
from secrets import choice as randchoice
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

OPCOES_PPT = ("pedra", "papel", "tesoura")
WINS = {"pedra": {"tesoura"}, "papel": {"pedra"}, "tesoura": {"papel"}}
EMOJI = {"pedra":"🪨","papel":"📄","tesoura":"✂️"}

def resultado(a: str, b: str) -> str:
    if a == b: return "empate"
    if b in WINS[a]: return "jogador"
    if a in WINS[b]: return "bot"
    return "empate"

class EscolhaViewPPT(discord.ui.View):
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
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ **Tempo esgotado (90s)**", view=self)
            except Exception:
                pass

    async def _resolver(self, interaction: discord.Interaction, jogada: str):
        await interaction.response.defer()
        if jogada == "aleatoria":
            jogada = randchoice(OPCOES_PPT)
        bot_escolha = randchoice(OPCOES_PPT)

        r = resultado(jogada, bot_escolha)
        texto = (
            f"**Você**: {EMOJI[jogada]} **{jogada.capitalize()}**\n"
            f"**Bot**: {EMOJI[bot_escolha]} **{bot_escolha.capitalize()}**\n\n"
        )
        texto += "🟨 **Empate!**" if r=="empate" else ("🟩 **Você venceu!**" if r=="jogador" else "🟥 **O bot venceu!**")

        for c in self.children: c.disabled = True
        await interaction.edit_original_response(content=texto, view=self)

    @discord.ui.button(label="Pedra", style=discord.ButtonStyle.secondary, emoji="🪨")
    async def pedra(self, i: discord.Interaction, _): await self._resolver(i, "pedra")

    @discord.ui.button(label="Papel", style=discord.ButtonStyle.secondary, emoji="📄")
    async def papel(self, i: discord.Interaction, _): await self._resolver(i, "papel")

    @discord.ui.button(label="Tesoura", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def tesoura(self, i: discord.Interaction, _): await self._resolver(i, "tesoura")

    @discord.ui.button(label="Aleatória", style=discord.ButtonStyle.primary)
    async def aleatoria(self, i: discord.Interaction, _): await self._resolver(i, "aleatoria")

class PPT(commands.Cog):
    def __init__(self, bot: commands.Bot): self.bot = bot

    @app_commands.command(name="ppt", description="Jogue Pedra, Papel e Tesoura (sem bomba).")
    @app_commands.describe(escolha="(opcional) pedra/papel/tesoura/aleatoria")
    @app_commands.choices(escolha=[
        app_commands.Choice(name="Pedra", value="pedra"),
        app_commands.Choice(name="Papel", value="papel"),
        app_commands.Choice(name="Tesoura", value="tesoura"),
        app_commands.Choice(name="Aleatória", value="aleatoria"),
    ])
    async def ppt(self, interaction: discord.Interaction, escolha: Optional[app_commands.Choice[str]] = None):
        # se o usuário digitou a escolha → resolve direto
        if escolha is not None:
            jog = randchoice(OPCOES_PPT) if escolha.value == "aleatoria" else escolha.value
            bot_escolha = randchoice(OPCOES_PPT)
            r = resultado(jog, bot_escolha)
            msg = (
                f"**Você**: {EMOJI[jog]} **{jog.capitalize()}**\n"
                f"**Bot**: {EMOJI[bot_escolha]} **{bot_escolha.capitalize()}**\n\n"
            )
            msg += "🟨 **Empate!**" if r=="empate" else ("🟩 **Você venceu!**" if r=="jogador" else "🟥 **O bot venceu!**")
            await interaction.response.send_message(msg)
            return

        # sem parâmetro → abre botões
        view = EscolhaViewPPT(user_id=interaction.user.id, timeout=90)
        await interaction.response.defer(thinking=True)
        await interaction.edit_original_response(content="Escolha sua jogada:", view=view)
        try: view.message = await interaction.original_response()
        except Exception: pass

async def setup(bot: commands.Bot):
    await bot.add_cog(PPT(bot))
