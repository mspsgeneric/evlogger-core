from __future__ import annotations
import time
import asyncio
import logging
import discord
from discord.ext import commands

from evtranslator.config import (
    DB_PATH,
    TRANSLATED_FLAG,
    MIN_MSG_LEN,
    MAX_MSG_LEN,
    USER_COOLDOWN_SEC,
    CHANNEL_COOLDOWN_SEC,
)
from evtranslator.db import get_link_info
from evtranslator.translate import google_web_translate
from evtranslator.supabase_client import consume_chars, ensure_guild_row, get_quota


class RelayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_cooldowns: dict[int, float] = {}
        self.channel_cooldowns: dict[int, float] = {}
        self.warned_guilds: set[int] = set()  # servidores já avisados de 90%

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        # detectar proxy: mensagens de webhook (ex.: Tupperbox NPCs)
        is_proxy_msg = message.webhook_id is not None

        # --- filtro anti-duplicidade ---
        if not is_proxy_msg and not message.author.bot:
            # aguarda um pouquinho para dar tempo do Tupperbox apagar/proxiar
            await asyncio.sleep(0.7)
            try:
                await message.channel.fetch_message(message.id)
            except discord.NotFound:
                # mensagem já foi apagada (provavelmente proxied pelo Tupperbox) → ignorar
                return
            except Exception:
                pass
        # --- fim do filtro ---

        if message.author.bot and not is_proxy_msg:
            return

        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.content.endswith(TRANSLATED_FLAG):
            return

        info = await get_link_info(DB_PATH, message.guild.id, message.channel.id)
        if not info:
            return
        target_id, src_lang, target_lang = info

        target_ch = message.guild.get_channel(target_id)
        if not isinstance(target_ch, discord.TextChannel) or target_id == message.channel.id:
            return

        text = (message.content or "").strip()
        if len(text) < MIN_MSG_LEN:
            return
        if len(text) > MAX_MSG_LEN:
            text = text[:MAX_MSG_LEN] + " (…)"  # truncagem

        now = time.time()
        last_user = self.user_cooldowns.get(message.author.id, 0.0)
        if now - last_user < USER_COOLDOWN_SEC:
            return
        self.user_cooldowns[message.author.id] = now

        last_ch = self.channel_cooldowns.get(message.channel.id, 0.0)
        if now - last_ch < CHANNEL_COOLDOWN_SEC:
            return
        self.channel_cooldowns[message.channel.id] = now

        # QUOTA (Supabase)
        try:
            await asyncio.to_thread(ensure_guild_row, message.guild.id)
        except Exception:
            pass

        try:
            allowed, remaining = await asyncio.to_thread(
                consume_chars, message.guild.id, len(text)
            )
            quota = await asyncio.to_thread(get_quota, message.guild.id)
            char_limit = quota["char_limit"]
            used_chars = quota["used_chars"]

            # 🔔 Alerta de 90% de uso
            if (
                char_limit
                and used_chars >= 0.9 * char_limit
                and message.guild.id not in self.warned_guilds
            ):
                self.warned_guilds.add(message.guild.id)
                warning = (
                    f"⚠️ Este servidor já consumiu {used_chars:,} de {char_limit:,} caracteres "
                    f"(90% da cota mensal). Considere ajustar o limite ou aguardar o reset."
                )
                try:
                    if message.guild.owner:
                        await message.guild.owner.send(warning)
                except Exception as e:
                    logging.warning("Falha ao enviar DM ao dono do servidor: %s", e)

                for member in message.guild.members:
                    if member.guild_permissions.administrator and not member.bot:
                        try:
                            await member.send(warning)
                        except Exception:
                            continue

            if used_chars < 1000 and message.guild.id in self.warned_guilds:
                self.warned_guilds.remove(message.guild.id)

        except Exception as e:
            logging.exception("Falha ao consultar/consumir cota no Supabase: %s", e)
            return

        if not allowed:
            await message.channel.send(
                "⚠️ A cota de tradução deste servidor está esgotada por enquanto. "
                "Um admin pode ajustar o limite ou aguardar o reset mensal (`/quota`)."
            )
            return

        # traduz (apenas google_web_translate)
        try:
            async with self.bot.sem:  # type: ignore[attr-defined]
                translated = await google_web_translate(
                    self.bot.http_session, text, src_lang, target_lang
                )  # type: ignore[attr-defined]
        except Exception as e:
            logging.exception("Falha ao traduzir: %s", e)
            return

        # envia via webhook
        try:
            if is_proxy_msg:
                username = message.author.name or message.author.display_name
                avatar_url = (
                    str(message.author.display_avatar.url)
                    if message.author.display_avatar
                    else None
                )
                await self.bot.webhooks.send_as_identity(
                    target_ch,
                    username=username,
                    avatar_url=avatar_url,
                    text=f"{translated}{TRANSLATED_FLAG}",
                )
            else:
                await self.bot.webhooks.send_as_member(
                    target_ch, message.author, f"{translated}{TRANSLATED_FLAG}"
                )  # type: ignore[attr-defined]
        except Exception as e:
            logging.exception("Falha ao enviar via webhook: %s", e)
