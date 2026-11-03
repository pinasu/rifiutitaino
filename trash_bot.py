import json
import os
import re
import html
import asyncio
import logging
import urllib.request
import pytz
from datetime import datetime, timedelta, time
from time import monotonic
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown
from zoneinfo import ZoneInfo

# --- Pagina del Comune di Taino con gli orari della dott.ssa Htet ---
MEDICO_URL = "https://www.comune.taino.va.it/it/news/132139/nuovo-medico-di-medicina-generale"
GIORNI_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

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
MEDICI_UTENTI_FILE = 'medici_utenti.json'

# --- Pagina del Comune di Taino con gli orari della biblioteca ---
BIBLIOTECA_URL = "https://www.comune.taino.va.it/it/unita_organizzative/biblioteca"

# --- Cache delle pagine del Comune: gli orari cambiano raramente ---
PAGE_CACHE_TTL = 6 * 60 * 60  # secondi
_page_cache = {}        # nome -> (istante del download, risultato)
_page_cache_locks = {}  # nome -> asyncio.Lock, per non scaricare due volte la stessa pagina in parallelo

# --- Tastiera con i comandi al posto della tastiera classica ---
# Il testo di ogni bottone viene inviato in chat come se l'avesse scritto l'utente,
# quindi i comandi vengono gestiti dai rispettivi CommandHandler.
COMMANDS_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("/trash"), KeyboardButton("/ecocentro")],
        [KeyboardButton("/medico"), KeyboardButton("/biblioteca")]
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Usa i bottoni qui sotto 👇"
)

# --- Mappatura icone e stili per i rifiuti ---
TRASH_ICONS = {
    "UMIDO": "🍏 *Umido*",
    "CARTA": "📦 *Carta*",
    "PLASTICA": "🥤 *Plastica*",
    "VETRO E LATTINE": "🍾 *Vetro e Lattine*",
    "SECCO": "🗑️ *Secco Residuo*"
}

def format_trash_message(trash_list):
    """Formatta il messaggio dei rifiuti in modo elegante con le icone."""
    if not trash_list:
        return "✨ *Domani non c'è niente da esporre!* Goditi la serata. 🎉"
    
    message = "📋 *Promemoria Raccolta Differenziata*\n\n"
    message += "🚚 *Domani ricordati di esporre:*\n"
    for item in trash_list:
        # Pulisce da eventuali spazi e forza il maiuscolo per evitare discrepanze
        clean_item = item.strip().upper()
        formatted_item = TRASH_ICONS.get(clean_item, f"🔹 *{item}*")
        message += f"• {formatted_item}\n"
    
    message += "\n⚠️ _Ricordati di esporre i sacchi/mastelli correttamente._"
    return message

def save_json(path, data):
    """Scrive il file in modo atomico: se il Raspberry si spegne a metà, il file vecchio resta intatto."""
    tmp_path = f"{path}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)

def load_subscribers():
    if os.path.exists('subscribers.json'):
        with open('subscribers.json', 'r') as f:
            return json.load(f)
    return []

def save_subscribers():
    save_json('subscribers.json', subscribers)

def add_chat_id(chat_id):
    global subscribers
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers()
        return True
    return False

def load_medici_utenti():
    if os.path.exists(MEDICI_UTENTI_FILE):
        with open(MEDICI_UTENTI_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_medico_utente(chat_id, medico_id):
    global medici_utenti
    # Le chiavi JSON sono sempre stringhe
    medici_utenti[str(chat_id)] = medico_id
    save_json(MEDICI_UTENTI_FILE, medici_utenti)

def setup_logging():
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logger = logging.getLogger('trash_bot')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    class DailyLogHandler(logging.FileHandler):
        def __init__(self, filename_template, max_days=7, **kwargs):
            self.filename_template = filename_template
            self.max_days = max_days
            super().__init__(self._get_current_filename(), **kwargs)
            self._cleanup_old_logs()

        def _get_current_filename(self):
            """Genera il nome del file basato sulla data corrente."""
            return self.filename_template.format(date=datetime.now().strftime('%Y-%m-%d'))

        def _cleanup_old_logs(self):
            now = datetime.now()
            log_dir = os.path.dirname(self.filename_template.split('/')[0]) or '.'
            if not os.path.exists(log_dir): return
            
            for fname in os.listdir(log_dir):
                if fname.startswith('bot_') and fname.endswith('.log'):
                    try:
                        date_str = fname[4:-4]
                        file_date = datetime.strptime(date_str, '%Y-%m-%d')
                        if (now - file_date) > timedelta(days=self.max_days):
                            os.remove(os.path.join(log_dir, fname))
                    except (ValueError, OSError):
                        pass

        def emit(self, record):
            """Verifica la data prima di ogni emissione e ruota il file se necessario."""
            target_filename = self._get_current_filename()
            if self.baseFilename != os.path.abspath(target_filename):
                if self.stream:
                    self.stream.close()
                    self.stream = None
                # Assoluto come in FileHandler: con un percorso relativo il confronto sopra fallirebbe sempre
                self.baseFilename = os.path.abspath(target_filename)
            super().emit(record)

    log_handler = DailyLogHandler(
        filename_template='logs/bot_{date}.log',
        max_days=7,
        encoding='utf-8'
    )
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    return logger

logger = setup_logging()

try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    logger.info("Configurazione caricata con successo.")

    with open(config['calendar_file'], 'r') as f:
        calendar_data = json.load(f)
    logger.info(f"Calendario caricato da {config['calendar_file']}.")

except FileNotFoundError as e:
    logger.error(f"File non trovato: {e.filename}")
    raise

except json.JSONDecodeError:
    logger.error("Errore nel parsing del file JSON.")
    raise

def get_trash_exposure_date():
    next_day = (datetime.now() + timedelta(days=1)).strftime('%d-%m-%y')
    logger.info(f"Controllo esposizione rifiuti per domani: {next_day}")

    if next_day in calendar_data:
        logger.info(f"Trovata esposizione per domani: {calendar_data[next_day]}")
        return calendar_data[next_day]
    logger.warning(f"Nessuna esposizione trovata per domani ({next_day}).")
    return []

async def send_trash_exposure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global subscribers
    chat_id = update.effective_chat.id
    if add_chat_id(chat_id):
        await update.message.reply_text("🔔 *Ti ho aggiunto alla lista delle notifiche delle 20:00!*", parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
        logger.info(f"Aggiunto nuovo sottoscrittore da /trash: {chat_id}")

    logger.info(f"Ricevuto comando /trash da chat_id: {chat_id}")
    trash_info = get_trash_exposure_date()

    formatted_message = format_trash_message(trash_info)
    await context.bot.send_message(chat_id=chat_id, text=formatted_message, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    logger.info(f"Messaggio inviato a {chat_id}: {formatted_message}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global subscribers
    chat_id = update.effective_chat.id
    if add_chat_id(chat_id):
        logger.info(f"Aggiunto nuovo sottoscrittore da /start: {chat_id}")

    await update.message.reply_text(
        "👋 *Benvenuto!* Usa i bottoni qui sotto per i comandi:\n"
        "• /trash - cosa esporre domani\n"
        "• /ecocentro - orari di oggi dell'ecocentro\n"
        "• /medico - orari di oggi del medico di base\n"
        "• /biblioteca - orari della biblioteca\n\n"
        "🔔 _Riceverai anche la notifica delle 20:00._",
        parse_mode="Markdown",
        reply_markup=COMMANDS_KEYBOARD
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce tutto ciò che non è un comando dei bottoni: testo libero, comandi sconosciuti, foto, ecc.

    Telegram non permette di disattivare il campo di testo, quindi il messaggio dell'utente
    viene cancellato e si ricorda di usare i bottoni.
    """
    global subscribers
    chat_id = update.effective_chat.id

    try:
        await update.effective_message.delete()
    except Exception as e:
        logger.warning(f"Impossibile cancellare il messaggio di {chat_id}: {e}")

    # Tiene in chat un solo promemoria: cancella quello inviato in precedenza
    hint_id = context.chat_data.pop("hint_message_id", None)
    if hint_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=hint_id)
        except Exception as e:
            logger.warning(f"Impossibile cancellare il promemoria precedente in {chat_id}: {e}")

    if add_chat_id(chat_id):
        testo = "🔔 *Ti ho aggiunto alla lista delle notifiche delle 20:00!*\n\n👇 Usa i bottoni qui sotto per i comandi."
        logger.info(f"Aggiunto nuovo sottoscrittore da messaggio: {chat_id}")
    else:
        testo = "👇 Puoi usare il bot solo con i bottoni qui sotto."

    hint = await context.bot.send_message(chat_id=chat_id, text=testo, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    context.chat_data["hint_message_id"] = hint.message_id

async def send_daily_notification(context: ContextTypes.DEFAULT_TYPE):
    global subscribers
    logger.info("=== INIZIO INVIO NOTIFICHE GIORNALIERE ===")
    next_day = (datetime.now() + timedelta(days=1)).strftime('%d-%m-%y')

    if not subscribers:
        logger.warning("Nessun sottoscrittore configurato per le notifiche.")
        return

    trash_info = calendar_data.get(next_day, [])

    if not trash_info:
        logger.info(f"Nessun rifiuto da esporre per il {next_day}: notifica giornaliera saltata.")
        logger.info("=== FINE INVIO NOTIFICHE GIORNALIERE ===")
        return

    formatted_message = format_trash_message(trash_info)
    logger.info(f"Messaggio da inviare: {formatted_message}")

    for chat_id in subscribers:
        try:
            # Aggiunto parse_mode="Markdown" anche qui per l'invio pianificato automatico delle 20:00
            await context.bot.send_message(chat_id=chat_id, text=formatted_message, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
            logger.info(f"✅ Notifica inviata a chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"❌ Errore nell'invio a {chat_id}: {e}")

    logger.info("=== FINE INVIO NOTIFICHE GIORNALIERE ===")

async def send_ecocentro_openings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tz = ZoneInfo("Europe/Rome")
    oggi = datetime.now(tz)
    
    mese = oggi.month
    giorno_settimana = oggi.weekday()  # 0 = Lunedì, 1 = Martedì, ..., 5 = Sabato, 6 = Domenica

    giorni_it = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    nome_giorno = giorni_it[giorno_settimana]

    is_estivo = (5 <= mese <= 10)
    periodo_str = "ESTIVO" if is_estivo else "INVERNALE"

    orario_oggi = None

    if is_estivo:
        if giorno_settimana in (0, 2):  # 0 = Lunedì, 2 = Mercoledì
            orario_oggi = "🕒 14:00 - 18:00"
        elif giorno_settimana == 5:     # 5 = Sabato
            orario_oggi = "🕒 9:00 - 12:00 e 14:00 - 17:00"
    else:
        if giorno_settimana in (0, 2):  # 0 = Lunedì, 2 = Mercoledì
            orario_oggi = "🕒 15:00 - 17:00"
        elif giorno_settimana == 5:     # 5 = Sabato
            orario_oggi = "🕒 9:00 - 12:00 e 14:00 - 17:00"

    if orario_oggi:
        messaggio = (
            f"♻️ **Ecocentro di Taino** ♻️\n\n"
            f"Oggi è **{nome_giorno}** (Periodo {periodo_str})\n"
            f"L'ecocentro è **APERTO** con il seguente orario:\n"
            f"{orario_oggi}"
        )
    else:
        messaggio = (
            f"♻️ **Ecocentro di Taino** ♻️\n\n"
            f"Oggi è **{nome_giorno}** (Periodo {periodo_str})\n"
            f"Spiacente, oggi l'ecocentro è **CHIUSO**. 🛑"
        )

    await update.message.reply_text(messaggio, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)

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

def fetch_medico_info():
    """Scarica la news del Comune e restituisce gli studi (con orari per giorno) e i contatti."""
    page = fetch_page(MEDICO_URL)

    # Il testo della news è nel primo <div> senza attributi dopo la sezione "descrizione"
    descrizione = re.search(r'id="descrizione".*?<div\s*>(.*?)</div>', page, re.S)
    if not descrizione:
        raise ValueError("Sezione descrizione non trovata nella pagina del Comune")

    testo = re.sub(r'<br\s*/?>|</p>', '\n', descrizione.group(1))
    testo = html.unescape(re.sub(r'<[^>]+>', '', testo)).replace('\xa0', ' ')
    righe = [re.sub(r'\s+', ' ', r).strip() for r in testo.split('\n')]
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

def medico_choice_keyboard():
    """Bottoni inline per scegliere il proprio medico di base."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(nome, callback_data=f"medico:{medico_id}")] for medico_id, nome in MEDICI.items()]
    )

async def send_medico_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Ricevuto comando /medico da chat_id: {chat_id}")

    medico_id = medici_utenti.get(str(chat_id))
    if medico_id not in MEDICI:
        await update.message.reply_text(
            "🩺 *Chi è il tuo medico di base?*\n\nScegli qui sotto: lo ricorderò per le prossime volte.",
            parse_mode="Markdown",
            reply_markup=medico_choice_keyboard()
        )
        return

    await send_medico_message(chat_id, medico_id, context)

async def handle_medico_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    scelta = query.data.split(':', 1)[1]

    if scelta == "cambia":
        await query.message.reply_text(
            "🩺 *Chi è il tuo medico di base?*",
            parse_mode="Markdown",
            reply_markup=medico_choice_keyboard()
        )
        return

    if scelta not in MEDICI:
        return

    save_medico_utente(chat_id, scelta)
    logger.info(f"Chat {chat_id} ha impostato il medico: {scelta}")
    await query.edit_message_text(
        f"✅ Medico impostato: *{escape_markdown(MEDICI[scelta])}*",
        parse_mode="Markdown"
    )
    await send_medico_message(chat_id, scelta, context)

async def send_medico_message(chat_id, medico_id, context: ContextTypes.DEFAULT_TYPE) -> None:
    if medico_id == "marzo":
        studi, contatti = MARZO_STUDI, MARZO_CONTATTI
    else:
        try:
            studi, contatti = await get_cached("medico_htet", fetch_medico_info)
        except Exception as e:
            logger.error(f"Errore nel recupero degli orari del medico: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Non sono riuscito a recuperare gli orari del medico. Riprova più tardi.",
                reply_markup=COMMANDS_KEYBOARD
            )
            return

    nome_giorno = GIORNI_IT[datetime.now(ZoneInfo("Europe/Rome")).weekday()]
    messaggio = f"🩺 *{escape_markdown(MEDICI[medico_id])}* 🩺\n\nOggi è *{nome_giorno}*\n\n"

    studi_aperti = 0
    for studio in studi:
        fasce_oggi = studio["orari"].get(nome_giorno)
        if not fasce_oggi:
            continue

        studi_aperti += 1
        messaggio += f"🏥 Studio di *{escape_markdown(studio['nome'])}*\n"
        if studio["indirizzo"]:
            messaggio += f"📍 {escape_markdown(studio['indirizzo'])}\n"
        for orario, tipo in fasce_oggi:
            if "ricett" in tipo.lower():
                icona = "💊"
            elif "segreteria" in tipo.lower():
                icona = "📞"
            else:
                icona = "🕒"
            messaggio += f"{icona} {orario} {escape_markdown(tipo)}\n"
        messaggio += "\n"

    if studi_aperti == 0:
        messaggio += "Spiacente, oggi il medico non riceve. 🛑\n\n"

    for contatto in contatti:
        messaggio += f"ℹ️ _{escape_markdown(contatto)}_\n"

    await context.bot.send_message(
        chat_id=chat_id,
        text=messaggio,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Cambia medico", callback_data="medico:cambia")]])
    )
    logger.info(f"Orari medico ({medico_id}) inviati a {chat_id}: {studi_aperti} studi aperti oggi")

def giorno_da_testo(parola):
    """Riconosce il giorno dalle prime tre lettere, così regge errori di battitura come "Lunerdì"."""
    for giorno in GIORNI_IT:
        if parola[:3].lower() == giorno[:3].lower():
            return giorno
    return None

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

async def send_biblioteca_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Ricevuto comando /biblioteca da chat_id: {chat_id}")

    try:
        info = await get_cached("biblioteca", fetch_biblioteca_info)
    except Exception as e:
        logger.error(f"Errore nel recupero degli orari della biblioteca: {e}")
        await update.message.reply_text(
            "⚠️ Non sono riuscito a recuperare gli orari della biblioteca. Riprova più tardi.",
            reply_markup=COMMANDS_KEYBOARD
        )
        return

    nome_giorno = GIORNI_IT[datetime.now(ZoneInfo("Europe/Rome")).weekday()]
    fasce_oggi = info["orari"].get(nome_giorno)

    messaggio = f"📚 *Biblioteca di Taino* 📚\n\nOggi è *{nome_giorno}*\n"
    if fasce_oggi:
        messaggio += "La biblioteca è *APERTA*:\n"
        messaggio += "".join(f"🕒 {fascia}\n" for fascia in fasce_oggi)
    else:
        messaggio += "Spiacente, oggi la biblioteca è *CHIUSA*. 🛑\n"

    messaggio += "\n🗓️ *Orari della settimana:*\n"
    for giorno in GIORNI_IT:
        fasce = info["orari"].get(giorno)
        messaggio += f"• {giorno}: {', '.join(fasce) if fasce else 'chiuso'}\n"

    messaggio += "\n"
    if info["sede"]:
        messaggio += f"📍 {escape_markdown(info['sede'])}\n"
    if info["telefono"]:
        messaggio += f"📞 {escape_markdown(info['telefono'])}\n"
    if info["email"]:
        messaggio += f"✉️ {escape_markdown(info['email'])}\n"
    if info["aggiornamento"]:
        messaggio += f"\n_Orari aggiornati al {escape_markdown(info['aggiornamento'])}_"

    await update.message.reply_text(messaggio, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    logger.info(f"Orari biblioteca inviati a {chat_id}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scrive nel log del bot le eccezioni non gestite dagli handler (altrimenti finirebbero solo su stderr)."""
    logger.error("Errore durante la gestione di un update", exc_info=context.error)

def main():
    global subscribers, medici_utenti
    subscribers = load_subscribers()
    medici_utenti = load_medici_utenti()

    os.environ['TZ'] = 'Europe/Rome'
    
    logger.info("Avvio del bot...")
    
    # concurrent_updates: un utente che aspetta la pagina del Comune non blocca gli altri
    application = Application.builder().token(config['token']).concurrent_updates(True).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('trash', send_trash_exposure))
    application.add_handler(CommandHandler("ecocentro", send_ecocentro_openings))
    application.add_handler(CommandHandler("medico", send_medico_hours))
    application.add_handler(CommandHandler("biblioteca", send_biblioteca_hours))
    application.add_handler(CallbackQueryHandler(handle_medico_choice, pattern=r'^medico:'))
    # Registrato per ultimo: riceve solo ciò che nessun handler precedente ha gestito (compresi i comandi sconosciuti)
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_error_handler(error_handler)

    notifications_config = config.get('notifications', {})
    if notifications_config.get('enabled', False):
        try:
            hour, minute = map(int, notifications_config['time'].split(':'))
            
            rome_tz = pytz.timezone('Europe/Rome')
            
            application.job_queue.run_daily(
                callback=send_daily_notification,
                # Passiamo il fuso orario direttamente qui
                time=time(hour=hour, minute=minute, tzinfo=rome_tz),
                days=(0, 1, 2, 3, 4, 5, 6),
                name='daily_trash_notification'
            )
            logger.info(f"⏰ Notifiche programmate per le {notifications_config['time']} ogni giorno (Fuso locale).")
        except Exception as e:
            logger.error(f"Errore nella programmazione delle notifiche: {e}")
    else:
        logger.warning("⚠️ Le notifiche automatiche sono disabilitate in config.json.")

    logger.info("Bot configurato e pronto.")
    application.run_polling()

if __name__ == '__main__':
    main()
