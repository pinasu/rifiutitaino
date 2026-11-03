"""Configurazione: config.json, calendario e variabili d'ambiente."""
import json
import os

from .logs import logger

CALENDAR_DIR = os.path.join('data', 'trash')  # cartella dei calendari della raccolta


def data_path(*parts):
    """Percorso di un file dati: nella cartella BOT_DATA_DIR se impostata, altrimenti in quella corrente."""
    return os.path.join(os.environ.get('BOT_DATA_DIR', '.'), *parts)


def calendar_path(calendar_file):
    """Percorso del calendario indicato in config.json: viene cercato solo in data/trash/.

    Conta solo il nome del file, quindi "2026.json" e "data/trash/2026.json" indicano lo stesso file.
    """
    return data_path(CALENDAR_DIR, os.path.basename(calendar_file))


def load_config():
    """Legge config.json e il calendario indicato al suo interno.

    Il token può arrivare anche dalla variabile d'ambiente TELEGRAM_TOKEN, che ha la precedenza.
    """
    try:
        with open(data_path('config.json'), 'r') as f:
            config = json.load(f)
        logger.info("Configurazione caricata con successo.")
        if os.environ.get('TELEGRAM_TOKEN'):
            config['token'] = os.environ['TELEGRAM_TOKEN']
            logger.info("Token letto dalla variabile d'ambiente TELEGRAM_TOKEN.")

        percorso_calendario = calendar_path(config['calendar_file'])
        with open(percorso_calendario, 'r') as f:
            calendar = json.load(f)
        logger.info(f"Calendario caricato da {percorso_calendario}.")

    except FileNotFoundError as e:
        logger.error(f"File non trovato: {e.filename}")
        raise

    except json.JSONDecodeError:
        logger.error("Errore nel parsing del file JSON.")
        raise

    return config, calendar
