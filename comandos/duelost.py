# comandos/duelost.py
from __future__ import annotations
import asyncio
import hashlib
import secrets
from typing import Dict, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

# Reaproveita constantes e função de resultado do seu /duelo
# (ajuste o caminho do import se sua estrutura for diferente)
from .duelo import EMOJI, OPCOES_PPT, OPCOES_PPTB, WINS, resultado
from secrets import choice as randchoice


def _hash_commit(sinal_st: str, nonce: str) -> str:
    data = f"{sinal_st}|{nonce}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class EscolhaJogadorView(discord.ui.View):
    """View de escolha de jogada para um jogador específico.
    Pode ser enviada por DM ou no canal. Garante que apenas o jogador-alvo interaja.
    """
    def __init__(
        self,
        alvo: discord.abc.User,
        parent: "DuelosST",
        duelo_id: int,
        permitir_bomba: bool,
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self.alvo = alvo
        self.parent = parent
        self.duelo_id = duelo_id
        self.permitir_bomba = permitir_bomba
        self.escolha: str | None = None

        if not self.permitir_bomba:
            # remove botão da bomba se não for permitido
            for c in list(self.children):
                if isinstance(c, discord.ui.Button) and c.label == "Bomba":
                    self.remove_item(c)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # só o jogador-alvo pode clicar
        if interaction.user.id != self.alvo.id:
            await interaction.response.send_message("❌ Este painel não é para você.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.escolha is None:
            # Timeout → aleatório entre pedra/papel/tesoura (sem bomba)
            jogada = randchoice(OPCOES_PPT)
            await self.parent._registrar_jogada(self.duelo_id, self.alvo.id, jogada, aleatorio=True)
            # tentativa de avisar por DM; se falhar, ignora
            try:
                await self.alvo.send(
                    f"⏰ Tempo esgotado! Sua jogada foi escolhida aleatoriamente: {EMOJI[jogada]} {jogada.capitalize()}"
                )
            except Exception:
                pass

    async def _resolver(self, interaction: discord.Interaction, jogada: str):
        self.escolha = jogada
        await self.parent._registrar_jogada(self.duelo_id, self.alvo.id, jogada, aleatorio=False)
        # desabilita botões após escolher
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Sua jogada foi escolhida: {EMOJI[jogada]} {jogada.capitalize()}",
            view=self
        )

    @discord.ui.button(label="Pedra", style=discord.ButtonStyle.secondary, emoji="🪨")
    async def pedra(self, i: discord.Interaction, _: discord.ui.Button):
        await self._resolver(i, "pedra")

    @discord.ui.button(label="Papel", style=discord.ButtonStyle.secondary, emoji="📄")
    async def papel(self, i: discord.Interaction, _: discord.ui.Button):
        await self._resolver(i, "papel")

    @discord.ui.button(label="Tesoura", style=discord.ButtonStyle.secondary, emoji="✂️")
    async def tesoura(self, i: discord.Interaction, _: discord.ui.Button):
        await self._resolver(i, "tesoura")

    @discord.ui.button(label="Bomba", style=discord.ButtonStyle.danger, emoji="💣")
    async def bomba(self, i: discord.Interaction, _: discord.ui.Button):
        await self._resolver(i, "bomba")


class SelecionarUsuarios(discord.ui.View):
    """Seleção paginada mostrando apenas membros com acesso ao canal (sem bots)."""
    PER_PAGE = 25

    def __init__(
        self,
        channel: discord.TextChannel,
        candidatos: List[discord.Member],   # já filtrados por permissão e sem bots
        max_users: int = 50,
        timeout: float = 180.0,
    ):
        super().__init__(timeout=timeout)
        self.channel = channel
        self.max_users = max_users
        self.candidatos = candidatos
        self.page = 0
        self.selecionados_ids: set[int] = set()  # acumula seleção entre páginas
        self.selecionados: List[discord.Member] | None = None

        self._montar_pagina()

    def _limpar_itens(self):
        for c in list(self.children):
            self.remove_item(c)

    def _total_paginas(self) -> int:
        if not self.candidatos:
            return 1
        return (len(self.candidatos) + self.PER_PAGE - 1) // self.PER_PAGE

    def _montar_pagina(self):
        self._limpar_itens()

        inicio = self.page * self.PER_PAGE
        fim = inicio + self.PER_PAGE
        pagina = self.candidatos[inicio:fim]

        placeholder = (
            "Nenhum candidato" if not pagina
            else f"Página {self.page+1}/{self._total_paginas()} — selecione participantes…"
        )

        # Select de strings (discord.ui.Select)
        select = discord.ui.Select(
            placeholder=placeholder,
            min_values=0,
            max_values=max(1, len(pagina)),
        )
        for m in pagina:
            nome = (m.display_name or m.name)[:100]
            desc = f"@{m.name}"[:100]
            select.add_option(label=nome, value=str(m.id), description=desc)

        async def _on_select(i: discord.Interaction):
            # adiciona IDs selecionados nesta página
            for vid in i.data.get("values", []):
                self.selecionados_ids.add(int(vid))
            # só confirma a interação
            try:
                await i.response.defer()
            except Exception:
                pass

        select.callback = _on_select
        self.add_item(select)

        # Botões (criados dinamicamente)
        prev_disabled = (self.page == 0)
        next_disabled = (self.page >= self._total_paginas() - 1)

        prev_btn    = discord.ui.Button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary, disabled=prev_disabled)
        add_all_btn = discord.ui.Button(label="Selecionar todos desta página", style=discord.ButtonStyle.secondary)
        next_btn    = discord.ui.Button(label="Próxima ➡️", style=discord.ButtonStyle.secondary, disabled=next_disabled)
        confirm_btn = discord.ui.Button(label="Confirmar", style=discord.ButtonStyle.primary)
        cancel_btn  = discord.ui.Button(label="Cancelar", style=discord.ButtonStyle.secondary)


        async def _prev_cb(i: discord.Interaction):
            self.page -= 1
            try:
                await i.response.defer()
            except Exception:
                pass
            self._montar_pagina()
            await i.edit_original_response(view=self)

        async def _next_cb(i: discord.Interaction):
            self.page += 1
            try:
                await i.response.defer()
            except Exception:
                pass
            self._montar_pagina()
            await i.edit_original_response(view=self)

        async def _add_all_cb(i: discord.Interaction):
            for m in pagina:
                self.selecionados_ids.add(m.id)
            try:
                await i.response.defer()
            except Exception:
                pass

        async def _confirm_cb(i: discord.Interaction):
            if not self.selecionados_ids:
                await i.response.send_message("Selecione ao menos 1 participante.", ephemeral=True)
                return
            idset = set(self.selecionados_ids)
            membros: List[discord.Member] = []
            for m in self.candidatos:
                if m.id in idset and self.channel.permissions_for(m).view_channel:
                    membros.append(m)

            self.selecionados = membros[: self.max_users]
            # desativa tudo
            for c in self.children:
                if hasattr(c, "disabled"):
                    c.disabled = True
            await i.response.edit_message(
                content=f"✅ Participantes confirmados: {len(self.selecionados)}.",
                view=self
            )
            self.stop()

        async def _cancel_cb(i: discord.Interaction):
            self.selecionados = None
            for c in self.children:
                if hasattr(c, "disabled"):
                    c.disabled = True
            await i.response.edit_message(content="Operação cancelada.", view=self)
            self.stop()

        prev_btn.callback = _prev_cb
        next_btn.callback = _next_cb
        add_all_btn.callback = _add_all_cb
        confirm_btn.callback = _confirm_cb
        cancel_btn.callback = _cancel_cb

        self.add_item(prev_btn)
        self.add_item(add_all_btn)
        self.add_item(next_btn)
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)





class DuelosST(commands.Cog):
    """Duelos em massa: ST escolhe um sinal e vários jogadores respondem."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # mapeia id do duelo → estado
        self.duelos: Dict[int, Dict] = {}

    async def _registrar_jogada(self, duelo_id: int, user_id: int, jogada: str, aleatorio: bool):
        d = self.duelos.get(duelo_id)
        if not d:
            return
        d["escolhas"][user_id] = (jogada, aleatorio)
        # Se todos já responderam, dispara o Event
        if all(uid in d["escolhas"] for uid in d["participantes_ids"]):
            d["done"].set()

    async def _enviar_painel_para_jogador(
        self,
        interaction: discord.Interaction,
        duelo_id: int,
        membro: discord.Member,
        permitir_bomba: bool,
        timeout: float,
    ):
        """Tenta DM. Se falhar, publica no canal um painel endereçado ao jogador."""
        view = EscolhaJogadorView(membro, parent=self, duelo_id=duelo_id, permitir_bomba=permitir_bomba, timeout=timeout)
        # 1) tenta DM
        try:
            await membro.send(
                f"Escolha sua jogada no **DUELoST** contra o ST em {interaction.channel.mention}:",
                view=view
            )
            return
        except Exception:
            pass

        # 2) fallback: painel no canal, endereçado ao jogador
        try:
            await interaction.channel.send(
                f"{membro.mention} escolha sua jogada para o **DUELoST**:",
                view=view
            )
        except Exception:
            # Se até enviar no canal falhar, marca aleatório para este
            await self._registrar_jogada(duelo_id, membro.id, randchoice(OPCOES_PPT), aleatorio=True)

    def _formatar_resumo(
        self,
        sinal_st: str,
        participantes: List[discord.Member],
        escolhas: Dict[int, Tuple[str, bool]],
    ) -> Tuple[str, str]:
        """Retorna (texto_resumo, texto_detalhado)."""
        venceu, perdeu, empatou = [], [], []
        for m in participantes:
            jog, ale = escolhas.get(m.id, (randchoice(OPCOES_PPT), True))
            r = resultado(jog, sinal_st)
            entrada = f"{m.mention} ({EMOJI[jog]})" + (" *(aleatório)*" if ale else "")
            if r == "jogador1":  # jogador vence ST
                venceu.append(entrada)
            elif r == "jogador2":  # ST vence jogador
                perdeu.append(entrada)
            else:
                empatou.append(entrada)

        linhas_resumo = [
            f"**ST**: {EMOJI[sinal_st]} {sinal_st.capitalize()}",
            f"**Venceu ({len(venceu)})**: " + (", ".join(venceu) if venceu else "—"),
            f"**Perdeu ({len(perdeu)})**: " + (", ".join(perdeu) if perdeu else "—"),
            f"**Empatou ({len(empatou)})**: " + (", ".join(empatou) if empatou else "—"),
        ]
        texto_resumo = "⚔️ **Duelost — Todos vs ST**\n" + "\n".join(linhas_resumo)

        # Tabela detalhada linha a linha
        linhas_detalhe = ["\n**Detalhe por jogador**"]
        for m in participantes:
            jog, ale = escolhas.get(m.id, (randchoice(OPCOES_PPT), True))
            r = resultado(jog, sinal_st)
            if r == "jogador1":
                tag = "🟩 Venceu"
            elif r == "jogador2":
                tag = "🟥 Perdeu"
            else:
                tag = "🟨 Empatou"
            linhas_detalhe.append(
                f"- {m.mention}: {EMOJI[jog]} {jog.capitalize()}" + (" *(aleatório)*" if ale else "") + f" → {tag}"
            )
        texto_detalhado = "\n".join(linhas_detalhe)
        return texto_resumo, texto_detalhado

    
    @app_commands.command(
        name="duelost",
        description="Todos vs ST: o narrador escolhe um sinal, vários jogadores respondem (PPTB)."
    )
    @app_commands.describe(
        sinal_st="Sinal do ST (pedra, papel, tesoura, bomba).",
        tempo="Tempo (segundos) para respostas (padrão: 60).",
        permitir_bomba="Permitir que os jogadores escolham bomba (padrão: não).",
        detalhar="Incluir bloco detalhado por jogador (padrão: não).",
    )
    @app_commands.choices(
        sinal_st=[
            app_commands.Choice(name="Pedra 🪨", value="pedra"),
            app_commands.Choice(name="Papel 📄", value="papel"),
            app_commands.Choice(name="Tesoura ✂️", value="tesoura"),
            app_commands.Choice(name="Bomba 💣", value="bomba"),
        ]
    )
    @app_commands.choices(
        permitir_bomba=[
            app_commands.Choice(name="Sim", value="sim"),
            app_commands.Choice(name="Não", value="nao"),
        ],
        detalhar=[
            app_commands.Choice(name="Sim", value="sim"),
            app_commands.Choice(name="Não", value="nao"),
        ],
    )
    async def duelost(
        self,
        interaction: discord.Interaction,
        sinal_st: app_commands.Choice[str],
        tempo: int = 60,
        permitir_bomba: app_commands.Choice[str] | None = None,
        detalhar: app_commands.Choice[str] | None = None,
    ):
        # Restrições básicas
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Use em um canal de texto do servidor (não em thread/DM).", ephemeral=True)
            return

        # Permissão mínima: admin ou manage_guild (ajuste se quiser papel de Narrador)
        user = interaction.user
        assert isinstance(user, discord.Member)
        is_admin = user.guild_permissions.administrator or user.guild_permissions.manage_guild
        if not is_admin:
            await interaction.response.send_message("❌ Apenas administradores/gestores podem iniciar o Duelost.", ephemeral=True)
            return

        # Converte as choices “Sim/Não” em bool; padrão = Não (False)
        permitir_bomba_b = (permitir_bomba.value == "sim") if permitir_bomba else False
        detalhar_b       = (detalhar.value == "sim")       if detalhar       else False

        # === Selecionar participantes (sempre via seletor paginado) ===
        ch: discord.TextChannel = interaction.channel
        guild = interaction.guild

        # (opcional) tenta preencher o cache de membros
        fetch_ok = True
        try:
            async for _ in guild.fetch_members(limit=None):
                pass
        except Exception:
            fetch_ok = False  # provável: intent de membros desativada

        # 📌 Só quem PODE VER o canal (inclui offline)
        ids_vistos: set[int] = set()
        candidatos: List[discord.Member] = []

        # 1) os que o Discord já lista para o canal
        for m in ch.members:
            if m.bot:
                continue
            candidatos.append(m)
            ids_vistos.add(m.id)

        # 2) completa com offline que veem o canal
        for m in guild.members:
            if m.bot or m.id in ids_vistos:
                continue
            if ch.permissions_for(m).view_channel:
                candidatos.append(m)
                ids_vistos.add(m.id)

        # 3) se ainda ficou vazio, explica o motivo OU inclui ao menos o invocador
        if not candidatos:
            if not fetch_ok:
                await interaction.response.send_message(
                    "⚠️ Não consegui listar os membros do canal (provável: **Server Members Intent** desativado no bot ou no Dev Portal). "
                    "Ative a intenção de membros para incluir offline na seleção.",
                    ephemeral=True
                )
                return
            # fallback mínimo: permite selecionar o próprio narrador (pra teste)
            if not user.bot and ch.permissions_for(user).view_channel:
                candidatos = [user]
            else:
                await interaction.response.send_message(
                    "Não há membros humanos com acesso a este canal para selecionar.",
                    ephemeral=True
                )
                return

        view = SelecionarUsuarios(channel=ch, candidatos=candidatos, max_users=50, timeout=180.0)
        await interaction.response.send_message(
            "Selecione os participantes do Duelost e confirme:",
            view=view,
            ephemeral=True
        )

        timeout = await view.wait()
        if view.selecionados is None:
            await interaction.followup.send(
                "Operação cancelada." if not timeout else "Tempo esgotado ao selecionar participantes.",
                ephemeral=True
            )
            return

        participantes: List[discord.Member] = view.selecionados

        # Prepara estado do duelo (commit-reveal)
        duelo_id = interaction.id  # único por invocação
        nonce = secrets.token_urlsafe(16)
        st_move = sinal_st.value  # pedra/papel/tesoura/bomba
        commit_hash = _hash_commit(st_move, nonce)

        estado = {
            "guild_id": interaction.guild.id,
            "canal_id": interaction.channel.id,
            "st_id": user.id,
            "st_move": st_move,
            "nonce": nonce,
            "commit": commit_hash,
            "participantes_ids": [m.id for m in participantes],
            "escolhas": {},  # user_id -> (jogada, aleatorio: bool)
            "done": asyncio.Event(),
        }
        self.duelos[duelo_id] = estado

        # ⚠️ Agora use FOLLOWUP (response já foi usado acima)
        await interaction.followup.send(
            f"⚔️ **Duelost iniciado!** Participantes: {len(participantes)}\n"
            f"Tempo: {tempo}s\n"
            f"🔒 *Commit do sinal do ST:* `{commit_hash[:10]}…`",
        )

        # Dispara os painéis (DM ou fallback no canal)
        tasks = [
            self._enviar_painel_para_jogador(interaction, duelo_id, m, permitir_bomba_b, float(tempo))
            for m in participantes
        ]
        await asyncio.gather(*tasks)

        # Espera até todos responderem ou estourar o tempo
        try:
            await asyncio.wait_for(estado["done"].wait(), timeout=float(tempo))
        except asyncio.TimeoutError:
            pass  # completa abaixo

        # Completa quem não respondeu com aleatório P/P/T
        for uid in estado["participantes_ids"]:
            if uid not in estado["escolhas"]:
                estado["escolhas"][uid] = (randchoice(OPCOES_PPT), True)

        # Monta resumo
        texto_resumo, texto_detalhe = self._montar_resposta_formatada(
            st_move=estado["st_move"],
            participantes=participantes,
            escolhas=estado["escolhas"],
            commit=estado["commit"],
            nonce=estado["nonce"],
        )

        # Publica resultado final no canal
        if detalhar_b:
            await interaction.channel.send(texto_resumo)
            await interaction.channel.send(texto_detalhe)
        else:
            await interaction.channel.send(texto_resumo)

        # Limpa estado
        self.duelos.pop(duelo_id, None)


    def _montar_resposta_formatada(
        self,
        st_move: str,
        participantes: List[discord.Member],
        escolhas: Dict[int, Tuple[str, bool]],
        commit: str,
        nonce: str,
    ) -> Tuple[str, str]:
        # bloco resumo + bloco detalhado
        resumo, detalhado = self._formatar_resumo(st_move, participantes, escolhas)
        # adiciona reveal/commit check
        prova = f"\n\n🔓 **Reveal do ST**: {EMOJI[st_move]} {st_move.capitalize()}\n" \
                f"`sha256(\"{st_move}|{nonce}\") = {commit}`"
        return resumo + prova, detalhado

    def _formatar_resumo(
        self,
        sinal_st: str,
        participantes: List[discord.Member],
        escolhas: Dict[int, Tuple[str, bool]],
    ) -> Tuple[str, str]:
        return self._formatar_resumo_impl(sinal_st, participantes, escolhas)

    @staticmethod
    def _formatar_resumo_impl(
        sinal_st: str,
        participantes: List[discord.Member],
        escolhas: Dict[int, Tuple[str, bool]],
    ) -> Tuple[str, str]:
        venceu, perdeu, empatou = [], [], []
        for m in participantes:
            jog, ale = escolhas.get(m.id, (randchoice(OPCOES_PPT), True))
            r = resultado(jog, sinal_st)
            entrada = f"{m.mention} ({EMOJI[jog]})" + (" *(aleatório)*" if ale else "")
            if r == "jogador1":
                venceu.append(entrada)
            elif r == "jogador2":
                perdeu.append(entrada)
            else:
                empatou.append(entrada)

        resumo_linhas = [
            f"**ST**: {EMOJI[sinal_st]} {sinal_st.capitalize()}",
            f"**Venceu ({len(venceu)})**: " + (", ".join(venceu) if venceu else "—"),
            f"**Perdeu ({len(perdeu)})**: " + (", ".join(perdeu) if perdeu else "—"),
            f"**Empatou ({len(empatou)})**: " + (", ".join(empatou) if empatou else "—"),
        ]
        texto_resumo = "⚔️ **Duelost — Todos vs ST**\n" + "\n".join(resumo_linhas)

        detalhado_linhas = ["\n**Detalhe por jogador**"]
        for m in participantes:
            jog, ale = escolhas.get(m.id, (randchoice(OPCOES_PPT), True))
            r = resultado(jog, sinal_st)
            if r == "jogador1":
                tag = "🟩 Venceu"
            elif r == "jogador2":
                tag = "🟥 Perdeu"
            else:
                tag = "🟨 Empatou"
            detalhado_linhas.append(
                f"- {m.mention}: {EMOJI[jog]} {jog.capitalize()}" + (" *(aleatório)*" if ale else "") + f" → {tag}"
            )
        texto_detalhado = "\n".join(detalhado_linhas)
        return texto_resumo, texto_detalhado

async def setup(bot: commands.Bot):
    await bot.add_cog(DuelosST(bot))
