"""Download delle pagine web, con cache in memoria, ed estrazione del testo dall'HTML."""
import asyncio
import html
import re
import urllib.request
from time import monotonic

from .logs import logger

# --- Cache delle pagine del Comune: gli orari cambiano raramente ---
PAGE_CACHE_TTL = 6 * 60 * 60  # secondi
_page_cache = {}        # nome -> (istante del download, risultato)
_page_cache_locks = {}  # nome -> asyncio.Lock, per non scaricare due volte la stessa pagina in parallelo


def fetch_page(url):
    """Scarica una pagina web e ne restituisce l'HTML."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


async def get_cached(nome, fetch_fn):
    """Esegue fetch_fn in un thread e ne tiene il risultato in cache per PAGE_CACHE_TTL secondi.

    Se il download fallisce ma esiste una copia in cache, anche scaduta, restituisce quella.
    """
    lock = _page_cache_locks.setdefault(nome, asyncio.Lock())
    async with lock:
        salvato = _page_cache.get(nome)
        if salvato and monotonic() - salvato[0] < PAGE_CACHE_TTL:
            return salvato[1]
        try:
            risultato = await asyncio.to_thread(fetch_fn)
        except Exception as e:
            if salvato:
                logger.warning(f"Pagina '{nome}' non disponibile, uso la copia in cache: {e}")
                return salvato[1]
            raise
        _page_cache[nome] = (monotonic(), risultato)
        return risultato


def html_to_text(fragment):
    """Toglie i tag HTML, decodifica le entità e normalizza gli spazi."""
    testo = html.unescape(re.sub(r'<[^>]+>', '', fragment)).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', testo).strip()
