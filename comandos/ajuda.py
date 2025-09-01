from discord import app_commands
from discord.ext import commands
import discord

ALLOWED_NONE = discord.AllowedMentions.none()

async def setup(bot: commands.Bot):
    @bot.tree.command(name="ajuda", description="Mostra os comandos disponíveis do EVlogger.")
    async def ajuda(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📘 Comandos do EVlogger",
            description="Ferramentas para registrar, exportar e limpar cenas — e mini-jogos rápidos.",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🔐 Comandos para administradores",
            value=(
                "**/definir_email [email]**\n"
                "Define o e-mail que receberá os logs das cenas deste servidor.\n\n"
                "**/mostrar_email**\n"
                "Mostra o e-mail atualmente configurado para envio de logs.\n\n"
                "**/encerrar_cena**\n"
                "Salva o log da cena atual, envia por e-mail (caso configurado) e também por DM em formato `.txt`.\n\n"
                "**/limpar_canal**\n"
                "⚠️ 'Limpa' o canal atual.\n"
                "O log será salvo e enviado antes da limpeza, como em encerrar cena.\n\n"
                "**/arquivar_canal**\n"
                "⚠️ Arquiva (apaga/exclui) o canal atual **permanentemente**.\n"
                "O log será salvo e enviado antes da exclusão, como em encerrar cena."
            ),
            inline=False
        )

        embed.add_field(
            name="👥 Comandos para jogadores",
            value=(
                "**/obter_log**\n"
                "Envia por DM o log da cena atual (em `.txt`). Pode ser usado por qualquer membro com permissão de leitura no canal.\n"
                "• A retirada é registrada **no próprio canal** de forma **anônima** (sem expor quem pediu).\n\n"
                "**/check**\n"
                "Mostra **só para você** as datas e horas em que **você** baixou o log **neste canal**.\n"
                "• Não revela retiradas de outras pessoas.\n"
                "• Se você ainda não retirou nenhum log deste canal, o bot informa isso claramente.\n\n"
                "**/wiki [nome do personagem]**\n"
                "Busca na **Wiki da OWBN**. Retorna resultados resumidos com link direto para a página do personagem.\n"
                "• Exemplo: `/wiki João`\n\n"
                "**/custom [termo]**\n"
                "Consulta a base de conteudo custom.\n"
                "• Exemplo: `/custom nome | erato`"
            ),
            inline=False
        )


        # MINI-JOGOS
        embed.add_field(
            name="🎮 Mini-jogos: Pedra, Papel, Tesoura e Bomba",
            value="Diversão rápida no chat ou em duelo PvP.",
            inline=False
        )

        embed.add_field(
            name="🧑‍🤝‍🧑 Modos Solo (você vs Bot)",
            value=(
                "**/ppt [escolha]**\n"
                "Pedra, Papel e Tesoura **(sem bomba)**.\n"
                "• Sem parâmetro → abre botões.\n"
                "• Com parâmetro → resolve direto. Opções: `pedra`, `papel`, `tesoura`, `aleatoria` (sorteia entre PPT).\n\n"
                "**/pptb [escolha]**\n"
                "Pedra, Papel, Tesoura e **Bomba**.\n"
                "• Sem parâmetro → abre botões.\n"
                "• Com parâmetro → resolve direto. Opções: `pedra`, `papel`, `tesoura`, `bomba`, `aleatoria` (pode sair 💣)."
            ),
            inline=False
        )

        embed.add_field(
            name="🤼 Modos PvP (jogador vs jogador)",
            value=(
                "**/pptbd @PC1 @PC2 [PC 1 Bomba] [PC 2 Bomba]**\n"
                "Duelo rápido (resultado imediato, sorteio feito pelo bot).\n"
                "• **PC 1 Bomba / PC 2 Bomba** → escolha: 🚫 Sem bomba (padrão) ou 💣 Com bomba.\n"
                "• Exemplo:\n"
                "```/pptbd @Jogador1 @Jogador2 (PC 1 Bomba: 🚫 Sem bomba) (PC 2 Bomba: 💣 Com bomba)```\n\n"
                "**/duelo @PC1 @PC2 [PC 1 Bomba] [PC 2 Bomba]**\n"
                "Duelo interativo por **DM** (cada jogador escolhe sua jogada com botões).\n"
                "• Tempo limite: 60s (se não escolher, sai jogada aleatória e o bot avisa por DM).\n"
                "• Resultado é revelado no canal onde o comando foi chamado.\n"
                "• Exemplo:\n"
                "```/duelo @Jogador1 @Jogador2 (PC 1 Bomba: 💣 Com bomba) (PC 2 Bomba: 🚫 Sem bomba)```"
            ),
            inline=False
        )

        embed.add_field(
            name="⚙️ Outros comandos",
            value=(
                "**/gerar_evlog**\n"
                "Gera um arquivo `.evlog` com o conteúdo completo do canal atual.\n"
                "Inclui mensagens, anexos e imagens incorporadas.\n"
                "Use o programa **EVlogger Converter** para visualizar esse arquivo localmente com layout aprimorado.\n\n"
                "**/blc (EXPERIMENTAL)**\n"
                "Consulta ao Bylaws Character.\n"
                "Dicas: use **aspas** para frases, `-termo` para excluir, filtros `pc:notify`, `npc:approval`, `coord:wraith`,\n"
                "e `foo|bar` para OR. Exemplos: `\"true brujah\"`, `brujah 4`, `kiasyd -ritual`, `brujah|tremere pc:approval`."
            ),
            inline=False
        )

        embed.set_footer(text="Dúvidas ou sugestões? Fale com o criador do bot.")
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=ALLOWED_NONE)
