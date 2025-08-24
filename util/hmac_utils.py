# util/hmac_utils.py
import os, hmac, hashlib
from datetime import datetime, timezone

_SECRET = os.getenv("EVLOGGER_HMAC_SECRET")
if not _SECRET:
    # defina EVLOGGER_HMAC_SECRET no ambiente (.env) — pode ser uma string aleatória longa
    _SECRET = "defina-um-segredo-bem-grande-aqui"
_SECRET_BYTES = _SECRET.encode()

def ts_min_iso(dt: datetime) -> str:
    """Normaliza para minuto UTC e retorna no formato 2025-08-24T05:12Z."""
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%MZ")

def token_anonimo(guild_id: int, channel_id: int, user_id: int, ts_iso_min: str) -> str:
    """Token anônimo e determinístico para (guild, canal, usuário, minuto)."""
    msg = f"{guild_id}|{channel_id}|{user_id}|{ts_iso_min}".encode()
    return hmac.new(_SECRET_BYTES, msg, hashlib.sha256).hexdigest()[:12]
