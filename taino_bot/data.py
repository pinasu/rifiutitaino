"""Dati fissi del bot: orari scritti a mano, indirizzi delle pagine del Comune, nomi dei medici."""
from zoneinfo import ZoneInfo

ROME_TZ = ZoneInfo("Europe/Rome")
GIORNI_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

# --- Orari dell'ecocentro: estivo da maggio a ottobre, invernale il resto dell'anno ---
ECOCENTRO_ORARI = {
    "ESTIVO": {
        "Lunedì": "14:00 - 18:00",
        "Mercoledì": "14:00 - 18:00",
        "Sabato": "9:00 - 12:00 e 14:00 - 17:00"
    },
    "INVERNALE": {
        "Lunedì": "15:00 - 17:00",
        "Mercoledì": "15:00 - 17:00",
        "Sabato": "9:00 - 12:00 e 14:00 - 17:00"
    }
}

# --- Pagina del Comune di Taino con gli orari della dott.ssa Htet ---
MEDICO_URL = "https://www.comune.taino.va.it/it/news/132139/nuovo-medico-di-medicina-generale"

# --- Orari dr. Marzo (dal volantino data/marzo.pdf) ---
# Al mattino è attiva la segreteria, al pomeriggio il medico riceve solo su appuntamento
MARZO_STUDI = [
    {
        "nome": "Taino",
        "indirizzo": "Via Europa, 11",
        "orari": {
            "Lunedì": [("09:00 - 11:00", "Segreteria"), ("16:00 - 19:00", "Medico (su appuntamento)")],
            "Mercoledì": [("09:00 - 11:00", "Segreteria"), ("15:00 - 18:00", "Medico (su appuntamento)")],
            "Venerdì": [("09:00 - 11:00", "Segreteria"), ("16:30 - 19:30", "Medico (su appuntamento)")]
        }
    },
    {
        "nome": "Angera",
        "indirizzo": "Piazza Parrocchiale, 8",
        "orari": {
            "Martedì": [("09:00 - 11:00", "Segreteria"), ("16:00 - 19:00", "Medico (su appuntamento)")],
            "Giovedì": [("09:00 - 11:00", "Segreteria"), ("15:00 - 18:00", "Medico (su appuntamento)")]
        }
    }
]
MARZO_CONTATTI = [
    "E-mail: dr.v.marzo@gmail.com",
    "Tel. Segreteria: 351 83 69 125 dalle 9.00 alle 10.00",
    "Tel. Medico: 351 33 69 124 previo primo contatto con la segreteria"
]

# --- Medici di base disponibili: id -> nome visualizzato ---
MEDICI = {
    "htet": "Htet Htet Ne Win",
    "marzo": "Valentina Marzo"
}

# --- Pagina del Comune di Taino con gli orari della biblioteca ---
BIBLIOTECA_URL = "https://www.comune.taino.va.it/it/unita_organizzative/biblioteca"
