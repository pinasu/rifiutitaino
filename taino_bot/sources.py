"""Da dove vengono i dati: il calendario della raccolta e le pagine del Comune."""
import re

from .data import BIBLIOTECA_URL, GIORNI_IT, MEDICO_URL
from .logs import logger
from .utils import chiave_domani, giorno_da_testo
from .web import fetch_page, html_to_text

# --- Calendario della raccolta: riempito da main() ---
calendar_data = {}    # "GG-MM-AA" -> rifiuti da esporre quel giorno


def get_trash_exposure_date():
    next_day = chiave_domani()
    logger.info(f"Controllo esposizione rifiuti per domani: {next_day}")

    if next_day in calendar_data:
        logger.info(f"Trovata esposizione per domani: {calendar_data[next_day]}")
        return calendar_data[next_day]
    logger.warning(f"Nessuna esposizione trovata per domani ({next_day}).")
    warn_if_calendar_expired(next_day)
    return []


def warn_if_calendar_expired(chiave):
    """Avvisa nel log se il calendario non contiene nessuna data dell'anno di `chiave` (GG-MM-AA)."""
    anno = chiave[-2:]
    if not any(data.endswith(f"-{anno}") for data in calendar_data):
        logger.warning(f"⚠️ Il calendario non contiene date del 20{anno}: va aggiornato (calendar_file in config.json).")


def fetch_medico_info():
    """Scarica la news del Comune e restituisce gli studi (con orari per giorno) e i contatti."""
    page = fetch_page(MEDICO_URL)

    # Il testo della news è nel primo <div> senza attributi dopo la sezione "descrizione"
    descrizione = re.search(r'id="descrizione".*?<div\s*>(.*?)</div>', page, re.S)
    if not descrizione:
        raise ValueError("Sezione descrizione non trovata nella pagina del Comune")

    testo = re.sub(r'<br\s*/?>|</p>', '\n', descrizione.group(1))
    righe = [html_to_text(r) for r in testo.split('\n')]
    righe = [r for r in righe if r]

    giorni_regex = re.compile(r'^(' + '|'.join(GIORNI_IT) + r')\s*-\s*(.*)$', re.IGNORECASE)
    studi = []
    contatti = []
    in_contatti = False

    for riga in righe:
        if riga.lower().startswith('contatti'):
            in_contatti = True
            continue
        if in_contatti:
            if riga.lower().startswith('richiesta'):
                contatti.append(riga)
            continue

        # Intestazione studio, es. "TAINO c/o Centro Bielli - Via Europa, 15"
        studio_match = re.match(r'^([A-ZÀ-Ù]{3,})\b\s*(.*)$', riga)
        if studio_match:
            studi.append({
                "nome": studio_match.group(1).title(),
                "indirizzo": studio_match.group(2).strip() or None,
                "orari": {}
            })
            continue

        # Riga giorno, es. "Martedì - 9.00/11.00 Ambulatorio 11.30/12.00 Ritiro Ricette"
        giorno_match = giorni_regex.match(riga)
        if giorno_match and studi:
            giorno = giorno_match.group(1).capitalize()
            fasce = []
            for h1, m1, h2, m2, tipo in re.findall(r'(\d{1,2})[.:](\d{2})\s*/\s*(\d{1,2})[.:](\d{2})\s*([^\d]*)', giorno_match.group(2)):
                fasce.append((f"{int(h1):02d}:{m1} - {int(h2):02d}:{m2}", tipo.strip() or "Ambulatorio"))
            studi[-1]["orari"].setdefault(giorno, []).extend(fasce)

    return studi, contatti


def fetch_biblioteca_info():
    """Scarica la pagina della biblioteca e restituisce sede, contatti, orari per giorno e data di aggiornamento."""
    page = fetch_page(BIBLIOTECA_URL)

    # Gli orari sono nell'elenco della sezione "Ulteriori informazioni", es. "Mercoledì dalle 15:00 alle 18:00"
    sezione_orari = re.search(r'id="ulteriori-informazioni".*?<div\s*>(.*?)</div>', page, re.S)
    if not sezione_orari:
        raise ValueError("Sezione orari non trovata nella pagina della biblioteca")

    orari = {}
    for voce in re.findall(r'<li[^>]*>(.*?)</li>', sezione_orari.group(1), re.S):
        testo = html_to_text(voce)
        giorno = giorno_da_testo(testo.split(' ', 1)[0])
        tempi = [f"{int(h):02d}:{m}" for h, m in re.findall(r'(\d{1,2})[.:](\d{2})', testo)]
        if not giorno or len(tempi) < 2:
            continue
        # Gli orari vanno a coppie (apertura, chiusura): regge anche "dalle 9 alle 12 e dalle 15 alle 18"
        fasce = [f"{tempi[i]} - {tempi[i + 1]}" for i in range(0, len(tempi) - 1, 2)]
        orari.setdefault(giorno, []).extend(fasce)

    if not orari:
        raise ValueError("Nessun orario trovato nella pagina della biblioteca")

    sede = re.search(r'id="sede-principale".*?card-title[^>]*>(.*?)</h1>.*?card-text[^>]*>(.*?)</div>', page, re.S)
    contatti = re.search(r'id="contatti"(.*?)id="ulteriori-informazioni"', page, re.S)
    contatti = contatti.group(1) if contatti else ""
    email = re.search(r'href="mailto:([^"]+)"', contatti)
    telefono = re.search(r'href="tel:[^"]*"[^>]*>([^<]+)<', contatti)
    aggiornamento = re.search(r'Ultimo aggiornamento</b>:\s*([^<]+)', page)

    return {
        "sede": f"{html_to_text(sede.group(1))}, {html_to_text(sede.group(2))}" if sede else None,
        "email": email.group(1).strip() if email else None,
        "telefono": html_to_text(telefono.group(1)) if telefono else None,
        "orari": orari,
        "aggiornamento": html_to_text(aggiornamento.group(1)) if aggiornamento else None
    }
