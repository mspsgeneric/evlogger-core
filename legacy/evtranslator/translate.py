
from __future__ import annotations
import asyncio
import aiohttp
import urllib.parse
from typing import Optional
from .config import RETRIES, BACKOFF_BASE, HTTP_TIMEOUT

async def google_web_translate(session: aiohttp.ClientSession, text: str, src: str, dest: str) -> str:
    base = "https://translate.googleapis.com/translate_a/single"
    params = {"client": "gtx", "sl": src, "tl": dest, "dt": "t", "q": text}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    for attempt in range(RETRIES):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as resp:
                if resp.status == 429 or 500 <= resp.status < 600:
                    delay = BACKOFF_BASE * (2 ** attempt) + (0.2 * attempt)
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                parts = []
                for seg in data[0]:
                    if seg and seg[0]:
                        parts.append(seg[0])
                return "".join(parts)
        except Exception:
            delay = BACKOFF_BASE * (2 ** attempt) + 0.1 * attempt
            await asyncio.sleep(delay)
    raise RuntimeError("google_web_translate: failed after retries")
