from discord import app_commands, Interaction
from discord.ext import commands
from util.supabase import get_supabase
import logging, re

supabase = get_supabase()

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def apenas_admin():
    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message(
            "🚫 Você precisa ser administrador para usar este comando.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)

async def setup(bot: commands.Bot):
    @bot.tree.command(
        name="definir_email",
        description="Define o e-mail para receber logs (somente administradores)"
    )
    @app_commands.guild_only()
    @app_commands.describe(email="E-mail para receber logs neste servidor")
    @apenas_admin()
    async def definir_email(interaction: Interaction, email: str):
        logger.info("Comando /definir_email acionado")

        # validação simples de e-mail
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            await interaction.response.send_message("❌ E-mail inválido.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        try:
            # 1) MODO ESTRITO: verificar se já existe registro
            res = supabase.table("emails").select("guild_id").eq("guild_id", guild_id).maybe_single().execute()
            row = res.data

            if not row:
                # NÃO cria. Exige cadastro prévio via painel/db
                await interaction.response.send_message(
                    "🚫 Este servidor ainda **não está autorizado**. "
                    "Peça ao administrador do sistema para cadastrar o `guild_id` no painel.",
                    ephemeral=True
                )
                return

            # 2) UPDATE (não cria)
            update_payload = {
                "email": email,
                # opcional: manter o nome sincronizado quando o admin usar o comando
                "guild_name": interaction.guild.name
            }
            supabase.table("emails").update(update_payload).eq("guild_id", guild_id).execute()

            logger.info(
                f"[EMAIL CONFIGURADO] '{email}' por {interaction.user} "
                f"(user_id={interaction.user.id}) no servidor '{interaction.guild.name}' (guild_id={guild_id})"
            )

            await interaction.response.send_message(
                f"📬 E-mail definido como: {email}",
                ephemeral=True
            )

        except Exception as e:
            logger.error("Erro ao definir e-mail", exc_info=True)
            # cuidado: Interaction só pode responder uma vez; se já respondeu acima, use followup.
            if interaction.response.is_done():
                await interaction.followup.send("❌ Erro ao definir e-mail.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Erro ao definir e-mail.", ephemeral=True)
