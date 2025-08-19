# evtranslator/bot.py
from __future__ import annotations
import logging
import asyncio
import aiohttp
import discord
from discord.ext import commands
from .config import INTENTS, TEST_GUILD_ID, CONCURRENCY
from .db import init_db
from .webhook import WebhookSender

# importa os cogs
from .cogs.links import LinksCog
from .cogs.relay import RelayCog
from .cogs.events import EventsCog   # <-- novo cog
from .cogs.quota import Quota

class EVTranslatorBot(commands.Bot):
    def __init__(self, db_path: str):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.db_path = db_path
        self.sem = asyncio.Semaphore(CONCURRENCY)
        self.http_session: aiohttp.ClientSession | None = None
        self.webhooks: WebhookSender | None = None

    async def setup_hook(self) -> None:
        await init_db(self.db_path)
        self.http_session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"})
        self.webhooks = WebhookSender(bot_user_id=self.user.id)  # type: ignore[arg-type]

        # carregar cogs
        await self.add_cog(LinksCog(self))
        await self.add_cog(RelayCog(self))
        await self.add_cog(EventsCog(self))  # <-- adiciona aqui
        await self.add_cog(Quota(self))

        # sync slash
        try:
            if TEST_GUILD_ID:
                await self.tree.sync(guild=discord.Object(id=int(TEST_GUILD_ID)))
                logging.info("Slash sync (guild %s)", TEST_GUILD_ID)
            else:
                await self.tree.sync()
                logging.info("Slash sync (global)")
        except Exception as e:
            logging.warning("Slash sync failed: %s", e)

    async def close(self):
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()
