"""Handler Telegram: ricevono l'update, prendono i dati e inviano il messaggio preparato in messages.py."""
import asyncio

from telegram import Update
from telegram.error import Forbidden, RetryAfter
from telegram.ext import ContextTypes

from . import sources, storage
from .data import GIORNI_IT, MARZO_CONTATTI, MARZO_STUDI, MEDICI
from .logs import logger
from .messages import (
    CAMBIA_MEDICO_KEYBOARD, COMMANDS_KEYBOARD, MSG_CAMBIA_MEDICO, MSG_DOMANDA_MEDICO, MSG_ERRORE_BIBLIOTECA,
    MSG_ERRORE_MEDICO, MSG_HINT, MSG_HINT_NUOVO, MSG_ISCRIZIONE, MSG_START, format_biblioteca_message,
    format_ecocentro_message, format_medico_message, format_medico_scelto, format_trash_message,
    medico_choice_keyboard
)
from .utils import adesso, chiave_domani
from .web import get_cached


async def send_trash_exposure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if storage.add_chat_id(chat_id):
        await update.effective_message.reply_text(MSG_ISCRIZIONE, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
        logger.info(f"Aggiunto nuovo sottoscrittore da /trash: {chat_id}")

    logger.info(f"Ricevuto comando /trash da chat_id: {chat_id}")
    trash_info = sources.get_trash_exposure_date()

    formatted_message = format_trash_message(trash_info)
    await context.bot.send_message(chat_id=chat_id, text=formatted_message, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    logger.info(f"Messaggio /trash inviato a {chat_id}")
    logger.debug(f"Testo inviato a {chat_id}: {formatted_message}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if storage.add_chat_id(chat_id):
        logger.info(f"Aggiunto nuovo sottoscrittore da /start: {chat_id}")

    await update.effective_message.reply_text(MSG_START, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce tutto ciò che non è un comando dei bottoni: testo libero, comandi sconosciuti, foto, ecc.

    Telegram non permette di disattivare il campo di testo, quindi il messaggio dell'utente
    viene cancellato e si ricorda di usare i bottoni.
    """
    chat_id = update.effective_chat.id

    if storage.add_chat_id(chat_id):
        testo = MSG_HINT_NUOVO
        logger.info(f"Aggiunto nuovo sottoscrittore da messaggio: {chat_id}")
    else:
        testo = MSG_HINT

    # Le tre chiamate sono indipendenti: partono insieme, così l'utente aspetta un solo giro di rete
    chiamate = [
        delete_quietly(update.effective_message.delete(), f"Impossibile cancellare il messaggio di {chat_id}"),
        context.bot.send_message(chat_id=chat_id, text=testo, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    ]
    # Tiene in chat un solo promemoria: cancella quello inviato in precedenza
    hint_id = context.chat_data.pop("hint_message_id", None)
    if hint_id:
        chiamate.append(delete_quietly(
            context.bot.delete_message(chat_id=chat_id, message_id=hint_id),
            f"Impossibile cancellare il promemoria precedente in {chat_id}"
        ))

    _, hint, *_ = await asyncio.gather(*chiamate)
    context.chat_data["hint_message_id"] = hint.message_id


async def delete_quietly(cancellazione, messaggio_errore):
    """Esegue una cancellazione: se fallisce (es. messaggio troppo vecchio) scrive solo un avviso nel log."""
    try:
        await cancellazione
    except Exception as e:
        logger.warning(f"{messaggio_errore}: {e}")


async def send_daily_notification(context: ContextTypes.DEFAULT_TYPE):
    logger.info("=== INIZIO INVIO NOTIFICHE GIORNALIERE ===")
    next_day = chiave_domani()

    if not storage.subscribers:
        logger.warning("Nessun sottoscrittore configurato per le notifiche.")
        return

    trash_info = sources.calendar_data.get(next_day, [])

    if not trash_info:
        logger.info(f"Nessun rifiuto da esporre per il {next_day}: notifica giornaliera saltata.")
        logger.info("=== FINE INVIO NOTIFICHE GIORNALIERE ===")
        return

    formatted_message = format_trash_message(trash_info)
    logger.debug(f"Messaggio da inviare: {formatted_message}")

    # Copia della lista: chi ha bloccato il bot viene rimosso durante il ciclo
    for chat_id in list(storage.subscribers):
        try:
            await send_with_retry(context.bot, chat_id, formatted_message)
            logger.info(f"✅ Notifica inviata a chat_id: {chat_id}")
        except Forbidden:
            storage.remove_chat_id(chat_id)
            logger.info(f"🚫 {chat_id} ha bloccato il bot: rimosso dagli iscritti")
        except Exception as e:
            logger.error(f"❌ Errore nell'invio a {chat_id}: {e}")

    logger.info("=== FINE INVIO NOTIFICHE GIORNALIERE ===")


async def send_with_retry(bot, chat_id, text):
    """Invia la notifica; se Telegram chiede di rallentare (RetryAfter) aspetta e riprova una volta."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    except RetryAfter as e:
        # retry_after è in secondi (int) o un timedelta, a seconda della versione della libreria
        attesa = e.retry_after.total_seconds() if hasattr(e.retry_after, "total_seconds") else e.retry_after
        logger.warning(f"Limite di Telegram raggiunto, riprovo l'invio a {chat_id} tra {attesa} s")
        await asyncio.sleep(attesa)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)


async def send_ecocentro_openings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    messaggio = format_ecocentro_message(adesso())
    await update.effective_message.reply_text(messaggio, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)


async def send_medico_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Ricevuto comando /medico da chat_id: {chat_id}")

    medico_id = storage.medici_utenti.get(str(chat_id))
    if medico_id not in MEDICI:
        await update.effective_message.reply_text(MSG_DOMANDA_MEDICO, parse_mode="Markdown", reply_markup=medico_choice_keyboard())
        return

    await send_medico_message(chat_id, medico_id, context)


async def handle_medico_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    scelta = query.data.split(':', 1)[1]

    if scelta == "cambia":
        await query.message.reply_text(MSG_CAMBIA_MEDICO, parse_mode="Markdown", reply_markup=medico_choice_keyboard())
        return

    if scelta not in MEDICI:
        return

    storage.save_medico_utente(chat_id, scelta)
    logger.info(f"Chat {chat_id} ha impostato il medico: {scelta}")
    await query.edit_message_text(format_medico_scelto(scelta), parse_mode="Markdown")
    await send_medico_message(chat_id, scelta, context)


async def send_medico_message(chat_id, medico_id, context: ContextTypes.DEFAULT_TYPE) -> None:
    if medico_id == "marzo":
        studi, contatti = MARZO_STUDI, MARZO_CONTATTI
    else:
        try:
            studi, contatti = await get_cached("medico_htet", sources.fetch_medico_info)
        except Exception as e:
            logger.error(f"Errore nel recupero degli orari del medico: {e}")
            await context.bot.send_message(chat_id=chat_id, text=MSG_ERRORE_MEDICO, reply_markup=COMMANDS_KEYBOARD)
            return

    nome_giorno = GIORNI_IT[adesso().weekday()]
    messaggio, studi_aperti = format_medico_message(medico_id, studi, contatti, nome_giorno)

    await context.bot.send_message(chat_id=chat_id, text=messaggio, parse_mode="Markdown", reply_markup=CAMBIA_MEDICO_KEYBOARD)
    logger.info(f"Orari medico ({medico_id}) inviati a {chat_id}: {studi_aperti} studi aperti oggi")


async def send_biblioteca_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Ricevuto comando /biblioteca da chat_id: {chat_id}")

    try:
        info = await get_cached("biblioteca", sources.fetch_biblioteca_info)
    except Exception as e:
        logger.error(f"Errore nel recupero degli orari della biblioteca: {e}")
        await update.effective_message.reply_text(MSG_ERRORE_BIBLIOTECA, reply_markup=COMMANDS_KEYBOARD)
        return

    messaggio = format_biblioteca_message(info, GIORNI_IT[adesso().weekday()])
    await update.effective_message.reply_text(messaggio, parse_mode="Markdown", reply_markup=COMMANDS_KEYBOARD)
    logger.info(f"Orari biblioteca inviati a {chat_id}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scrive nel log del bot le eccezioni non gestite dagli handler (altrimenti finirebbero solo su stderr)."""
    logger.error("Errore durante la gestione di un update", exc_info=context.error)
