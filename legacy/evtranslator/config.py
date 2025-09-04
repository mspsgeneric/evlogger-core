from __future__ import annotations
import os
from dotenv import load_dotenv
import discord

# Carrega .env (separado por ambiente)
load_dotenv()

# Token do Discord (tradutor)
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise SystemExit("❌ Missing DISCORD_TOKEN in env")

# Banco de dados (SQLite usado pelos links)
DB_PATH = os.environ.get("EVLOGGER_DB", "evlogger_links.sqlite")

# Configuração de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("❌ Missing SUPABASE_URL / SUPABASE_KEY in env")

# Tunables
CONCURRENCY = int(os.environ.get("CONCURRENCY", "6"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "15"))
RETRIES = int(os.environ.get("RETRIES", "4"))
BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "0.5"))
CHANNEL_COOLDOWN_SEC = float(os.environ.get("CHANNEL_COOLDOWN", "0.15"))
USER_COOLDOWN_SEC = float(os.environ.get("USER_COOLDOWN", "2.0"))

TEST_GUILD_ID = os.environ.get("TEST_GUILD_ID")

TRANSLATED_FLAG = "\u200b"  # marcador invisível
MIN_MSG_LEN = 4
MAX_MSG_LEN = 2000

# Intents básicos (mensagens de texto)
INTENTS = discord.Intents.default()
INTENTS.message_content = True
