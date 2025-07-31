import discord, html, textwrap
from io import BytesIO
from util.supabase import get_supabase
from util.email import enviar_email

supabase = get_supabase()
MAX_REPLY_PREVIEW = 100

async def coletar_e_enviar_log(channel: discord.TextChannel, user: discord.User, guild_id: str):
    mensagens = []
    for msg in [m async for m in channel.history(limit=None, oldest_first=True)]:
        timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
        autor = msg.author.display_name
        conteudo = msg.content.strip()

        replied_text = ""
        if msg.reference and msg.reference.resolved:
            trecho = msg.reference.resolved.content
            if trecho:
                trecho = trecho.replace("\n", " ")
                if len(trecho) > MAX_REPLY_PREVIEW:
                    trecho = trecho[:MAX_REPLY_PREVIEW] + "..."
                replied_text = f'[Resposta a {msg.reference.resolved.author.display_name}: "{trecho}"]\n'
        conteudo = replied_text + conteudo

        if msg.attachments:
            conteudo += "\n" + "\n".join(a.url for a in msg.attachments)

        mensagens.append(f"[{timestamp}] {autor}:\n{conteudo}")

    log_txt = "\n\n".join(mensagens)
    log_html = "<br><br>".join(m.replace("\n", "<br>") for m in mensagens)

    email_ok = False
    dm_ok = False
    email = None

    # Tentar enviar email
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

            enviar_email(
                destinatario=email,
                assunto=assunto,
                corpo_html=corpo_html
            )
            email_ok = True
    except Exception as e:
        print("❌ Falha ao enviar email:", e)

    # Tentar enviar DM
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
