import os
import asyncio
from discord.ext import commands
from discord import Intents
from dotenv import load_dotenv
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
import discord
from aiohttp import web
from painel.routes import setup_painel_routes


# ===================== LOGGING =====================

os.makedirs("logs", exist_ok=True)
log_filename = f"logs/evlogger_{datetime.now().strftime('%Y-%m')}.log"

file_handler = TimedRotatingFileHandler(
    filename=log_filename,
    when="midnight",
    interval=30,
    backupCount=24,
    encoding="utf-8",
)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
    handlers=[file_handler, logging.StreamHandler()]
)

# ===================== AMBIENTE =====================

ENV = os.getenv("APP_ENV", "prod")
if ENV == "dev":
    load_dotenv(".env.dev")
else:
    load_dotenv()


TEST_GUILD_ID = int(os.getenv("TEST_GUILD_ID", "0"))

TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_NAME = os.getenv("MAIL_NAME")

# ===================== DISCORD BOT =====================

intents = Intents.default()
intents.message_content = True
intents.guilds = True  # necessário para listar guilds e detectar rename

bot = commands.Bot(command_prefix="!", intents=intents)

from lembretes import setup as setup_lembretes
setup_lembretes(bot)

membro_cache = {}

# ===================== SUPABASE =====================

from util.supabase import get_supabase
supabase = get_supabase()

def _is_guild_registered(guild_id: int) -> bool:
    """Existe linha para este guild_id? Se sim, está autorizado."""
    try:
        r = supabase.table("emails").select("guild_id").eq("guild_id", str(guild_id)).limit(1).execute()
        return bool(r.data)
    except Exception as e:
        logging.warning(f"[supabase] erro ao consultar guild_id {guild_id}: {e}")
        # por segurança, trate como não autorizado em caso de erro
        return False

def _update_guild_name_if_registered(guild: discord.Guild) -> bool:
    """
    Atualiza guild_name APENAS se o guild_id já existir.
    Retorna True se existe (registrado), False se não existe.
    """
    try:
        if _is_guild_registered(guild.id):
            supabase.table("emails").update(
                {"guild_name": guild.name}
            ).eq("guild_id", str(guild.id)).execute()
            return True
        return False
    except Exception as e:
        logging.warning(f"[supabase] falha ao atualizar guild_name p/ {guild.id}: {e}")
        return False

def _bulk_update_guild_names_strict(bot_: commands.Bot) -> int:
    """
    Atualiza guild_name para todos os servidores atuais, SOMENTE se já existirem.
    Retorna quantos foram atualizados.
    """
    updated = 0
    for g in bot_.guilds:
        try:
            if _is_guild_registered(g.id):
                supabase.table("emails").update(
                    {"guild_name": g.name}
                ).eq("guild_id", str(g.id)).execute()
                updated += 1
        except Exception as e:
            logging.warning(f"[supabase] falha ao atualizar nome em bulk p/ {g.id}: {e}")
    return updated

# ===================== EVTranslator (helpers mínimos) =====================

async def init_translator_runtime():
    """Inicializa recursos usados pelos cogs do EVTranslator (DB, sessão HTTP, semáforo)."""
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

# ===================== API de verificação =====================

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

# ===================== JOB DIÁRIO (bylaws) =====================

def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()

async def bylaws_daily_job(hour=3, minute=17, run_immediately=False):
    if run_immediately:
        try:
            from bylaws.fetch_character import main as fetch_main
            code = fetch_main()
            print(f"[bylaws] job (imediato) terminou com código {code}")
        except Exception as e:
            print(f"[bylaws] erro inesperado (imediato): {e}")

    await asyncio.sleep(_seconds_until(hour, minute))

    while True:
        try:
            from bylaws.fetch_character import main as fetch_main
            code = fetch_main()
            print(f"[bylaws] job diário terminou com código {code}")
        except Exception as e:
            print(f"[bylaws] erro inesperado no job diário: {e}")
        await asyncio.sleep(24 * 60 * 60)

# ===================== EVENTOS DO BOT =====================

@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")

    # Inicializa o WebhookSender usado pelo tradutor (somente após login)
    try:
        if not hasattr(bot, "webhooks") or getattr(bot, "webhooks", None) is None:
            from evtranslator.webhook import WebhookSender
            bot.webhooks = WebhookSender(bot_user_id=bot.user.id)  # type: ignore[attr-defined]
    except Exception as e:
        logging.warning(f"Falha ao inicializar WebhookSender: {e}")

    await asyncio.sleep(3)  # evita corridas no início com muitos servidores

    if ENV != "dev":
        # 1) Atualiza NOME dos servidores cadastrados (modo estrito: só se já existirem)
        def _run_bulk():
            updated = _bulk_update_guild_names_strict(bot)
            logging.info(f"[supabase] guild_name atualizado em {updated} servidores (modo estrito)")
        await bot.loop.run_in_executor(None, _run_bulk)

        # 2) Sai de servidores que não têm registro no Supabase
        for guild in bot.guilds:
            def _check():
                return _is_guild_registered(guild.id)
            ok = await bot.loop.run_in_executor(None, _check)
            if not ok:
                print(f"🚫 Sem registro no Supabase: {guild.name} ({guild.id}) — Saindo...")
                try:
                    await guild.leave()
                except Exception as e:
                    print(f"⚠️ Erro ao sair de {guild.name}: {e}")
            else:
                print(f"✅ Autorizado (Supabase): {guild.name} ({guild.id})")
    else:
        print("🔧 DEV: pulando checagem de servidores autorizados (Supabase).")

    # Sync de comandos
    try:
        if ENV == "dev" and TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"📤 {len(synced)} comandos de barra (DEV) sincronizados no guild {TEST_GUILD_ID}.")
        else:
            synced = await bot.tree.sync()
            print(f"📤 {len(synced)} comandos de barra sincronizados globalmente.")
    except Exception as e:
        print(f"⚠️ Erro ao sincronizar comandos: {e}")

    # API de verificação
    async def iniciar_api_verificacao():
        app = web.Application()
        app.router.add_post("/verificar_acesso", verificar_acesso)

        # injeta o cliente supabase já criado no main
        setup_painel_routes(app, supabase)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8937)
        await site.start()
        print("🔐 API pública: http://0.0.0.0:8937/verificar_acesso")
        print("🛠️ Painel admin: http://0.0.0.0:8937/admin/guilds")

    asyncio.create_task(iniciar_api_verificacao())

    # Agenda o fetch/parse diário (03:17)
    if not getattr(bot, "_bylaws_job_started", False):
        asyncio.create_task(bylaws_daily_job(hour=3, minute=17, run_immediately=False))
        bot._bylaws_job_started = True

@bot.event
async def on_guild_join(guild):
    print(f"📥 Bot foi adicionado ao servidor: {guild.name} ({guild.id})")

    # MODO ESTRITO:
    # 1) Checa se existe registro; 2) se existir, atualiza o nome; 3) se não, sai.
    def _check_and_update():
        if _is_guild_registered(guild.id):
            try:
                supabase.table("emails").update(
                    {"guild_name": guild.name}
                ).eq("guild_id", str(guild.id)).execute()
            except Exception as e:
                logging.warning(f"[supabase] falha ao atualizar nome no join p/ {guild.id}: {e}")
            return True
        return False

    ok = await bot.loop.run_in_executor(None, _check_and_update)

    if not ok:
        print(f"🚫 Sem registro no Supabase (on_guild_join): {guild.name} ({guild.id}) — Saindo...")
        try:
            owner = await bot.fetch_user(guild.owner_id)
            await owner.send(
                f"❌ O bot **{bot.user.name}** não está autorizado para uso neste servidor.\n"
                f"Peça ao administrador para cadastrar o **guild_id** `{guild.id}` no painel."
            )
        except Exception as e:
            print(f"⚠️ Não foi possível enviar DM ao dono do servidor: {e}")
        await guild.leave()
    else:
        print(f"✅ Novo servidor autorizado (Supabase): {guild.name} ({guild.id})")

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    # Mantém guild_name sincronizado apenas se já houver registro (modo estrito)
    if before.name != after.name:
        def _update_if_registered():
            if _is_guild_registered(after.id):
                try:
                    supabase.table("emails").update({"guild_name": after.name}).eq("guild_id", str(after.id)).execute()
                    return True
                except Exception as e:
                    logging.warning(f"[supabase] falha ao atualizar nome p/ {after.id}: {e}")
            return False
        changed = await bot.loop.run_in_executor(None, _update_if_registered)
        if changed:
            logging.info(f"[supabase] guild_name sincronizado: {before.name} -> {after.name} ({after.id})")

# ===================== COMANDOS / COGS =====================

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

# ===================== MAIN =====================

async def main():
    await load_commands()
    # ====== EVTranslator: inicializa runtime + registra cogs ======
    await init_translator_runtime()
    await load_translator_cogs()
    # =============================================================
    try:
        await bot.start(TOKEN)
    finally:
        session = getattr(bot, "http_session", None)
        if session is not None and not session.closed:
            await session.close()

if __name__ == "__main__":
    asyncio.run(main())
