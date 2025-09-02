from __future__ import annotations
import logging
import discord
from typing import Optional  # ✅ único import
from discord import AllowedMentions

TARGET_NAME = "EVlogger Relay"  # ✅ constante

class WebhookSender:
    def __init__(self, bot_user_id: Optional[int]):
        self.cache: dict[int, discord.Webhook] = {}
        self.bot_user_id = bot_user_id

    async def get_or_create(self, channel: discord.TextChannel) -> Optional[discord.Webhook]:
        wh = self.cache.get(channel.id)
        if wh:
            return wh
        try:
            hooks = await channel.webhooks()
            target = None
            # 1) Preferir nosso webhook pelo user.id (quando soubermos)
            if self.bot_user_id is not None:
                for h in hooks:
                    if h.user and h.user.id == self.bot_user_id:
                        target = h
                        break
            # 2) Caso contrário, tentar pelo nome
            if target is None:
                for h in hooks:
                    if (h.name or "").strip() == TARGET_NAME:
                        target = h
                        break

            # 3) Se achou, mas SEM token, apaga e cria de novo (para ter token)
            if target is not None and target.token is None:
                try:
                    await target.delete(reason="Recreating to ensure token for execution")
                except Exception:
                    pass
                target = None

            # 4) Criar novo se não houver um válido/tokenizado
            if target is None:
                target = await channel.create_webhook(name=TARGET_NAME)
                try:
                    await target.edit(avatar=None)
                except Exception:
                    pass

            # 5) Normaliza nome/avatar e cacheia
            try:
                if target.name != TARGET_NAME or target.avatar is not None:
                    await target.edit(name=TARGET_NAME, avatar=None)
            except Exception:
                pass

            self.cache[channel.id] = target
            return target

        except discord.Forbidden:
            logging.warning("Sem permissão para gerenciar webhooks em #%s", channel.name)
            return None
        except Exception as e:
            logging.warning("Falha ao obter/criar webhook em #%s: %s", channel.name, e)
            return None


    def _norm_kwargs(self, kwargs: dict, default_allowed: AllowedMentions) -> dict:
        if "embeds" in kwargs and isinstance(kwargs["embeds"], discord.Embed):
            kwargs["embeds"] = [kwargs["embeds"]]
        if "text" in kwargs and "content" not in kwargs:
            kwargs["content"] = kwargs.pop("text")
        kwargs.setdefault("allowed_mentions", default_allowed)
        return kwargs

    async def send_as_member(self, channel: discord.TextChannel, member: discord.Member, text: str, **kwargs):
        """Envia mensagem imitando um membro humano (apelido + avatar)."""
        default_allowed = AllowedMentions.none()
        kwargs = self._norm_kwargs(kwargs, default_allowed)

        wh = await self.get_or_create(channel)
        display = member.display_name or member.name
        avatar = member.display_avatar.replace(size=128).url if member.display_avatar else None

        if not wh:
            logging.warning("Sem webhook em #%s; abortando para evitar mostrar nome do bot.", channel.name)
            return  # ✅ sem fallback (evita 'nome do bot')

        try:
            await wh.send(
                content=text,
                username=display,
                avatar_url=avatar,
                wait=False,
                **kwargs,
            )
        except Exception as e:
            logging.warning("Webhook falhou em #%s: %s", channel.name, e)
            # opcional: tentar texto-apenas
            try:
                await wh.send(content=text, username=display, avatar_url=avatar, wait=False,
                              allowed_mentions=kwargs.get("allowed_mentions", default_allowed))
            except Exception as e2:
                logging.warning("Webhook texto-apenas falhou em #%s: %s", channel.name, e2)

    async def send_as_identity(
        self,
        channel: discord.TextChannel,
        username: str,
        avatar_url: Optional[str],
        text: str,
        **kwargs,
    ):
        """Envia mensagem com nome/avatar arbitrários."""
        default_allowed = AllowedMentions.none()
        kwargs = self._norm_kwargs(kwargs, default_allowed)

        wh = await self.get_or_create(channel)
        if not wh:
            logging.warning("Sem webhook em #%s; abortando para evitar mostrar nome do bot.", channel.name)
            return  # ✅ sem fallback

        uname = (username or "Proxy").strip()[:80]
        try:
            await wh.send(
                content=text,
                username=uname,
                avatar_url=avatar_url or discord.utils.MISSING,
                wait=False,
                **kwargs,
            )
        except Exception as e:
            logging.warning("Webhook (identity) falhou em #%s: %s", channel.name, e)
            try:
                await wh.send(
                    content=text,
                    username=uname,
                    avatar_url=avatar_url or discord.utils.MISSING,
                    wait=False,
                    allowed_mentions=kwargs.get("allowed_mentions", default_allowed),
                )
            except Exception as e2:
                logging.warning("Webhook (identity) texto-apenas falhou em #%s: %s", channel.name, e2)
