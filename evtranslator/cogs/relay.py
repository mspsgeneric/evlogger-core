from __future__ import annotations
import time
import asyncio
import logging
import discord
from discord.ext import commands
import os
import random
from dataclasses import dataclass


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


# === Helpers de anexos (embed-only) ===
MAX_FILES_PER_MESSAGE = 10

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

def _is_image(att: discord.Attachment) -> bool:
    # tenta pelo content_type; se vier None, cai no filename
    if att.content_type and att.content_type.startswith("image/"):
        return True
    name = (att.filename or "").lower()
    return name.endswith(_IMG_EXTS)

def _build_embeds_and_links(atts: list[discord.Attachment]) -> tuple[list[discord.Embed], list[str]]:
    """Cria embeds para até 10 imagens e devolve links (com spoiler preservado) para o restante."""
    embeds: list[discord.Embed] = []
    links: list[str] = []

    count = 0
    for a in atts:
        # não embeda spoiler: deixa como link com markdown de spoiler
        if count < MAX_FILES_PER_MESSAGE and _is_image(a) and not a.is_spoiler():
            emb = discord.Embed()
            emb.set_image(url=a.url)  # sem download
            embeds.append(emb)
            count += 1
        else:
            url = f"||{a.url}||" if a.is_spoiler() else a.url
            links.append(url)

    return embeds, links





class TokenBucket:
    def __init__(self, rate_per_sec: float, capacity: float):
        self.rate = float(rate_per_sec)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last = time.perf_counter()

    async def acquire(self):
        while True:
            now = time.perf_counter()
            elapsed = now - self.last
            self.last = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            # espera o suficiente para formar 1 token
            await asyncio.sleep(max(0.0, (1.0 - self.tokens) / self.rate))

@dataclass
class BackoffCfg:
    attempts: int = 3
    base: float = 0.3   # s
    factor: float = 2.0
    max_delay: float = 2.0
    jitter_ms: int = 150

class ExponentialBackoff:
    def __init__(self, cfg: BackoffCfg):
        self.cfg = cfg
        self.try_n = 0

    def next_delay(self) -> float:
        d = min(self.cfg.base * (self.cfg.factor ** self.try_n), self.cfg.max_delay)
        j = random.uniform(0, self.cfg.jitter_ms / 1000.0)
        self.try_n += 1
        return d + j

class CircuitBreaker:
    def __init__(self, fail_threshold: int = 6, cooldown_sec: float = 30.0):
        self.fail_threshold = fail_threshold
        self.cooldown_sec = cooldown_sec
        self.fail_count = 0
        self.open_until = 0.0

    @property
    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def on_success(self):
        self.fail_count = 0

    def on_failure(self):
        self.fail_count += 1
        if self.fail_count >= self.fail_threshold:
            self.open_until = time.monotonic() + self.cooldown_sec
            self.fail_count = 0



class RelayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_cooldowns: dict[int, float] = {}
        self.channel_cooldowns: dict[int, float] = {}
        self.warned_guilds: set[int] = set()  # servidores já avisados ao atingir 90%
        self.disabled_notice_ts: dict[int, float] = {}  # rate-limit do aviso "não habilitado"
        # --- EV modo-evento e controles de capacidade ---
        self.event_mode = os.getenv("EV_MODE_EVENT", "false").lower() == "true"

        # Cooldowns “modo evento” (fallback para os teus valores padrão)
        self.user_cd_event = float(os.getenv("EV_USER_COOLDOWN_SEC", "1.5"))
        self.chan_cd_event = float(os.getenv("EV_CHANNEL_COOLDOWN_SEC", "2.0"))

        # Rate cap (RPS) e burst curto
        rate = float(os.getenv("EV_PROVIDER_RATE_CAP", "12"))    # rps
        burst = float(os.getenv("EV_PROVIDER_BURST", "24"))      # burst curto
        self.rate_limiter = TokenBucket(rate, burst)

        # Timeout duro por tradução + jitter anti-rajada
        self.translate_timeout = float(os.getenv("EV_TRANSLATE_TIMEOUT", "8"))  # s
        self.jitter_ms = int(os.getenv("EV_JITTER_MS", "150"))

        # Backoff e breaker (sem fallback: só “esfria” quando ferver)
        self.backoff_cfg = BackoffCfg(
            attempts = int(os.getenv("EV_RETRY_ATTEMPTS", "3")),
            base     = float(os.getenv("EV_RETRY_BASE", "0.3")),
            factor   = float(os.getenv("EV_RETRY_FACTOR", "2.0")),
            max_delay= float(os.getenv("EV_RETRY_MAX", "2.0")),
            jitter_ms= int(os.getenv("EV_RETRY_JITTER_MS", "150")),
        )
        self.cb = CircuitBreaker(
            fail_threshold = int(os.getenv("EV_CB_THRESHOLD", "6")),
            cooldown_sec   = float(os.getenv("EV_CB_COOLDOWN", "30")),
        )

        # Dedupe leve (drop de mensagens idênticas curtinhas em janela)
        self.dedupe_window = float(os.getenv("EV_DEDUPE_WINDOW_SEC", "3.0"))
        self._last_hash_by_user_chan: dict[tuple[int,int], tuple[str,float]] = {}


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

        user_cd = self.user_cd_event if self.event_mode else USER_COOLDOWN_SEC
        last_user = self.user_cooldowns.get(message.author.id, 0.0)
        if now - last_user < user_cd:
            return
        self.user_cooldowns[message.author.id] = now

        chan_cd = self.chan_cd_event if self.event_mode else CHANNEL_COOLDOWN_SEC
        last_ch = self.channel_cooldowns.get(message.channel.id, 0.0)
        if now - last_ch < chan_cd:
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



        # Dedupe leve em modo-evento: drop de repetição curtinha por autor/canal
        if self.event_mode:
            key = (message.channel.id, message.author.id)
            norm = " ".join(text.split())[:140]
            ts_now = time.monotonic()
            last = self._last_hash_by_user_chan.get(key)
            if norm and last:
                lasth, lastt = last
                if norm == lasth and (ts_now - lastt) < self.dedupe_window:
                    return
            self._last_hash_by_user_chan[key] = (norm, ts_now)
    

        # --- traduz (com jitter, rate cap, timeout, backoff e breaker) ---
        if self.cb.is_open:
            logging.warning(
                "CB open: pausando traduções por curto período (guild=%s ch=%s)",
                message.guild.id, message.channel.id
            )
            return

        # jitter para desfazer sincronização (0..EV_JITTER_MS ms)
        if self.jitter_ms > 0:
            await asyncio.sleep(random.uniform(0, self.jitter_ms / 1000.0))

        # respeita RPS cap global do provedor
        await self.rate_limiter.acquire()

        sem = getattr(self.bot, "sem", None)
        if sem is None:
            sem = asyncio.Semaphore(1)

        bo = ExponentialBackoff(self.backoff_cfg)
        translated = None
        last_err = None

        for attempt in range(self.backoff_cfg.attempts):
            try:
                async with sem:
                    translated = await asyncio.wait_for(
                        google_web_translate(  # tua função real
                            self.bot.http_session, text, src_lang, target_lang
                        ),
                        timeout=self.translate_timeout,
                    )
                self.cb.on_success()
                break
            except asyncio.TimeoutError as e:
                last_err = e
                self.cb.on_failure()
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "429" in msg or "too many" in msg or "rate" in msg or "timeout" in msg or msg.startswith("5"):
                    self.cb.on_failure()
                else:
                    logging.exception("Erro não recuperável na tradução: %r", e)
                    break

            if attempt < self.backoff_cfg.attempts - 1:
                await asyncio.sleep(bo.next_delay())

        if translated is None:
            logging.warning(
                "Tradução falhou apos %d tentativas (guild=%s ch=%s msg=%s) ultimo_erro=%r",
                self.backoff_cfg.attempts, message.guild.id, message.channel.id, message.id, last_err
            )
            return


        # --- envia via webhook (EMBED-ONLY) ---
        try:
            conteudo = f"{translated}{TRANSLATED_FLAG}"

            # Monta embeds p/ imagens e links p/ demais anexos (preserva spoiler)
            embeds, links_fallback = _build_embeds_and_links(message.attachments or [])

            # Anexa os links no final do texto (ou manda numa 2ª msg se passar 2000 chars)
            if links_fallback:
                links_txt = "\n".join(f"• {u}" for u in links_fallback)
                sufixo = "\n\n**Anexos:**\n" + links_txt
                if len(conteudo) + len(sufixo) <= MAX_MSG_LEN:
                    conteudo += sufixo
                else:
                    # envia corpo + embeds primeiro
                    try:
                        if is_proxy_msg:
                            username = message.author.name or message.author.display_name
                            avatar_url = str(message.author.display_avatar.url) if message.author.display_avatar else None
                            await self.bot.webhooks.send_as_identity(
                                target_ch,
                                username=username,
                                avatar_url=avatar_url,
                                text=conteudo,
                                embeds=embeds,
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                        else:
                            await self.bot.webhooks.send_as_member(
                                target_ch,
                                message.author,
                                conteudo,
                                embeds=embeds,
                                allowed_mentions=discord.AllowedMentions.none(),  # type: ignore[attr-defined]
                            )
                    except TypeError:
                        # wrappers não aceitaram embeds/allowed_mentions → fallback simples
                        await target_ch.send(content=conteudo, embeds=embeds, allowed_mentions=discord.AllowedMentions.none())

                    # depois envia apenas os links
                    conteudo = "**Anexos:**\n" + links_txt
                    embeds = []

            # envio principal (tudo em UMA mensagem quando possível)
            if is_proxy_msg:
                username = message.author.name or message.author.display_name
                avatar_url = str(message.author.display_avatar.url) if message.author.display_avatar else None
                await self.bot.webhooks.send_as_identity(
                    target_ch,
                    username=username,
                    avatar_url=avatar_url,
                    text=conteudo,
                    embeds=embeds,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            else:
                await self.bot.webhooks.send_as_member(
                    target_ch,
                    message.author,
                    conteudo,
                    embeds=embeds,
                    allowed_mentions=discord.AllowedMentions.none(),  # type: ignore[attr-defined]
                )

        except TypeError:
            # wrappers não aceitam embeds/allowed_mentions → fallback p/ send()
            await target_ch.send(content=conteudo, embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            logging.exception(
                "Falha ao enviar via webhook (guild=%s channel=%s msg_id=%s): %s",
                message.guild.id, message.channel.id, message.id, e
            )


