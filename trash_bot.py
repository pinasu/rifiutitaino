import json
import os
import logging
import pytz
from datetime import datetime, timedelta, time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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

# --- Funzioni per gestire i sottoscrittori ---
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

# --- Configurazione Logging ---
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
        await update.message.reply_text("🔔 *Ti ho aggiunto alla lista delle notifiche delle 20:00!*", parse_mode="Markdown")
        logger.info(f"Aggiunto nuovo sottoscrittore da /trash: {chat_id}")

    logger.info(f"Ricevuto comando /trash da chat_id: {chat_id}")
    trash_info = get_trash_exposure_date()

    formatted_message = format_trash_message(trash_info)
    await context.bot.send_message(chat_id=chat_id, text=formatted_message, parse_mode="Markdown")
    logger.info(f"Messaggio inviato a {chat_id}: {formatted_message}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global subscribers
    chat_id = update.effective_chat.id
    if add_chat_id(chat_id):
        await update.message.reply_text("🔔 *Ti ho aggiunto alla lista delle notifiche delle 20:00!*", parse_mode="Markdown")
        logger.info(f"Aggiunto nuovo sottoscrittore da messaggio: {chat_id}")

async def send_daily_notification(context: ContextTypes.DEFAULT_TYPE):
    global subscribers
    logger.info("=== INIZIO INVIO NOTIFICHE GIORNALIERE ===")
    next_day = (datetime.now() + timedelta(days=1)).strftime('%d-%m-%y')

    if not subscribers:
        logger.warning("Nessun sottoscrittore configurato per le notifiche.")
        return

    trash_info = calendar_data.get(next_day, [])
    formatted_message = format_trash_message(trash_info)
    logger.info(f"Messaggio da inviare: {formatted_message}")

    for chat_id in subscribers:
        try:
            # Aggiunto parse_mode="Markdown" anche qui per l'invio pianificato automatico delle 20:00
            await context.bot.send_message(chat_id=chat_id, text=formatted_message, parse_mode="Markdown")
            logger.info(f"✅ Notifica inviata a chat_id: {chat_id}")
        except Exception as e:
            logger.error(f"❌ Errore nell'invio a {chat_id}: {e}")

    logger.info("=== FINE INVIO NOTIFICHE GIORNALIERE ===")

def main():
    global subscribers
    subscribers = load_subscribers()
    
    os.environ['TZ'] = 'Europe/Rome'
    
    logger.info("Avvio del bot...")
    
    application = Application.builder().token(config['token']).build()
    application.add_handler(CommandHandler('trash', send_trash_exposure))
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