import logging
from discord.ext import tasks
from datetime import datetime
import pytz

# ID da sua esposa
ID_USUARIO_ESPOSA = 236497544559984641

def setup(bot):
    @tasks.loop(minutes=1)
    async def lembrete_racao():
        agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        hora_minuto = agora.strftime("%H:%M")

        if hora_minuto in ["08:00", "11:10"]:
            try:
                user = await bot.fetch_user(ID_USUARIO_ESPOSA)
                if user:
                    await user.send("🐶 Já deu a comida de Afonsinho?")
                    logging.info(f"[LEMBRETE] Mensagem enviada para {user} às {hora_minuto}")
            except Exception as e:
                logging.warning(f"[LEMBRETE] Erro ao enviar DM: {e}")

    async def on_ready():
        if not lembrete_racao.is_running():
            lembrete_racao.start()
            logging.info("⏰ Tarefa de lembrete iniciada!")

    bot.add_listener(on_ready)
