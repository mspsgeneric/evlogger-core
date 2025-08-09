from discord import app_commands
from discord.ext import commands
import discord

async def setup(bot: commands.Bot):
    @bot.tree.command(name="ajuda", description="Mostra todos os comandos disponíveis do EVlogger.")
    async def ajuda(interaction: discord.Interaction):
        embed = discord.Embed(
            title="📘 Comandos do EVlogger",
            description="Ferramentas para registrar, exportar e limpar cenas — e testes rápidos de jogada.",
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
                "O log será salvo e enviado antes da limpeza, se possível."
            ),
            inline=False
        )

        embed.add_field(
            name="👥 Comando para jogadores",
            value=(
                "**/obter_log**\n"
                "Envia por DM o log da cena atual (em `.txt`). Pode ser usado por qualquer membro com permissão de leitura no canal."
            ),
            inline=False
        )

        embed.add_field(
            name="🎮 Pedra, Papel, Tesoura e Bomba",
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
            name="⚙️ Outros comandos",
            value=(
                "**/gerar_evlog**\n"
                "Gera um arquivo `.evlog` com o conteúdo completo do canal atual.\n"
                "Inclui mensagens, anexos e imagens incorporadas.\n"
                "Use o programa **EVlogger Converter** para visualizar esse arquivo localmente com layout aprimorado."
            ),
            inline=False
        )

        embed.set_footer(text="Dúvidas ou sugestões? Fale com o criador do bot.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
