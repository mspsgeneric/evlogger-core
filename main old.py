import os
import asyncio
import csv
from discord.ext import commands
from discord import Intents
from dotenv import load_dotenv
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import discord
from datetime import timedelta  # você já importa datetime acima

# Cria a pasta de logs se não existir
os.makedirs("logs", exist_ok=True)

# Define o arquivo de log baseado no mês atual
log_filename = f"logs/evlogger_{datetime.now().strftime('%Y-%m')}.log"

# Configura o logger com rotação mensal e retenção de 24 arquivos (~2 anos)
file_handler = TimedRotatingFileHandler(
    filename=log_filename,
    when="midnight",
    interval=30,
    backupCount=24,
    encoding="utf-8"
)

# Aplica a configuração global de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()  # Mantém a exibição no tmux
    ]
)

from aiohttp import web

# Carrega as variáveis de ambiente por ambiente (prod x dev)
ENV = os.getenv("APP_ENV", "prod")
if ENV == "dev":
    load_dotenv(".env.dev")
else:
    load_dotenv()
TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

from util.db_supabase import get_supabase
supabase = get_supabase()

TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_NAME = os.getenv("MAIL_NAME")

intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
from lembretes import setup
setup(bot)

# Lista de servidores autorizados (carregada do CSV)
SERVIDORES_AUTORIZADOS = {}

# Fora da função, crie um cache simples por tempo curto (duração da execução):
membro_cache = {}

# ====== EVTranslator: helpers mínimos ======
async def init_translator_runtime():
    """Inicializa recursos usados pelos cogs do EVTranslator (DB, sessão HTTP, semáforo)."""
    # init DB do EVTranslator
    from evtranslator.config import DB_PATH, CONCURRENCY
    from evtranslator.db import init_db
    import aiohttp

    await init_db(DB_PATH)
    bot.sem = asyncio.Semaphore(CONCURRENCY)
    bot.http_session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"})

async def load_translator_cogs():
    """Registra os cogs do EVTranslator sem mexer na arquitetura do EVLogger."""
    from evtranslator.cogs.links import LinksCog
    from evtranslator.cogs.relay import RelayCog
    from evtranslator.cogs.events import EventsCog
    from evtranslator.cogs.quota import Quota

    await bot.add_cog(LinksCog(bot))
    await bot.add_cog(RelayCog(bot))
    await bot.add_cog(EventsCog(bot))
    await bot.add_cog(Quota(bot))
# ===========================================

async def verificar_acesso(request):
    try:
        data = await request.json()
        canal_id = int(data.get("canal_id"))
        usuario_id = int(data.get("usuario_id"))
        canal = bot.get_channel(canal_id)

        if canal is None:
            print(f"❌ Canal {canal_id} não encontrado.")
            return web.json_response({"acesso": False, "erro": "Canal não encontrado"})

        guild = canal.guild
        cache_key = (guild.id, usuario_id)

        if cache_key in membro_cache:
            membro = membro_cache[cache_key]
        else:
            membro = guild.get_member(usuario_id)
            if membro is None:
                try:
                    print(f"🔍 Buscando membro {usuario_id} no servidor {guild.name}...")
                    membro = await guild.fetch_member(usuario_id)
                except Exception as e:
                    print(f"❌ Não foi possível buscar o membro {usuario_id}: {e}")
                    return web.json_response({"acesso": False, "erro": "Usuário não encontrado"})

            membro_cache[cache_key] = membro

        perms = canal.permissions_for(membro)
        print(f"🔐 Permissão de leitura do usuário {usuario_id} no canal {canal_id}: {perms.read_messages}")

        return web.json_response({"acesso": perms.read_messages})

    except Exception as e:
        print(f"❌ Erro na verificação de acesso: {e}")
        return web.json_response({"acesso": False, "erro": str(e)})

def carregar_servidores_autorizados():
    global SERVIDORES_AUTORIZADOS
    SERVIDORES_AUTORIZADOS.clear()

    ids_autorizados = set()

    try:
        with open("servidores_autorizados.csv", newline='', encoding='utf-8') as csvfile:
            leitor = csv.DictReader(csvfile)

            for linha in leitor:
                try:
                    id_str = linha["id"].strip()
                    nome = linha["nome"].strip()
                    SERVIDORES_AUTORIZADOS[int(id_str)] = nome
                    ids_autorizados.add(id_str)  # IDs como string
                except ValueError:
                    print(f"⚠️ ID inválido na linha: {linha}")

            print(f"📄 IDs autorizados carregados do CSV: {ids_autorizados}")

    except FileNotFoundError:
        print("❌ Arquivo servidores_autorizados.csv não encontrado!")
        return

    # Buscar registros no Supabase
    resposta = supabase.table("emails").select("guild_id").execute()
    print(f"📦 Resposta bruta do Supabase: {resposta}")

    if hasattr(resposta, "error") and resposta.error:
        print(f"❌ Erro ao buscar registros do Supabase: {resposta.error}")
        return

    registros = resposta.data or []
    print(f"🔍 Verificando registros do Supabase... Total: {len(registros)}")

    if not registros:
        print("⚠️ Nenhum registro encontrado no Supabase.")
        return

    # Obtem a lista de IDs do Supabase que devem ser mantidos
    ids_a_manter = set(ids_autorizados)  # strings

    # Itera sobre os registros do Supabase
    for i, registro in enumerate(registros):
        guild_id_supabase = str(registro.get("guild_id", "")).strip()
        print(f"➡️ Registro {i}: {guild_id_supabase}")

        if guild_id_supabase not in ids_a_manter:
            print(f"🧹 Deletando: {guild_id_supabase}")
            deletar = supabase.table("emails").delete().eq("guild_id", guild_id_supabase).execute()
            if hasattr(deletar, "error") and deletar.error:
                print(f"❌ Erro ao deletar {guild_id_supabase}: {deletar.error}")
            else:
                print(f"✅ Supabase: guild_id {guild_id_supabase} removido com sucesso")
        else:
            print(f"🔐 Supabase: guild_id {guild_id_supabase} autorizado — mantido.")

# --- agendamento diário do fetch/parse de bylaws ---


def _seconds_until(hour: int, minute: int) -> float:
    """Segundos até a próxima ocorrência de HH:MM (hora do servidor)."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()

async def bylaws_daily_job(hour=3, minute=17, run_immediately=False):
    """
    Executa bylaws.fetch_character uma vez por dia.
    - hour/minute: horário do servidor (24h)
    - run_immediately=True: roda uma vez agora ao subir o bot
    """
    if run_immediately:
        try:
            from bylaws.fetch_character import main as fetch_main
            code = fetch_main()
            print(f"[bylaws] job (imediato) terminou com código {code}")
        except Exception as e:
            print(f"[bylaws] erro inesperado (imediato): {e}")

    # aguarda até o próximo HH:MM
    await asyncio.sleep(_seconds_until(hour, minute))

    while True:
        try:
            from bylaws.fetch_character import main as fetch_main
            code = fetch_main()  # 0=ok/sem mudança, 2=site fora etc. (não explode)
            print(f"[bylaws] job diário terminou com código {code}")
        except Exception as e:
            print(f"[bylaws] erro inesperado no job diário: {e}")
        # espera 24h
        await asyncio.sleep(24 * 60 * 60)
# --- fim helpers agendamento ---





@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")
    carregar_servidores_autorizados()

    # Inicializa o WebhookSender usado pelo tradutor (somente após login)
    try:
        if not hasattr(bot, "webhooks") or getattr(bot, "webhooks", None) is None:
            from evtranslator.webhook import WebhookSender
            bot.webhooks = WebhookSender(bot_user_id=bot.user.id)  # type: ignore[attr-defined]
    except Exception as e:
        logging.warning(f"Falha ao inicializar WebhookSender: {e}")

    await asyncio.sleep(3)  # evita corridas no início com muitos servidores

    if ENV != "dev":
        for guild in bot.guilds:
            if guild.id not in SERVIDORES_AUTORIZADOS:
                print(f"🚫 Servidor não autorizado: {guild.name} ({guild.id}) — Saindo...")
                try:
                    await guild.leave()
                except Exception as e:
                    print(f"⚠️ Erro ao sair de {guild.name}: {e}")
            else:
                print(f"✅ Conectado ao servidor autorizado: {guild.name} ({guild.id})")
    else:
        print("🔧 DEV: pulando checagem de servidores autorizados.")

    try:
        if ENV == "dev" and TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            # 👇 copia os comandos globais carregados pelos cogs para o servidor de teste
            bot.tree.copy_global_to(guild=guild)
            # 👇 sincroniza no guild (aparece na hora)
            synced = await bot.tree.sync(guild=guild)
            print(f"📤 {len(synced)} comandos de barra (DEV) sincronizados no guild {TEST_GUILD_ID}.")
        else:
            # produção: sync global (pode levar alguns minutos até 1h para propagar no Discord)
            synced = await bot.tree.sync()
            print(f"📤 {len(synced)} comandos de barra sincronizados globalmente.")
    except Exception as e:
        print(f"⚠️ Erro ao sincronizar comandos: {e}")

    async def iniciar_api_verificacao():
        app = web.Application()
        app.router.add_post("/verificar_acesso", verificar_acesso)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8937)
        await site.start()
        print("🔐 API pública de verificação iniciada em http://0.0.0.0:8937")

    # Dentro do on_ready, após os prints e sync:
    asyncio.create_task(iniciar_api_verificacao())

    # Agenda o fetch/parse diário (03:17, hora do servidor). Evita agendar 2x em reconexões.
    if not getattr(bot, "_bylaws_job_started", False):
        asyncio.create_task(bylaws_daily_job(hour=3, minute=17, run_immediately=False))
        bot._bylaws_job_started = True



@bot.event
async def on_guild_join(guild):
    print(f"📥 Bot foi adicionado ao servidor: {guild.name} ({guild.id})")
    carregar_servidores_autorizados()

    if guild.id not in SERVIDORES_AUTORIZADOS:
        print(f"🚫 Servidor não autorizado (on_guild_join): {guild.name} ({guild.id}) — Saindo...")
        try:
            owner = await bot.fetch_user(guild.owner_id)
            await owner.send(
                f"❌ O bot **{bot.user.name}** não está autorizado para uso neste servidor.\n"
                f"Se você acredita que isso é um erro, entre em contato com o administrador."
            )
        except Exception as e:
            print(f"⚠️ Não foi possível enviar DM ao dono do servidor: {e}")

        await guild.leave()
    else:
        print(f"✅ Novo servidor autorizado: {guild.name} ({guild.id})")

async def load_commands():
    await bot.load_extension("comandos.definir_email")
    await bot.load_extension("comandos.mostrar_email")
    await bot.load_extension("comandos.encerrar_cena")
    await bot.load_extension("comandos.limpar_cena")
    await bot.load_extension("comandos.ajuda")
    await bot.load_extension("comandos.obter_log")
    await bot.load_extension("comandos.gerar_evlog")
    await bot.load_extension("comandos.arquivar_canal")
    await bot.load_extension("comandos.pptb")
    await bot.load_extension("comandos.ppt")
    await bot.load_extension("comandos.blc_bylaws")
    await bot.load_extension("comandos.check")

async def main():
    await load_commands()
    # ====== EVTranslator: inicializa runtime + registra cogs ======
    await init_translator_runtime()
    await load_translator_cogs()
    # =============================================================
    try:
        await bot.start(TOKEN)
    finally:
        # encerra sessão HTTP do tradutor com elegância (se criada)
        session = getattr(bot, "http_session", None)
        if session is not None and not session.closed:
            await session.close()

if __name__ == "__main__":
    asyncio.run(main())
