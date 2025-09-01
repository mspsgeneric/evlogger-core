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
        self.warned_guilds: set[int] = set()  # servidores já avisados ao atingir 90%
        self.disabled_notice_ts: dict[int, float] = {}  # rate-limit do aviso "não habilitado"

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
        if (message.content or "").strip().endswith(TRANSLATED_FLAG):
            return

        # Link fonte→alvo configurado?
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

        # cooldowns de usuário e canal
        now = time.time()
        last_user = self.user_cooldowns.get(message.author.id, 0.0)
        if now - last_user < USER_COOLDOWN_SEC:
            return
        self.user_cooldowns[message.author.id] = now

        last_ch = self.channel_cooldowns.get(message.channel.id, 0.0)
        if now - last_ch < CHANNEL_COOLDOWN_SEC:
            return
        self.channel_cooldowns[message.channel.id] = now

        # --- limpeza eventual dos dicionários de cooldown ---
        if len(self.user_cooldowns) > 10000:
            cutoff = now - max(USER_COOLDOWN_SEC * 2, 120)
            self.user_cooldowns = {
                uid: ts for uid, ts in self.user_cooldowns.items() if ts >= cutoff
            }

        if len(self.channel_cooldowns) > 10000:
            cutoff = now - max(CHANNEL_COOLDOWN_SEC * 2, 120)
            self.channel_cooldowns = {
                cid: ts for cid, ts in self.channel_cooldowns.items() if ts >= cutoff
            }

        # --- SUPABASE: garantir linha e ler flags/cota ---
        try:
            await asyncio.to_thread(ensure_guild_row, message.guild.id)
        except Exception:
            # não trava a tradução; só evita crash
            pass

        try:
            quota_snapshot = await asyncio.to_thread(get_quota, message.guild.id)
        except Exception as e:
            logging.exception(
                "Falha ao consultar cota/flags no Supabase (guild=%s channel=%s msg_id=%s): %s",
                message.guild.id, message.channel.id, message.id, e
            )
            return

        # 🔒 Checar cedo se a guilda está habilitada
        translate_enabled = bool(quota_snapshot.get("translate_enabled", False))
        if not translate_enabled:
            # Rate-limit do aviso de "não habilitado" por 60s por guild
            last_notice = self.disabled_notice_ts.get(message.guild.id, 0.0)
            if now - last_notice > 60:
                try:
                    await message.channel.send(
                        "🚫 Este servidor **não está habilitado** para tradução no momento. "
                        "Entre em contato com o criador/gerente do bot."
                    )
                except Exception as e:
                    logging.warning(
                        "Falha ao enviar aviso de 'não habilitado' no canal (guild=%s channel=%s): %s",
                        message.guild.id, message.channel.id, e
                    )
                self.disabled_notice_ts[message.guild.id] = now
            return

        # Depois de confirmar habilitação, podemos seguir com a cota
        try:
            allowed, remaining = await asyncio.to_thread(
                consume_chars, message.guild.id, len(text)
            )
        except Exception as e:
            logging.exception(
                "Falha ao consumir cota no Supabase (guild=%s channel=%s msg_id=%s): %s",
                message.guild.id, message.channel.id, message.id, e
            )
            return

        if not allowed:
            try:
                await message.channel.send(
                    "⚠️ A cota de tradução deste servidor está esgotada por enquanto. "
                    "Um admin pode ajustar o limite ou aguardar o reset mensal (`/quota`)."
                )
            except Exception as e:
                logging.warning(
                    "Falha ao enviar aviso de cota esgotada no canal (guild=%s channel=%s): %s",
                    message.guild.id, message.channel.id, e
                )
            return

        # Reconsulta números atualizados para alerta de 90%
        try:
            quota = await asyncio.to_thread(get_quota, message.guild.id)
            char_limit = quota.get("char_limit") or 0
            used_chars = quota.get("used_chars") or 0

            # 🔔 Alerta de 90% de uso (DM para o dono, com fallback para 1º admin humano)
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

                sent = False
                # 1) tentar DM para o dono
                try:
                    if message.guild.owner:
                        await message.guild.owner.send(warning)
                        sent = True
                except Exception as e:
                    logging.warning(
                        "Falha ao enviar DM ao dono do servidor (guild=%s): %s",
                        message.guild.id, e
                    )

                # 2) fallback: primeiro admin humano
                if not sent:
                    try:
                        admin = next(
                            (m for m in message.guild.members
                             if m.guild_permissions.administrator and not m.bot),
                            None
                        )
                        if admin:
                            await admin.send(warning)
                            sent = True
                    except Exception as e:
                        logging.warning(
                            "Falha ao enviar DM ao admin (fallback) (guild=%s): %s",
                            message.guild.id, e
                        )

                if not sent:
                    logging.info(
                        "Não foi possível notificar dono/admin sobre 90%% da cota em guild %s",
                        message.guild.id,
                    )

            # se voltou a ficar baixo (ex.: reset), limpa flag
            if used_chars < 1000 and message.guild.id in self.warned_guilds:
                self.warned_guilds.remove(message.guild.id)

        except Exception as e:
            logging.exception(
                "Falha ao consultar cota (pós-consumo) no Supabase (guild=%s channel=%s msg_id=%s): %s",
                message.guild.id, message.channel.id, message.id, e
            )
            # não retorna; a tradução já foi autorizada, seguimos

        # --- traduz (apenas google_web_translate) ---
        try:
            sem = getattr(self.bot, "sem", None)
            if sem is None:
                sem = asyncio.Semaphore(1)
            async with sem:
                translated = await google_web_translate(
                    self.bot.http_session, text, src_lang, target_lang
                )  # type: ignore[attr-defined]
        except Exception as e:
            logging.exception(
                "Falha ao traduzir (guild=%s channel=%s msg_id=%s): %s",
                message.guild.id, message.channel.id, message.id, e
            )
            return

        # --- envia via webhook ---
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
            logging.exception(
                "Falha ao enviar via webhook (guild=%s channel=%s msg_id=%s): %s",
                message.guild.id, message.channel.id, message.id, e
            )
