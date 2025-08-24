# util/pino_anon.py
import re, discord
from datetime import datetime, timezone
from discord import TextChannel

MARCADOR = "EVLOGGER_PIN_V3"
CAB = "🧾 Retiradas de logs (anônimo)"
DETALHE_HDR = "Detalhes técnicos (ignore):"
MAX_LINHAS = 1000  # quantos registros manter no bloco técnico

async def get_pin(channel: TextChannel) -> discord.Message | None:
    """Acha o pino do EVlogger no canal (não cria)."""
    try:
        pins = await channel.pins()
    except discord.Forbidden:
        return None
    me = channel.guild.me
    for m in pins:
        if m.author == me and m.content and MARCADOR in m.content:
            return m
    return None

def parse_entries(content: str) -> list[tuple[str, str]]:
    """
    Extrai entradas do bloco ```txt``` como [(iso_min, token), ...] (mais recente primeiro).
    Espera linhas no formato: 2025-08-24T05:12Z · abcd1234ef56
    """
    if not content or DETALHE_HDR not in content:
        return []
    try:
        tail = content.split(DETALHE_HDR, 1)[1]
        m = re.search(r"```(?:txt)?\n(.*?)\n```", tail, flags=re.S)
        if not m:
            return []
        out: list[tuple[str, str]] = []
        for ln in m.group(1).splitlines():
            ln = ln.strip()
            if not ln or "·" not in ln:
                continue
            ts, tok = [p.strip() for p in ln.split("·", 1)]
            out.append((ts, tok))
        return out
    except Exception:
        return []

def _render(entries: list[tuple[str, str]]) -> str:
    """Renderiza o conteúdo completo do pino (cabeçalho + contagens + bloco técnico)."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    c_today = sum(1 for iso_min, _ in entries if iso_min.startswith(today))
    head = f"{CAB}\n\nHoje: {c_today}   Últimos 7 dias: {len(entries)}\n\n{DETALHE_HDR}\n```txt\n"
    body = "\n".join(f"{iso_min} · {tok}" for iso_min, tok in entries[:MAX_LINHAS])
    return head + body + "\n```\n— " + MARCADOR

async def _create_pin_with_entries(channel: TextChannel, entries: list[tuple[str, str]]) -> discord.Message | None:
    """Cria a mensagem e tenta fixar (usado apenas quando há a primeira retirada)."""
    try:
        msg = await channel.send(_render(entries), allowed_mentions=discord.AllowedMentions.none())
        try:
            await msg.pin()
        except discord.Forbidden:
            pass
        return msg
    except discord.Forbidden:
        return None

async def registrar_retirada_anonima(channel: TextChannel, iso_min: str, token: str) -> None:
    """
    Adiciona (iso_min, token) no topo. Se não existir pino, cria **agora** (primeira retirada).
    """
    pin = await get_pin(channel)
    if pin:
        entries = parse_entries(pin.content or "")
        if not any(ts == iso_min and tk == token for ts, tk in entries):
            entries.insert(0, (iso_min, token))
            novo = _render(entries)
            if novo != pin.content:
                await pin.edit(content=novo, allowed_mentions=discord.AllowedMentions.none())
        return

    # Sem pino ainda: cria apenas se já temos a primeira entrada (evita “pino vazio”)
    await _create_pin_with_entries(channel, [(iso_min, token)])
