# comandos/duelo.py
from secrets import choice as randchoice
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

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

class EscolhaDM(discord.ui.View):
    def __init__(self, user: discord.User, parent, opcoes: tuple[str], timeout: float = 60):
        super().__init__(timeout=timeout)
        self.user = user
        self.parent = parent
        self.opcoes = opcoes
        self.escolha: str | None = None

        # Remove botão de bomba se não for permitido
        if "bomba" not in self.opcoes:
            for c in self.children:
                if isinstance(c, discord.ui.Button) and c.label == "Bomba":
                    self.remove_item(c)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def on_timeout(self):
        if self.escolha is None:
            jogada = randchoice(self.opcoes)
            self.parent.finalizar_jogada(self.user.id, jogada, aleatorio=True)
            try:
                await self.user.send(
                    f"⏰ Tempo esgotado! Sua jogada foi escolhida aleatoriamente: {EMOJI[jogada]} {jogada.capitalize()}"
                )
            except Exception:
                pass

    async def _resolver(self, interaction: discord.Interaction, jogada: str):
        self.escolha = jogada
        self.parent.finalizar_jogada(self.user.id, jogada, aleatorio=False)
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Sua jogada foi escolhida: {EMOJI[jogada]} {jogada.capitalize()}",
            view=self
        )

    @discord.ui.button(label="Pedra", style=discord.ButtonStyle.secondary, emoji="🪨")
    async def pedra(self, i, _): await self._resolver(i, "pedra")

    @discord.ui.button(label="Papel", style=discord.ButtonStyle.secondary, emoji="📄")
    async def papel(self, i, _): await self._resolver(i, "papel")

    @discord.ui.button(label="Tesoura", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def tesoura(self, i, _): await self._resolver(i, "tesoura")

    @discord.ui.button(label="Bomba", style=discord.ButtonStyle.danger, emoji="💣")
    async def bomba(self, i, _): await self._resolver(i, "bomba")

class Duelo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.partidas = {}  # {id_interaction: {"j1":..., "j2":..., "escolhas":{user_id:(jogada,aleatorio)}}}

    def finalizar_jogada(self, user_id: int, jogada: str, aleatorio: bool = False):
        for partida in self.partidas.values():
            if user_id in (partida["j1"].id, partida["j2"].id):
                partida["escolhas"][user_id] = (jogada, aleatorio)

    @app_commands.command(
        name="duelo",
        description="Inicia um duelo PvP em DM (pedra/papel/tesoura, com opção de bomba)."
    )
    @app_commands.describe(
        jogador1="Jogador 1",
        jogador2="Jogador 2",
        jogador1_b="Digite 'b' se o Jogador 1 pode usar bomba",
        jogador2_b="Digite 'b' se o Jogador 2 pode usar bomba",
    )
    async def duelo(
        self,
        interaction: discord.Interaction,
        jogador1: discord.User,
        jogador2: discord.User,
        jogador1_b: str = "",
        jogador2_b: str = "",
    ):
        if jogador1.id == jogador2.id:
            await interaction.response.send_message("⚠️ Os jogadores devem ser diferentes.", ephemeral=True)
            return

        partida = {"j1": jogador1, "j2": jogador2, "escolhas": {}}
        self.partidas[interaction.id] = partida

        await interaction.response.send_message(
            f"🎮 Duelo iniciado entre {jogador1.mention} e {jogador2.mention}! Jogadas serão escolhidas por DM."
        )

        # opções de cada jogador
        opcoes_j1 = OPCOES_PPTB if jogador1_b.lower() == "b" else OPCOES_PPT
        opcoes_j2 = OPCOES_PPTB if jogador2_b.lower() == "b" else OPCOES_PPT

        # Envia DMs
        for jogador, opcoes, outro in (
            (jogador1, opcoes_j1, jogador2),
            (jogador2, opcoes_j2, jogador1),
        ):
            try:
                view = EscolhaDM(jogador, parent=self, opcoes=opcoes)
                await jogador.send(
                    f"Escolha sua jogada no duelo contra {outro.mention}:",
                    view=view
                )
            except Exception:
                await interaction.followup.send(f"❌ Não consegui enviar DM para {jogador.mention}.", ephemeral=True)

        # espera 60s
        await asyncio.sleep(60)

        # resolve duelo (preenche com aleatório quem não jogou)
        jog1, ale1 = partida["escolhas"].get(jogador1.id, (randchoice(opcoes_j1), True))
        jog2, ale2 = partida["escolhas"].get(jogador2.id, (randchoice(opcoes_j2), True))

        r = resultado(jog1, jog2)

        texto = (
            f"👤 {jogador1.mention}: {EMOJI[jog1]} {jog1.capitalize()}{' (aleatório)' if ale1 else ''}\n"
            f"👤 {jogador2.mention}: {EMOJI[jog2]} {jog2.capitalize()}{' (aleatório)' if ale2 else ''}\n\n"
        )

        if r == "empate":
            texto += "🟨 **Empate!**"
        elif r == "jogador1":
            texto += f"🟩 **{jogador1.mention} venceu!**"
        else:
            texto += f"🟥 **{jogador2.mention} venceu!**"

        await interaction.followup.send(texto)
        del self.partidas[interaction.id]

async def setup(bot: commands.Bot):
    await bot.add_cog(Duelo(bot))
