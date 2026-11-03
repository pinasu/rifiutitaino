import json
import os
import re
import html
import asyncio
import logging
import urllib.request
import pytz
from datetime import datetime, timedelta, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown
from zoneinfo import ZoneInfo

# --- Pagina del Comune di Taino con gli orari del medico di base ---
MEDICO_URL = "https://www.comune.taino.va.it/it/news/132139/nuovo-medico-di-medicina-generale"
GIORNI_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

# --- Tastiera con i comandi al posto della tastiera classica ---
# Il testo di ogni bottone viene inviato in chat come se l'avesse scritto l'utente,
# quindi i comandi vengono gestiti dai rispettivi CommandHandler.
COMMANDS_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("/trash"), KeyboardButton("/ecocentro"), KeyboardButton("/medico")]],
    resize_keyboard=True,
    is_persistent=True
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

def load_subscribers():
    if os.path.exists('subscribers.json'):
        with open('subscribers.json', 'r') as f:
            return json.load(f)
    return []

def save_subscribers():
    with open('subscribers.json', 'w') as f:
        json.dump(subscribers, f, indent=2)

def add_chat_id(chat_id):
    global subscribers
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers()
        return True
    return False

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
                self.baseFilename = target_filename
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
        "• /medico - orari di oggi del medico di base\n\n"
        "🔔 _Riceverai anche la notifica delle 20:00._",
        parse_mode="Markdown",
        reply_markup=COMMANDS_KEYBOARD
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global subscribers
    chat_id = update.effective_chat.id
    if add_chat_id(chat_id):
        await update.message.reply_text("🔔 *Ti ho aggiunto alla lista delle notifiche delle 20:00!*", parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
        logger.info(f"Aggiunto nuovo sottoscrittore da messaggio: {chat_id}")
    else:
        await update.message.reply_text("👇 Usa i bottoni qui sotto per i comandi.", reply_markup=COMMANDS_KEYBOARD)

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

def fetch_medico_info():
    """Scarica la news del Comune e restituisce gli studi (con orari per giorno) e i contatti."""
    request = urllib.request.Request(MEDICO_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        page = response.read().decode("utf-8")

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

async def send_medico_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Ricevuto comando /medico da chat_id: {chat_id}")

    try:
        studi, contatti = await asyncio.to_thread(fetch_medico_info)
    except Exception as e:
        logger.error(f"Errore nel recupero degli orari del medico: {e}")
        await update.message.reply_text(
            "⚠️ Non sono riuscito a recuperare gli orari del medico. Riprova più tardi.",
            reply_markup=COMMANDS_KEYBOARD
        )
        return

    nome_giorno = GIORNI_IT[datetime.now(ZoneInfo("Europe/Rome")).weekday()]
    messaggio = f"🩺 *Medico di base* 🩺\n\nOggi è *{nome_giorno}*\n\n"

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
            icona = "💊" if "ricett" in tipo.lower() else "🕒"
            messaggio += f"{icona} {orario} {escape_markdown(tipo)}\n"
        messaggio += "\n"

    if studi_aperti == 0:
        messaggio += "Spiacente, oggi il medico non riceve. 🛑\n\n"

    for contatto in contatti:
        messaggio += f"ℹ️ _{escape_markdown(contatto)}_\n"

    await update.message.reply_text(messaggio, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    logger.info(f"Orari medico inviati a {chat_id}: {studi_aperti} studi aperti oggi")

def main():
    global subscribers
    subscribers = load_subscribers()
    
    os.environ['TZ'] = 'Europe/Rome'
    
    logger.info("Avvio del bot...")
    
    application = Application.builder().token(config['token']).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('trash', send_trash_exposure))
    application.add_handler(CommandHandler("ecocentro", send_ecocentro_openings))
    application.add_handler(CommandHandler("medico", send_medico_hours))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

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
