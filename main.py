import os
import asyncio
import csv
from discord.ext import commands
from discord import Intents
from dotenv import load_dotenv

# Carrega as variáveis do .env antes de qualquer uso
load_dotenv()

from util.supabase import get_supabase
supabase = get_supabase()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Lista de servidores autorizados (carregada do CSV)
SERVIDORES_AUTORIZADOS = {}

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


@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como {bot.user}")
    carregar_servidores_autorizados()

    await asyncio.sleep(3)  # evita corridas no início com muitos servidores

    for guild in bot.guilds:
        if guild.id not in SERVIDORES_AUTORIZADOS:
            print(f"🚫 Servidor não autorizado: {guild.name} ({guild.id}) — Saindo...")
            try:
                await guild.leave()
            except Exception as e:
                print(f"⚠️ Erro ao sair de {guild.name}: {e}")
        else:
            print(f"✅ Conectado ao servidor autorizado: {guild.name} ({guild.id})")

    try:
        synced = await bot.tree.sync()
        print(f"📤 {len(synced)} comandos de barra sincronizados.")
    except Exception as e:
        print(f"⚠️ Erro ao sincronizar comandos: {e}")


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



async def main():
    await load_commands()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
