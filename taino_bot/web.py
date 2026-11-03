"""Download delle pagine web, con cache in memoria e su disco, ed estrazione del testo dall'HTML."""
import asyncio
import html
import json
import re
import urllib.request
from time import monotonic

from . import storage
from .config import data_path
from .logs import logger

# --- Cache delle pagine del Comune: gli orari cambiano raramente ---
PAGE_CACHE_TTL = 6 * 60 * 60  # secondi
PAGE_CACHE_FILE = 'page_cache.json'  # ultima copia valida di ogni pagina, sopravvive ai riavvii
RETRY_AFTER_FAILURE = 5 * 60  # con il sito giù, per 5 minuti si usa la copia senza riprovare
RETRY_DELAY = 1  # secondi prima del secondo tentativo, quando non c'è nessuna copia
_page_cache = {}        # nome -> (istante del download, risultato)
_page_cache_locks = {}  # nome -> asyncio.Lock, per non scaricare due volte la stessa pagina in parallelo


def fetch_page(url):
    """Scarica una pagina web e ne restituisce l'HTML."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8")


async def get_cached(nome, fetch_fn):
    """Esegue fetch_fn in un thread e ne tiene il risultato in cache per PAGE_CACHE_TTL secondi.

    Se il download fallisce restituisce l'ultima copia valida (in memoria o, dopo un riavvio,
    su disco). Senza nessuna copia riprova una volta e, se fallisce ancora, solleva l'errore.
    """
    lock = _page_cache_locks.setdefault(nome, asyncio.Lock())
    async with lock:
        salvato = _page_cache.get(nome)
        if salvato and monotonic() - salvato[0] < PAGE_CACHE_TTL:
            return salvato[1]
        if not salvato:
            salvato = load_saved_copy(nome)
        try:
            # Con una copia di riserva non si riprova: meglio rispondere subito che far aspettare l'utente
            risultato = await fetch_with_retry(fetch_fn, tentativi=1 if salvato else 2)
        except Exception as e:
            if salvato:
                logger.warning(f"Pagina '{nome}' non disponibile, uso l'ultima copia valida: {e}")
                # Considera la copia valida ancora per RETRY_AFTER_FAILURE secondi, così durante
                # un disservizio non si riprova il sito a ogni richiesta
                _page_cache[nome] = (monotonic() - PAGE_CACHE_TTL + RETRY_AFTER_FAILURE, salvato[1])
                return salvato[1]
            raise
        _page_cache[nome] = (monotonic(), risultato)
        save_copy(nome, risultato)
        return risultato


async def fetch_with_retry(fetch_fn, tentativi):
    """Esegue fetch_fn in un thread; sugli errori di rete o del server (es. HTTP 500) riprova."""
    for tentativo in range(1, tentativi + 1):
        try:
            return await asyncio.to_thread(fetch_fn)
        except OSError as e:  # URLError, HTTPError e timeout sono tutti OSError
            if tentativo == tentativi:
                raise
            logger.warning(f"Download fallito ({e}), nuovo tentativo tra {RETRY_DELAY} s")
            await asyncio.sleep(RETRY_DELAY)


def _read_saved_copies():
    try:
        with open(data_path(PAGE_CACHE_FILE), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load_saved_copy(nome):
    """Ultima copia valida salvata su disco, come voce di cache già scaduta (o None)."""
    copie = _read_saved_copies()
    if nome in copie:
        return (float('-inf'), copie[nome])
    return None


def save_copy(nome, risultato):
    """Salva su disco l'ultima copia valida; un errore qui non deve impedire di rispondere."""
    copie = _read_saved_copies()
    copie[nome] = risultato
    try:
        storage.save_json(data_path(PAGE_CACHE_FILE), copie)
    except OSError as e:
        logger.warning(f"Impossibile salvare la copia della pagina '{nome}': {e}")


def html_to_text(fragment):
    """Toglie i tag HTML, decodifica le entità e normalizza gli spazi."""
    testo = html.unescape(re.sub(r'<[^>]+>', '', fragment)).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', testo).strip()
