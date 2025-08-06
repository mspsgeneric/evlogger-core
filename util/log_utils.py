import discord, html, textwrap, re
from io import BytesIO
from util.supabase import get_supabase
from util.email import enviar_email

supabase = get_supabase()
MAX_REPLY_PREVIEW = 100
MENTION_PATTERN = re.compile(r"<@!?(\d+)>")

async def coletar_e_enviar_log(channel: discord.TextChannel, user: discord.User, guild_id: str):
    mensagens = []
    apelido_cache = {}

    async for msg in channel.history(limit=None, oldest_first=True):
        try:
            timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
            autor_id = msg.author.id

            # Cache de apelido
            if autor_id in apelido_cache:
                autor_apelido = apelido_cache[autor_id]
            else:
                try:
                    membro = await channel.guild.fetch_member(autor_id)
                    autor_apelido = membro.display_name
                except discord.NotFound:
                    autor_apelido = str(msg.author)
                apelido_cache[autor_id] = autor_apelido

            conteudo = msg.content.strip()

            # Trata reply
            replied_text = ""
            if msg.reference and msg.reference.resolved:
                trecho = msg.reference.resolved.content
                if trecho:
                    trecho = trecho.replace("\n", " ")
                    if len(trecho) > MAX_REPLY_PREVIEW:
                        trecho = trecho[:MAX_REPLY_PREVIEW] + "..."
                    replied_text = f'[Resposta a {msg.reference.resolved.author.display_name}: "{trecho}"]\n'
            conteudo = replied_text + conteudo

            # Substitui menções por apelidos
            def substituir_mencao(match):
                user_id = int(match.group(1))
                if user_id in apelido_cache:
                    return f"@{apelido_cache[user_id]}"
                membro = channel.guild.get_member(user_id)
                if membro:
                    apelido_cache[user_id] = membro.display_name
                    return f"@{membro.display_name}"
                return f"@{user_id}"

            # Substituir menções manualmente de forma assíncrona
            matches = list(MENTION_PATTERN.finditer(conteudo))
            for match in reversed(matches):  # de trás pra frente para não bagunçar os índices
                user_id = int(match.group(1))
                if user_id in apelido_cache:
                    nome = apelido_cache[user_id]
                else:
                    membro = channel.guild.get_member(user_id)
                    if not membro:
                        try:
                            membro = await channel.guild.fetch_member(user_id)
                        except discord.NotFound:
                            nome = str(user_id)
                        else:
                            nome = membro.display_name
                    else:
                        nome = membro.display_name
                    apelido_cache[user_id] = nome

                inicio, fim = match.span()
                conteudo = conteudo[:inicio] + f"@{nome}" + conteudo[fim:]


            # Anexos
            if msg.attachments:
                conteudo += "\n" + "\n".join(a.url for a in msg.attachments)

            mensagens.append(f"[{timestamp}] {autor_apelido}:\n{conteudo}")

        except Exception as e:
            print(f"❌ Erro processando mensagem {msg.id if msg else 'sem id'}: {e}")

    log_txt = "\n\n".join(mensagens)
    log_html = "<br><br>".join(m.replace("\n", "<br>") for m in mensagens)

    email_ok = False
    dm_ok = False
    email = None

    # Envia email
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
                <pre style="font-family: monospace; font-size: 13px;">
{log_escape}
                </pre>
                <p>Boa leitura e até a próxima cena!</p>
                <p><em>Enviado por EVlogger – Eddverso</em></p>
                <p style="font-size: 12px; color: #555;">
                Acesse o <a href="https://eddverso.com.br">eddverso.com.br</a> para visualizar e gerenciar suas fichas.
                </p>
            """)

            enviar_email(destinatario=email, assunto=assunto, corpo_html=corpo_html)
            email_ok = True

    except Exception as e:
        print("❌ Falha ao enviar email:", e)

    # Envia DM
    try:
        log_file = discord.File(fp=BytesIO(log_txt.encode("utf-8")), filename=f"log_{channel.name}.txt")
        await user.send(content=f"📄 Aqui está o log da cena `{channel.name}`:", file=log_file)
        dm_ok = True
    except Exception as e:
        print("❌ Falha ao enviar DM:", e)

    return {
        "email": email_ok,
        "dm": dm_ok,
        "email_destinatario": email
    }
