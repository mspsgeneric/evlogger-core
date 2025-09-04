import discord, html, textwrap, re, logging
from io import BytesIO
from util.db_supabase import get_supabase
from util.email_sender import enviar_email
import asyncio

logger = logging.getLogger(__name__)

supabase = get_supabase()
MAX_REPLY_PREVIEW = 100
MENTION_PATTERN = re.compile(r"<@!?(\d+)>")

async def coletar_e_enviar_log(channel: discord.TextChannel, user: discord.User, guild_id: str, enviar_email_ativo: bool = True):
    mensagens = []
    apelido_cache: dict[int, str] = {}

    async def nome_de(user_id: int) -> str:
        if user_id in apelido_cache:
            return apelido_cache[user_id]
        membro = channel.guild.get_member(user_id)
        if membro is None:
            try:
                membro = await channel.guild.fetch_member(user_id)
            except discord.NotFound:
                nome = str(user_id)
            else:
                nome = membro.display_name
        else:
            nome = membro.display_name
        apelido_cache[user_id] = nome
        return nome

    # ===== HISTÓRICO PAGINADO =====
    batch_size = 100
    before = None
    coletadas = 0
    try:
        while True:
            # mais eficiente puxar do mais novo pro mais antigo e acumular
            history_iter = channel.history(limit=batch_size, before=before, oldest_first=False)
            batch = [m async for m in history_iter]
            if not batch:
                break
            for msg in batch:
                try:
                    timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
                    autor_id = msg.author.id
                    autor_apelido = await nome_de(autor_id)

                    conteudo = (msg.content or "").strip()

                    # Trata reply
                    replied_text = ""
                    if msg.reference and msg.reference.resolved:
                        trecho = getattr(msg.reference.resolved, "content", "") or ""
                        if trecho:
                            trecho = trecho.replace("\n", " ")
                            if len(trecho) > MAX_REPLY_PREVIEW:
                                trecho = trecho[:MAX_REPLY_PREVIEW] + "..."
                            rep_autor = getattr(msg.reference.resolved.author, "display_name", None) or getattr(msg.reference.resolved.author, "name", "autor")
                            replied_text = f'[Resposta a {rep_autor}: "{trecho}"]\n'
                    conteudo = replied_text + conteudo

                    # Substitui menções
                    for match in reversed(list(MENTION_PATTERN.finditer(conteudo))):
                        uid = int(match.group(1))
                        nome = await nome_de(uid)
                        i, f = match.span()
                        conteudo = conteudo[:i] + f"@{nome}" + conteudo[f:]

                    if msg.attachments:
                        conteudo += "\n" + "\n".join(a.url for a in msg.attachments)

                    mensagens.append(f"[{timestamp}] {autor_apelido}:\n{conteudo}")
                except Exception as e:
                    logger.warning(f"[LOG_UTILS] Erro processando mensagem {getattr(msg,'id','?')}: {e}")

            coletadas += len(batch)
            before = batch[-1].created_at  # continua de onde parou

            # pequeno descanso a cada ~1000 msgs para evitar rate limit/estouro
            if coletadas and coletadas % 1000 == 0:
                await asyncio.sleep(0.3)

            if len(batch) < batch_size:
                break
    except discord.NotFound:
        # canal sumiu durante a coleta
        raise
    except discord.Forbidden:
        # perdeu permissão durante a coleta
        raise

    # reverte para ficar do mais antigo -> mais novo
    mensagens.reverse()

    log_txt = "\n\n".join(mensagens)
    log_html = "<br><br>".join(m.replace("\n", "<br>") for m in mensagens)

    email_ok = False
    dm_ok = False
    email = None

    if enviar_email_ativo:
        try:
            result = supabase.table("emails").select("email").eq("guild_id", guild_id).execute()
            if result.data:
                email = result.data[0]["email"]
                guild_name = html.escape(channel.guild.name)
                log_escape = html.escape(log_txt)

                assunto = f"[{guild_name}] Log da cena: {channel.name}"
                corpo_html = textwrap.dedent(f"""
                    <p>Olá, <strong>{guild_name}</strong>!</p>
                    <p>Segue abaixo o log completo da cena <strong>"{channel.name}"</strong>:</p>
                    <pre style="font-family: monospace; font-size: 13px;">{log_escape}</pre>
                    <p>Boa leitura e até a próxima cena!</p>
                    <p><em>Enviado por EVlogger – Eddverso</em></p>
                    <p style="font-size: 12px; color: #555;">
                      Acesse o <a href="https://eddverso.com.br">eddverso.com.br</a> para visualizar e gerenciar suas fichas.
                    </p>
                """)
                enviar_email(destinatario=email, assunto=assunto, corpo_html=corpo_html)
                email_ok = True
        except Exception as e:
            logger.warning(f"[LOG_UTILS] Falha ao enviar email: {e}")

    try:
        log_file = discord.File(fp=BytesIO(log_txt.encode("utf-8")), filename=f"log_{channel.name}_{channel.id}.txt")
        await user.send(content=f"📄 Aqui está o log da cena `{channel.name}`:", file=log_file)
        dm_ok = True
    except Exception as e:
        logger.warning(f"[LOG_UTILS] Falha ao enviar DM: {e}")

    return {"email": email_ok, "dm": dm_ok, "email_destinatario": email}
