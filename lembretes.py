# lembretes.py
import logging
from discord.ext import tasks
from datetime import datetime

ID_USUARIO_ESPOSA = 236497544559984641

# Define o loop uma única vez (fora da função)
@tasks.loop(minutes=1)
async def lembrete_racao(bot):
    agora = datetime.now().strftime("%H:%M")
    if agora in ["08:00", "11:00"]:
        try:
            user = await bot.fetch_user(ID_USUARIO_ESPOSA)
            if user:
                await user.send("🐶 Já deu a comida de Afonsinho?")
                logging.info(f"[LEMBRETE] Mensagem enviada para {user} às {agora}")
        except Exception as e:
            logging.warning(f"[LEMBRETE] Erro: {e}")

def setup(bot):
    async def on_ready():
        if not lembrete_racao.is_running():
            lembrete_racao.start(bot)  # passa o bot como argumento
            logging.info("⏰ Tarefa de lembrete iniciada!")

    bot.add_listener(on_ready)
