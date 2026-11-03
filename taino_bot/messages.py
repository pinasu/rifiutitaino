"""Tutti i testi e le tastiere che l'utente vede. Le funzioni qui non parlano con Telegram."""
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.helpers import escape_markdown

from .data import ECOCENTRO_ORARI, GIORNI_IT, MEDICI

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

CAMBIA_MEDICO_KEYBOARD = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Cambia medico", callback_data="medico:cambia")]])

# --- Mappatura icone e stili per i rifiuti ---
TRASH_ICONS = {
    "UMIDO": "🍏 *Umido*",
    "CARTA": "📦 *Carta*",
    "PLASTICA": "🥤 *Plastica*",
    "VETRO E LATTINE": "🍾 *Vetro e Lattine*",
    "SECCO": "🗑️ *Secco Residuo*"
}

MSG_ISCRIZIONE = "🔔 *Ti ho aggiunto alla lista delle notifiche delle 20:00!*"
MSG_START = (
    "👋 *Benvenuto!* Usa i bottoni qui sotto per i comandi:\n"
    "• /trash - cosa esporre domani\n"
    "• /ecocentro - orari di oggi dell'ecocentro\n"
    "• /medico - orari di oggi del medico di base\n"
    "• /biblioteca - orari della biblioteca\n\n"
    "🔔 _Riceverai anche la notifica delle 20:00._"
)
MSG_HINT_NUOVO = f"{MSG_ISCRIZIONE}\n\n👇 Usa i bottoni qui sotto per i comandi."
MSG_HINT = "👇 Puoi usare il bot solo con i bottoni qui sotto."
MSG_DOMANDA_MEDICO = "🩺 *Chi è il tuo medico di base?*\n\nScegli qui sotto: lo ricorderò per le prossime volte."
MSG_CAMBIA_MEDICO = "🩺 *Chi è il tuo medico di base?*"
MSG_ERRORE_MEDICO = "⚠️ Non sono riuscito a recuperare gli orari del medico. Riprova più tardi."
MSG_ERRORE_BIBLIOTECA = "⚠️ Non sono riuscito a recuperare gli orari della biblioteca. Riprova più tardi."


def medico_choice_keyboard():
    """Bottoni inline per scegliere il proprio medico di base."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(nome, callback_data=f"medico:{medico_id}")] for medico_id, nome in MEDICI.items()]
    )


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


def format_ecocentro_message(oggi):
    nome_giorno = GIORNI_IT[oggi.weekday()]
    periodo_str = "ESTIVO" if 5 <= oggi.month <= 10 else "INVERNALE"
    orario_oggi = ECOCENTRO_ORARI[periodo_str].get(nome_giorno)

    if orario_oggi:
        return (
            f"♻️ *Ecocentro di Taino* ♻️\n\n"
            f"Oggi è *{nome_giorno}* (Periodo {periodo_str})\n"
            f"L'ecocentro è *APERTO* con il seguente orario:\n"
            f"🕒 {orario_oggi}"
        )
    return (
        f"♻️ *Ecocentro di Taino* ♻️\n\n"
        f"Oggi è *{nome_giorno}* (Periodo {periodo_str})\n"
        f"Spiacente, oggi l'ecocentro è *CHIUSO*. 🛑"
    )


def format_medico_scelto(medico_id):
    return f"✅ Medico impostato: *{escape_markdown(MEDICI[medico_id])}*"


def format_medico_message(medico_id, studi, contatti, nome_giorno):
    """Orari di oggi del medico. Restituisce il testo e il numero di studi aperti oggi."""
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

    return messaggio, studi_aperti


def format_biblioteca_message(info, nome_giorno):
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

    return messaggio
