"""Avvio del bot: carica configurazione e dati, registra handler e notifica serale, avvia il polling."""
import os
from datetime import time

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from . import handlers, sources, storage
from .config import data_path, load_config
from .data import ROME_TZ
from .logs import logger, setup_logging


def build_application(config):
    """Crea l'Application con tutti gli handler e, se attiva, la notifica serale."""
    # concurrent_updates: un utente che aspetta la pagina del Comune non blocca gli altri
    application = Application.builder().token(config['token']).concurrent_updates(True).build()
    application.add_handler(CommandHandler('start', handlers.start))
    application.add_handler(CommandHandler('trash', handlers.send_trash_exposure))
    application.add_handler(CommandHandler("ecocentro", handlers.send_ecocentro_openings))
    application.add_handler(CommandHandler("medico", handlers.send_medico_hours))
    application.add_handler(CommandHandler("biblioteca", handlers.send_biblioteca_hours))
    application.add_handler(CallbackQueryHandler(handlers.handle_medico_choice, pattern=r'^medico:'))
    # Registrato per ultimo: riceve solo ciò che nessun handler precedente ha gestito (compresi i comandi sconosciuti)
    application.add_handler(MessageHandler(filters.ALL, handlers.handle_message))
    application.add_error_handler(handlers.error_handler)

    notifications_config = config.get('notifications', {})
    if notifications_config.get('enabled', False):
        try:
            hour, minute = map(int, notifications_config['time'].split(':'))

            application.job_queue.run_daily(
                callback=handlers.send_daily_notification,
                # Passiamo il fuso orario direttamente qui
                time=time(hour=hour, minute=minute, tzinfo=ROME_TZ),
                days=(0, 1, 2, 3, 4, 5, 6),
                name='daily_trash_notification'
            )
            logger.info(f"⏰ Notifiche programmate per le {notifications_config['time']} ogni giorno (Fuso locale).")
        except Exception as e:
            logger.error(f"Errore nella programmazione delle notifiche: {e}")
    else:
        logger.warning("⚠️ Le notifiche automatiche sono disabilitate in config.json.")

    return application


def main():
    setup_logging(data_path('logs'))
    config, sources.calendar_data = load_config()
    storage.subscribers = storage.load_subscribers()
    storage.medici_utenti = storage.load_medici_utenti()

    os.environ['TZ'] = 'Europe/Rome'

    logger.info("Avvio del bot...")
    application = build_application(config)
    logger.info("Bot configurato e pronto.")
    application.run_polling()
