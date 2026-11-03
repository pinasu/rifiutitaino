"""Dati degli utenti salvati su file: iscritti alla notifica serale e medico scelto da ogni chat."""
import json
import os

from .config import data_path

MEDICI_UTENTI_FILE = 'medici_utenti.json'

# --- Stato degli utenti: riempito da main(), vuoto finché il bot non parte ---
subscribers = []      # chat iscritte alla notifica serale
medici_utenti = {}    # chat_id (stringa) -> id del medico scelto


def save_json(path, data):
    """Scrive il file in modo atomico: se il Raspberry si spegne a metà, il file vecchio resta intatto."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def load_subscribers():
    if os.path.exists(data_path('subscribers.json')):
        with open(data_path('subscribers.json'), 'r') as f:
            return json.load(f)
    return []


def save_subscribers():
    save_json(data_path('subscribers.json'), subscribers)


def add_chat_id(chat_id):
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers()
        return True
    return False


def load_medici_utenti():
    if os.path.exists(data_path(MEDICI_UTENTI_FILE)):
        with open(data_path(MEDICI_UTENTI_FILE), 'r') as f:
            return json.load(f)
    return {}


def save_medico_utente(chat_id, medico_id):
    # Le chiavi JSON sono sempre stringhe
    medici_utenti[str(chat_id)] = medico_id
    save_json(data_path(MEDICI_UTENTI_FILE), medici_utenti)
