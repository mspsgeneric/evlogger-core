from __future__ import annotations
import logging
import discord
from typing import Optional
from discord import AllowedMentions

class WebhookSender:
    def __init__(self, bot_user_id: int):
        self.cache: dict[int, discord.Webhook] = {}
        self.bot_user_id = bot_user_id

    async def get_or_create(self, channel: discord.TextChannel) -> Optional[discord.Webhook]:
        wh = self.cache.get(channel.id)
        if wh:
            return wh
        try:
            hooks = await channel.webhooks()
            for h in hooks:
                if h.user and h.user.id == self.bot_user_id:
                    self.cache[channel.id] = h
                    return h
            wh = await channel.create_webhook(name="EVlogger Relay")
            self.cache[channel.id] = wh
            return wh
        except discord.Forbidden:
            logging.warning("Sem permissão para gerenciar webhooks em #%s", channel.name)
            return None
        except Exception as e:
            logging.warning("Falha ao obter/criar webhook em #%s: %s", channel.name, e)
            return None

    # ---------- NOVO: helper p/ normalizar kwargs ----------
    def _norm_kwargs(self, kwargs: dict, default_allowed: AllowedMentions) -> dict:
        # aceitar Embed único ou lista
        if "embeds" in kwargs and isinstance(kwargs["embeds"], discord.Embed):
            kwargs["embeds"] = [kwargs["embeds"]]
        # uniformizar 'text' -> 'content' se vier por engano
        if "text" in kwargs and "content" not in kwargs:
            kwargs["content"] = kwargs.pop("text")
        # garantir allowed_mentions padrão se não vier
        kwargs.setdefault("allowed_mentions", default_allowed)
        return kwargs

    async def send_as_member(self, channel: discord.TextChannel, member: discord.Member, text: str, **kwargs):
        """Envia mensagem imitando um membro humano (apelido + avatar). Aceita embeds, files, etc."""
        default_allowed = AllowedMentions.none()
        kwargs = self._norm_kwargs(kwargs, default_allowed)

        wh = await self.get_or_create(channel)
        display = member.display_name or member.name
        avatar = member.display_avatar.replace(size=128).url if member.display_avatar else None

        if wh:
            try:
                await wh.send(
                    content=text,
                    username=display,
                    avatar_url=avatar,
                    wait=False,
                    **kwargs,  # repassa embeds, files, allowed_mentions, etc.
                )
                return
            except Exception as e:
                logging.warning("Webhook falhou em #%s: %s — usando fallback.", channel.name, e)

        # Fallback mantém o display do autor; repassa embeds se houver
        await channel.send(
            content=f"**{display}:** {text}",
            embeds=kwargs.get("embeds"),
            allowed_mentions=kwargs.get("allowed_mentions", default_allowed),
        )

    async def send_as_identity(
        self,
        channel: discord.TextChannel,
        username: str,
        avatar_url: Optional[str],
        text: str,
        **kwargs,
    ):
        """Envia mensagem com nome/avatar arbitrários (útil para Tupperbox e webhooks). Aceita embeds, files, etc."""
        default_allowed = AllowedMentions.none()
        kwargs = self._norm_kwargs(kwargs, default_allowed)

        wh = await self.get_or_create(channel)
        uname = (username or "Proxy").strip()[:80]  # limite do Discord

        if wh:
            try:
                await wh.send(
                    content=text,
                    username=uname,
                    avatar_url=avatar_url or discord.utils.MISSING,
                    wait=False,
                    **kwargs,
                )
                return
            except Exception as e:
                logging.warning("Webhook falhou em #%s (identity): %s — usando fallback.", channel.name, e)

        await channel.send(
            content=f"**{uname}:** {text}",
            embeds=kwargs.get("embeds"),
            allowed_mentions=kwargs.get("allowed_mentions", default_allowed),
        )
