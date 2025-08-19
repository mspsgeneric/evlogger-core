# evtranslator/cogs/events.py
from __future__ import annotations
import logging
import discord
from discord.ext import commands
from evtranslator.db import unlink_pair
from evtranslator.config import DB_PATH

class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.TextChannel):
            return
        guild_id = channel.guild.id
        ch_id = channel.id
        await unlink_pair(DB_PATH, guild_id, ch_id, ch_id)
        logging.info(f"🔗 Canal deletado {channel.name} removido dos links")
