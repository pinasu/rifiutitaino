"""Funzioni di supporto su date e giorni della settimana."""
from datetime import datetime, timedelta

from .data import GIORNI_IT, ROME_TZ


def adesso():
    """Data e ora correnti a Taino."""
    return datetime.now(ROME_TZ)


def chiave_domani():
    """Data di domani nel formato delle chiavi del calendario (GG-MM-AA)."""
    return (adesso() + timedelta(days=1)).strftime('%d-%m-%y')


def giorno_da_testo(parola):
    """Riconosce il giorno dalle prime tre lettere, così regge errori di battitura come "Lunerdì"."""
    for giorno in GIORNI_IT:
        if parola[:3].lower() == giorno[:3].lower():
            return giorno
    return None
