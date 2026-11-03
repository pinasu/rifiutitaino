"""Test del bot Rifiuti Taino.

Esecuzione dalla cartella del progetto:
    python -m unittest discover test -v

I test non usano la rete né Telegram: le chiamate al bot e la pagina del Comune sono simulate.
Per provare anche il parsing sulla pagina reale del Comune:
    RUN_LIVE_TESTS=1 python -m unittest discover test -v
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import Application

# Il bot legge config.json e scrive log e file JSON nella cartella corrente:
# lavoriamo in una cartella temporanea per non toccare i file veri.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = tempfile.mkdtemp(prefix="trash_bot_test_")
CALENDARIO = {
    "06-01-26": ["UMIDO", "CARTA", "PLASTICA"],
    "07-01-26": ["umido ", "VETRO E LATTINE"],
    "08-01-26": ["INGOMBRANTI"]
}
with open(os.path.join(TEST_DIR, "config.json"), "w") as f:
    json.dump({"token": "123:TEST", "calendar_file": "calendario.json",
               "notifications": {"enabled": True, "time": "20:00"}}, f)
with open(os.path.join(TEST_DIR, "calendario.json"), "w") as f:
    json.dump(CALENDARIO, f)
os.chdir(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

from taino_bot import app, config, data, handlers, logs, messages, sources, storage, utils, web  # noqa: E402

logs.setup_logging(config.data_path("logs"))

# Estratto della news del Comune con la stessa struttura HTML della pagina reale
HTET_HTML = """
<html><body>
<a id="descrizione" class="anchor-content" href="#">Municipium</a>
<h2>Descrizione </h2>
<div class="row"><div class="offset-md-1 col-md-11">
<div ><p>Siamo lieti di informare che a partire da luned&igrave; 10 febbraio 2025 la Dottoressa Htet Htet Ne Win assumer&agrave; il ruolo di MMG.</p>
<p>Orari Ambulatori e Ritiro Ricette:</p>
<p><strong>TAINO c/o Centro Bielli - Via Europa, 15</strong></p>
<p><strong>Marted&igrave; -&nbsp; &nbsp; &nbsp;9.00/11.00&nbsp; Ambulatorio&nbsp; &nbsp; &nbsp; 11.30/12.00 Ritiro Ricette</strong><br /><strong>Gioved&igrave; -&nbsp; &nbsp; &nbsp;9.00/11.00&nbsp; Ambulatorio&nbsp; &nbsp; &nbsp; 11.30/12.00 Ritiro Ricette</strong></p>
<p>ANGERA Piazza Parrocchiale, 8</p>
<p>Luned&igrave; -&nbsp; &nbsp; &nbsp; &nbsp; 13.00/16.00 Ambulatorio<br />Mercoled&igrave; -&nbsp; &nbsp;15.00/18.00&nbsp; &nbsp; &nbsp; 18.30/19.00 Ritiro Ricette<br />Venerd&igrave; -&nbsp; &nbsp; &nbsp; 15.00/18.00&nbsp; &nbsp; &nbsp; 18.30/19.00 Ritiro Ricette</p>
<p>Contatti:<br /><strong>Richiesta ricette farmaci ripetivi</strong>: e-mail: dott.newin@gmail.com o Chiamate o Whatsapp: 327 2704456</p>
<p>Le ricette vengono inviate dematerializzate (tel) oppure via mail.</p>
<p><strong>Richiesta appuntamenti:</strong> Chiamate o Whatsapp: 327 2704456 dal luned&igrave; al venerd&igrave; dalle 8.00 alle 9.00</p>
<p>&nbsp;</p></div>
</div></div>
</body></html>
"""


# Estratto della pagina della biblioteca (con il refuso "Lunerdì" presente sulla pagina reale)
BIBLIOTECA_HTML = """
<html><body>
<a id="sede-principale" class="anchor-content" href="#">Municipium</a>
<h2>Sede principale </h2>
<div class="card-body">
    <h1 class="card-title h5">
        <a class="text-decoration-none" href="https://www.comune.taino.va.it/it/point-of-interest/735368">
            Municipio
        </a>
    </h1>
    <div class="card-text">
        <p>Piazza Pajetta, 21020 Taino VA, Italia</p>
    </div>
</div>
<a id="contatti" class="anchor-content" href="#">Municipium</a>
<h2>Contatti  <span class="sr-only">Utili</span> </h2>
<div class="offset-md-1 col-md-11 page-pnrr-content" data-element="organizationalunit">
    <strong>Email</strong> : <a href="mailto:biblioteca@comune.taino.va.it">biblioteca@comune.taino.va.it</a>
</div>
<div class="offset-md-1 col-md-11 page-pnrr-content" data-element="organizationalunit">
    <strong>Telefono</strong> : <a href="tel:0331.956405 (int. 8)">0331.956405 (int. 8)</a>
</div>
<a id="ulteriori-informazioni" class="anchor-content" href="#">Municipium</a>
<h2>Ulteriori Informazioni </h2>
<div class="row"><div class="offset-md-1 col-md-11">
<div ><p>Orario ufficio:</p>
<ul>
<li>Lunerd&igrave; dalle 10:00 alle 12:00</li>
<li>Mercoled&igrave; dalle 15:00 alle 18:00</li>
<li>Gioved&igrave; dalle 15:00 alle 18:00</li>
<li>Venerd&igrave; dalle 10:00 alle 12:00</li>
<li>Sabato dalle 10:00 alle 12:00</li>
</ul></div>
</div></div>
<p><b>Ultimo aggiornamento</b>: 18 febbraio 2026, 17:58</p>
</body></html>
"""


# Testi esatti dei messaggi, generati dal codice e confrontati carattere per carattere.
# Per rigenerarli dopo una modifica voluta dei testi: UPDATE_SNAPSHOTS=1 python -m unittest discover test
SNAPSHOT_FILE = os.path.join(PROJECT_DIR, "test", "snapshots", "messaggi.json")


def describe_markup(markup):
    """Rappresentazione confrontabile di una tastiera Telegram."""
    if markup is None:
        return None
    if markup is messages.COMMANDS_KEYBOARD:
        return "COMMANDS_KEYBOARD"
    if hasattr(markup, "inline_keyboard"):
        return [[[b.text, b.callback_data] for b in riga] for riga in markup.inline_keyboard]
    return [[b.text for b in riga] for riga in markup.keyboard]


def fake_datetime(fixed):
    """Sostituto di datetime con now() fisso (ma con lo stesso comportamento per il resto)."""
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=tz) if tz else fixed
    return FakeDatetime


def fake_urlopen(page):
    """Sostituto di urllib.request.urlopen che restituisce la pagina indicata."""
    response = MagicMock()
    response.read.return_value = page.encode("utf-8")
    response.__enter__.return_value = response
    return MagicMock(return_value=response)


class TestTrashBot(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        storage.subscribers = []
        storage.medici_utenti = {}
        sources.calendar_data = dict(CALENDARIO)
        web._page_cache.clear()
        web._page_cache_locks.clear()
        for nome in ("subscribers.json", storage.MEDICI_UTENTI_FILE):
            if os.path.exists(nome):
                os.remove(nome)

        self.context = SimpleNamespace(
            bot=SimpleNamespace(
                send_message=AsyncMock(return_value=SimpleNamespace(message_id=100)),
                delete_message=AsyncMock()
            ),
            chat_data={}
        )

    def make_update(self, chat_id=42):
        message = SimpleNamespace(reply_text=AsyncMock(), delete=AsyncMock())
        return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), message=message, effective_message=message)

    def make_callback_update(self, callback_data, chat_id=42):
        query = SimpleNamespace(
            data=callback_data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), reply_text=AsyncMock())
        )
        return SimpleNamespace(callback_query=query)

    def sent_texts(self):
        return [c.kwargs["text"] for c in self.context.bot.send_message.call_args_list]

    # --- Tastiera dei comandi ---

    def test_commands_keyboard_has_all_commands(self):
        testi = [b.text for riga in messages.COMMANDS_KEYBOARD.keyboard for b in riga]
        self.assertEqual(testi, ["/trash", "/ecocentro", "/medico", "/biblioteca"])
        self.assertTrue(messages.COMMANDS_KEYBOARD.is_persistent)
        self.assertTrue(messages.COMMANDS_KEYBOARD.resize_keyboard)

    # --- Messaggio dei rifiuti ---

    def test_format_trash_message_empty(self):
        self.assertIn("non c'è niente da esporre", messages.format_trash_message([]))

    def test_format_trash_message_known_items(self):
        messaggio = messages.format_trash_message(["UMIDO", "CARTA", "PLASTICA", "VETRO E LATTINE", "SECCO"])
        for voce in messages.TRASH_ICONS.values():
            self.assertIn(voce, messaggio)

    def test_format_trash_message_normalizes_case_and_spaces(self):
        self.assertIn(messages.TRASH_ICONS["UMIDO"], messages.format_trash_message([" umido "]))

    def test_format_trash_message_unknown_item(self):
        self.assertIn("🔹 *INGOMBRANTI*", messages.format_trash_message(["INGOMBRANTI"]))

    def test_get_trash_exposure_date_returns_tomorrow(self):
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 18, 0))):
            self.assertEqual(sources.get_trash_exposure_date(), ["UMIDO", "CARTA", "PLASTICA"])

    def test_tomorrow_uses_rome_time_even_if_system_clock_is_utc(self):
        from datetime import timezone
        utc_now = datetime(2026, 1, 5, 23, 30, tzinfo=timezone.utc)  # a Roma è già il 6 gennaio, 00:30

        class UtcSystemDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return utc_now.astimezone(tz) if tz else utc_now.replace(tzinfo=None)

        with patch.object(utils, "datetime", UtcSystemDatetime):
            self.assertEqual(utils.chiave_domani(), "07-01-26")

    def test_get_trash_exposure_date_no_collection(self):
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 10, 18, 0))):
            self.assertEqual(sources.get_trash_exposure_date(), [])

    # --- Iscritti alle notifiche ---

    def test_add_chat_id_saves_new_subscriber(self):
        self.assertTrue(storage.add_chat_id(42))
        with open("subscribers.json") as f:
            self.assertEqual(json.load(f), [42])
        self.assertEqual(storage.load_subscribers(), [42])

    def test_add_chat_id_ignores_duplicates(self):
        storage.add_chat_id(42)
        self.assertFalse(storage.add_chat_id(42))
        self.assertEqual(storage.subscribers, [42])

    def test_save_json_keeps_old_file_if_write_fails(self):
        storage.save_json("subscribers.json", [1, 2])
        with patch("json.dump", side_effect=OSError("spegnimento improvviso")):
            with self.assertRaises(OSError):
                storage.save_json("subscribers.json", [1, 2, 3])

        with open("subscribers.json") as f:
            self.assertEqual(json.load(f), [1, 2])

    def test_save_json_same_format_as_before(self):
        storage.save_json("subscribers.json", [42])
        with open("subscribers.json") as f:
            self.assertEqual(f.read(), json.dumps([42], indent=2))
        self.assertFalse(os.path.exists("subscribers.json.tmp"))

    def test_load_subscribers_without_file(self):
        self.assertEqual(storage.load_subscribers(), [])

    # --- Comandi /start, /trash e messaggi liberi ---

    async def test_start_subscribes_and_shows_keyboard(self):
        update = self.make_update()
        await handlers.start(update, self.context)

        self.assertEqual(storage.subscribers, [42])
        kwargs = update.message.reply_text.call_args.kwargs
        self.assertIs(kwargs["reply_markup"], messages.COMMANDS_KEYBOARD)
        self.assertIn("/medico", update.message.reply_text.call_args.args[0])
        self.assertIn("/biblioteca", update.message.reply_text.call_args.args[0])

    async def test_trash_command_new_subscriber(self):
        update = self.make_update()
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 18, 0))):
            await handlers.send_trash_exposure(update, self.context)

        self.assertEqual(storage.subscribers, [42])
        self.assertIn("aggiunto", update.message.reply_text.call_args.args[0])
        self.assertIn(messages.TRASH_ICONS["CARTA"], self.sent_texts()[0])
        self.assertIs(self.context.bot.send_message.call_args.kwargs["reply_markup"], messages.COMMANDS_KEYBOARD)

    async def test_trash_command_existing_subscriber(self):
        storage.subscribers = [42]
        update = self.make_update()
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 18, 0))):
            await handlers.send_trash_exposure(update, self.context)

        update.message.reply_text.assert_not_called()
        self.context.bot.send_message.assert_called_once()

    def test_commands_keyboard_has_placeholder(self):
        self.assertIn("bottoni", messages.COMMANDS_KEYBOARD.input_field_placeholder)

    async def test_handle_message_new_user_is_subscribed(self):
        update = self.make_update()
        await handlers.handle_message(update, self.context)

        self.assertEqual(storage.subscribers, [42])
        update.message.delete.assert_awaited_once()
        self.assertIn("aggiunto", self.sent_texts()[0])

    async def test_handle_message_deletes_text_and_shows_keyboard(self):
        storage.subscribers = [42]
        update = self.make_update()
        await handlers.handle_message(update, self.context)

        update.message.delete.assert_awaited_once()
        self.assertIn("solo con i bottoni", self.sent_texts()[0])
        self.assertIs(self.context.bot.send_message.call_args.kwargs["reply_markup"], messages.COMMANDS_KEYBOARD)
        self.assertEqual(self.context.chat_data["hint_message_id"], 100)

    async def test_handle_message_replaces_previous_hint(self):
        storage.subscribers = [42]
        self.context.chat_data["hint_message_id"] = 99
        await handlers.handle_message(self.make_update(), self.context)

        self.context.bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=99)
        self.assertEqual(self.context.chat_data["hint_message_id"], 100)

    async def test_handle_message_works_if_delete_fails(self):
        storage.subscribers = [42]
        update = self.make_update()
        update.message.delete.side_effect = Exception("messaggio troppo vecchio")
        self.context.chat_data["hint_message_id"] = 99
        self.context.bot.delete_message.side_effect = Exception("promemoria già cancellato")
        await handlers.handle_message(update, self.context)

        self.context.bot.send_message.assert_awaited_once()
        self.assertEqual(self.context.chat_data["hint_message_id"], 100)

    # --- Notifica giornaliera ---

    async def test_daily_notification_sends_to_all_subscribers(self):
        storage.subscribers = [1, 2]
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 20, 0))):
            await handlers.send_daily_notification(self.context)

        chat_ids = [c.kwargs["chat_id"] for c in self.context.bot.send_message.call_args_list]
        self.assertEqual(chat_ids, [1, 2])

    async def test_daily_notification_skipped_without_collection(self):
        storage.subscribers = [1]
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 10, 20, 0))):
            await handlers.send_daily_notification(self.context)

        self.context.bot.send_message.assert_not_called()

    async def test_daily_notification_without_subscribers(self):
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 20, 0))):
            await handlers.send_daily_notification(self.context)

        self.context.bot.send_message.assert_not_called()

    async def test_daily_notification_continues_after_error(self):
        storage.subscribers = [1, 2]
        self.context.bot.send_message.side_effect = [Exception("bot bloccato"), None]
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 20, 0))):
            await handlers.send_daily_notification(self.context)

        self.assertEqual(self.context.bot.send_message.call_count, 2)

    # --- Ecocentro ---

    async def ecocentro_reply(self, giorno):
        update = self.make_update()
        with patch.object(utils, "datetime", fake_datetime(giorno)):
            await handlers.send_ecocentro_openings(update, self.context)
        return update.message.reply_text.call_args.args[0]

    async def test_ecocentro_summer_monday(self):
        messaggio = await self.ecocentro_reply(datetime(2026, 6, 1, 10, 0))
        self.assertIn("APERTO", messaggio)
        self.assertIn("ESTIVO", messaggio)
        self.assertIn("14:00 - 18:00", messaggio)

    async def test_ecocentro_winter_wednesday(self):
        messaggio = await self.ecocentro_reply(datetime(2026, 1, 7, 10, 0))
        self.assertIn("INVERNALE", messaggio)
        self.assertIn("15:00 - 17:00", messaggio)

    async def test_ecocentro_saturday(self):
        messaggio = await self.ecocentro_reply(datetime(2026, 1, 10, 10, 0))
        self.assertIn("9:00 - 12:00 e 14:00 - 17:00", messaggio)

    async def test_ecocentro_closed_tuesday(self):
        messaggio = await self.ecocentro_reply(datetime(2026, 1, 6, 10, 0))
        self.assertIn("CHIUSO", messaggio)

    # --- Parsing della pagina del Comune (dott.ssa Htet) ---

    def test_fetch_medico_info_parses_studios(self):
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)):
            studi, contatti = sources.fetch_medico_info()

        self.assertEqual([s["nome"] for s in studi], ["Taino", "Angera"])
        self.assertEqual(studi[0]["indirizzo"], "c/o Centro Bielli - Via Europa, 15")
        self.assertEqual(studi[1]["indirizzo"], "Piazza Parrocchiale, 8")
        self.assertEqual(studi[0]["orari"]["Martedì"], [("09:00 - 11:00", "Ambulatorio"), ("11:30 - 12:00", "Ritiro Ricette")])
        self.assertEqual(studi[1]["orari"]["Lunedì"], [("13:00 - 16:00", "Ambulatorio")])
        self.assertEqual(set(studi[0]["orari"]), {"Martedì", "Giovedì"})
        self.assertEqual(set(studi[1]["orari"]), {"Lunedì", "Mercoledì", "Venerdì"})

    def test_fetch_medico_info_unlabeled_slot_is_ambulatorio(self):
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)):
            studi, _ = sources.fetch_medico_info()

        self.assertEqual(studi[1]["orari"]["Mercoledì"], [("15:00 - 18:00", "Ambulatorio"), ("18:30 - 19:00", "Ritiro Ricette")])

    def test_fetch_medico_info_parses_contacts(self):
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)):
            _, contatti = sources.fetch_medico_info()

        self.assertEqual(len(contatti), 2)
        self.assertTrue(contatti[0].startswith("Richiesta ricette"))
        self.assertTrue(contatti[1].startswith("Richiesta appuntamenti"))
        self.assertIn("lunedì", contatti[1])

    def test_fetch_medico_info_page_without_description(self):
        with patch("urllib.request.urlopen", fake_urlopen("<html><body>Pagina cambiata</body></html>")):
            with self.assertRaises(ValueError):
                sources.fetch_medico_info()

    @unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS"), "imposta RUN_LIVE_TESTS=1 per usare la pagina reale")
    def test_fetch_medico_info_live_page(self):
        studi, contatti = sources.fetch_medico_info()
        self.assertTrue(studi)
        self.assertTrue(all(s["orari"] for s in studi))
        self.assertTrue(contatti)

    # --- Orari della dr. Marzo ---

    def test_marzo_schedule_covers_weekdays(self):
        giorni = [g for s in data.MARZO_STUDI for g in s["orari"]]
        self.assertEqual(sorted(giorni, key=data.GIORNI_IT.index), data.GIORNI_IT[:5])

    # --- Scelta del medico ---

    def test_medico_choice_keyboard_lists_all_doctors(self):
        bottoni = [b for riga in messages.medico_choice_keyboard().inline_keyboard for b in riga]
        self.assertEqual([b.callback_data for b in bottoni], [f"medico:{m}" for m in data.MEDICI])
        self.assertEqual([b.text for b in bottoni], list(data.MEDICI.values()))

    def test_save_and_load_medico_utente(self):
        storage.save_medico_utente(42, "marzo")
        self.assertEqual(storage.load_medici_utenti(), {"42": "marzo"})

    def test_load_medici_utenti_without_file(self):
        self.assertEqual(storage.load_medici_utenti(), {})

    async def test_medico_without_choice_asks_doctor(self):
        update = self.make_update()
        await handlers.send_medico_hours(update, self.context)

        self.assertIn("Chi è il tuo medico", update.message.reply_text.call_args.args[0])
        markup = update.message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(len(markup.inline_keyboard), len(data.MEDICI))
        self.context.bot.send_message.assert_not_called()

    async def test_medico_with_unknown_saved_choice_asks_again(self):
        storage.medici_utenti = {"42": "medico_rimosso"}
        update = self.make_update()
        await handlers.send_medico_hours(update, self.context)

        self.assertIn("Chi è il tuo medico", update.message.reply_text.call_args.args[0])

    async def test_choose_marzo_saves_and_sends_hours(self):
        update = self.make_callback_update("medico:marzo")
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 5, 10, 0))):  # lunedì
            await handlers.handle_medico_choice(update, self.context)

        update.callback_query.answer.assert_awaited_once()
        self.assertEqual(storage.load_medici_utenti(), {"42": "marzo"})
        self.assertIn("Valentina Marzo", update.callback_query.edit_message_text.call_args.args[0])

        messaggio = self.sent_texts()[0]
        self.assertIn("Lunedì", messaggio)
        self.assertIn("Taino", messaggio)
        self.assertIn("Via Europa, 11", messaggio)
        self.assertIn("16:00 - 19:00", messaggio)
        self.assertNotIn("Angera", messaggio)

    async def test_saved_marzo_choice_is_used(self):
        storage.medici_utenti = {"42": "marzo"}
        update = self.make_update()
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 6, 10, 0))):  # martedì
            await handlers.send_medico_hours(update, self.context)

        update.message.reply_text.assert_not_called()
        messaggio = self.sent_texts()[0]
        self.assertIn("Angera", messaggio)
        self.assertIn("📞 09:00 - 11:00 Segreteria", messaggio)

        markup = self.context.bot.send_message.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "medico:cambia")

    async def test_saved_htet_choice_uses_comune_page(self):
        storage.medici_utenti = {"42": "htet"}
        update = self.make_update()
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)), \
             patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 6, 10, 0))):  # martedì
            await handlers.send_medico_hours(update, self.context)

        messaggio = self.sent_texts()[0]
        self.assertIn("Htet Htet Ne Win", messaggio)
        self.assertIn("Centro Bielli", messaggio)
        self.assertIn("💊 11:30 - 12:00 Ritiro Ricette", messaggio)
        self.assertIn("Richiesta appuntamenti", messaggio)

    async def test_medico_weekend_not_available(self):
        storage.medici_utenti = {"42": "marzo"}
        with patch.object(utils, "datetime", fake_datetime(datetime(2026, 1, 10, 10, 0))):  # sabato
            await handlers.send_medico_hours(self.make_update(), self.context)

        self.assertIn("non riceve", self.sent_texts()[0])

    async def test_htet_page_error_sends_error_message(self):
        storage.medici_utenti = {"42": "htet"}
        with patch("urllib.request.urlopen", side_effect=OSError("rete assente")):
            await handlers.send_medico_hours(self.make_update(), self.context)

        self.assertIn("Non sono riuscito", self.sent_texts()[0])

    async def test_change_doctor_button_asks_again(self):
        storage.medici_utenti = {"42": "marzo"}
        update = self.make_callback_update("medico:cambia")
        await handlers.handle_medico_choice(update, self.context)

        self.assertIn("Chi è il tuo medico", update.callback_query.message.reply_text.call_args.args[0])
        self.assertEqual(storage.medici_utenti, {"42": "marzo"})
        self.context.bot.send_message.assert_not_called()

    async def test_unknown_doctor_choice_is_ignored(self):
        update = self.make_callback_update("medico:sconosciuto")
        await handlers.handle_medico_choice(update, self.context)

        self.assertEqual(storage.medici_utenti, {})
        update.callback_query.edit_message_text.assert_not_called()
        self.context.bot.send_message.assert_not_called()

    # --- Biblioteca ---

    def test_giorno_da_testo_handles_typos(self):
        self.assertEqual(utils.giorno_da_testo("Lunerdì"), "Lunedì")
        self.assertEqual(utils.giorno_da_testo("martedi"), "Martedì")
        self.assertEqual(utils.giorno_da_testo("Mercoledì"), "Mercoledì")
        self.assertIsNone(utils.giorno_da_testo("Orario"))

    def test_fetch_biblioteca_info_parses_page(self):
        with patch("urllib.request.urlopen", fake_urlopen(BIBLIOTECA_HTML)):
            info = sources.fetch_biblioteca_info()

        self.assertEqual(info["orari"], {
            "Lunedì": ["10:00 - 12:00"],
            "Mercoledì": ["15:00 - 18:00"],
            "Giovedì": ["15:00 - 18:00"],
            "Venerdì": ["10:00 - 12:00"],
            "Sabato": ["10:00 - 12:00"]
        })
        self.assertEqual(info["sede"], "Municipio, Piazza Pajetta, 21020 Taino VA, Italia")
        self.assertEqual(info["email"], "biblioteca@comune.taino.va.it")
        self.assertEqual(info["telefono"], "0331.956405 (int. 8)")
        self.assertEqual(info["aggiornamento"], "18 febbraio 2026, 17:58")

    def test_fetch_biblioteca_info_multiple_slots_per_day(self):
        pagina = BIBLIOTECA_HTML.replace(
            "<li>Sabato dalle 10:00 alle 12:00</li>",
            "<li>Sabato dalle 9.00 alle 12.00 e dalle 14:00 alle 17:00</li>"
        )
        with patch("urllib.request.urlopen", fake_urlopen(pagina)):
            info = sources.fetch_biblioteca_info()

        self.assertEqual(info["orari"]["Sabato"], ["09:00 - 12:00", "14:00 - 17:00"])

    def test_fetch_biblioteca_info_page_without_hours(self):
        with patch("urllib.request.urlopen", fake_urlopen("<html><body>Pagina cambiata</body></html>")):
            with self.assertRaises(ValueError):
                sources.fetch_biblioteca_info()

    @unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS"), "imposta RUN_LIVE_TESTS=1 per usare la pagina reale")
    def test_fetch_biblioteca_info_live_page(self):
        info = sources.fetch_biblioteca_info()
        self.assertTrue(info["orari"])
        self.assertIsNotNone(info["email"])

    async def biblioteca_reply(self, giorno, pagina=BIBLIOTECA_HTML):
        update = self.make_update()
        with patch("urllib.request.urlopen", fake_urlopen(pagina)), \
             patch.object(utils, "datetime", fake_datetime(giorno)):
            await handlers.send_biblioteca_hours(update, self.context)
        self.assertIs(update.message.reply_text.call_args.kwargs["reply_markup"], messages.COMMANDS_KEYBOARD)
        return update.message.reply_text.call_args.args[0]

    async def test_biblioteca_open_today(self):
        messaggio = await self.biblioteca_reply(datetime(2026, 1, 7, 10, 0))  # mercoledì
        self.assertIn("Oggi è *Mercoledì*", messaggio)
        self.assertIn("*APERTA*", messaggio)
        self.assertIn("🕒 15:00 - 18:00", messaggio)

    async def test_biblioteca_closed_today(self):
        messaggio = await self.biblioteca_reply(datetime(2026, 1, 6, 10, 0))  # martedì
        self.assertIn("*CHIUSA*", messaggio)

    async def test_biblioteca_shows_week_and_contacts(self):
        messaggio = await self.biblioteca_reply(datetime(2026, 1, 6, 10, 0))
        self.assertIn("• Lunedì: 10:00 - 12:00", messaggio)
        self.assertIn("• Martedì: chiuso", messaggio)
        self.assertIn("• Domenica: chiuso", messaggio)
        self.assertIn("Piazza Pajetta", messaggio)
        self.assertIn("0331.956405 (int. 8)", messaggio)
        self.assertIn("biblioteca@comune.taino.va.it", messaggio)
        self.assertIn("18 febbraio 2026", messaggio)

    async def test_biblioteca_page_error_sends_error_message(self):
        update = self.make_update()
        with patch("urllib.request.urlopen", side_effect=OSError("rete assente")):
            await handlers.send_biblioteca_hours(update, self.context)

        self.assertIn("Non sono riuscito", update.message.reply_text.call_args.args[0])

    # --- Cache delle pagine del Comune ---

    async def test_cache_avoids_second_download(self):
        urlopen = fake_urlopen(BIBLIOTECA_HTML)
        with patch("urllib.request.urlopen", urlopen):
            primo = await web.get_cached("biblioteca", sources.fetch_biblioteca_info)
            secondo = await web.get_cached("biblioteca", sources.fetch_biblioteca_info)

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(primo, secondo)

    async def test_cache_concurrent_requests_download_once(self):
        urlopen = fake_urlopen(BIBLIOTECA_HTML)
        with patch("urllib.request.urlopen", urlopen):
            risultati = await asyncio.gather(*(web.get_cached("biblioteca", sources.fetch_biblioteca_info) for _ in range(5)))

        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(len(risultati), 5)

    async def test_cache_expires(self):
        urlopen = fake_urlopen(BIBLIOTECA_HTML)
        with patch("urllib.request.urlopen", urlopen):
            await web.get_cached("biblioteca", sources.fetch_biblioteca_info)
            istante, valore = web._page_cache["biblioteca"]
            web._page_cache["biblioteca"] = (istante - web.PAGE_CACHE_TTL - 1, valore)
            await web.get_cached("biblioteca", sources.fetch_biblioteca_info)

        self.assertEqual(urlopen.call_count, 2)

    async def test_cache_serves_stale_copy_when_site_is_down(self):
        with patch("urllib.request.urlopen", fake_urlopen(BIBLIOTECA_HTML)):
            valido = await web.get_cached("biblioteca", sources.fetch_biblioteca_info)
        istante, valore = web._page_cache["biblioteca"]
        web._page_cache["biblioteca"] = (istante - web.PAGE_CACHE_TTL - 1, valore)

        with patch("urllib.request.urlopen", side_effect=OSError("rete assente")):
            self.assertEqual(await web.get_cached("biblioteca", sources.fetch_biblioteca_info), valido)

    async def test_cache_without_copy_propagates_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("rete assente")):
            with self.assertRaises(OSError):
                await web.get_cached("biblioteca", sources.fetch_biblioteca_info)
        self.assertNotIn("biblioteca", web._page_cache)

    async def test_error_handler_logs_exception(self):
        try:
            raise RuntimeError("errore di prova")
        except RuntimeError as e:
            errore = e
        with self.assertLogs("trash_bot", level="ERROR") as log:
            await handlers.error_handler(None, SimpleNamespace(error=errore))

        self.assertIn("errore di prova", "\n".join(log.output))

    # --- Log giornalieri ---

    def test_log_rotation_does_not_reopen_file_on_every_record(self):
        handler = logs.logger.handlers[0]
        with patch.object(logs, "datetime", fake_datetime(datetime(2030, 1, 1, 10, 0))):
            logs.logger.info("primo messaggio del nuovo giorno")
            stream = handler.stream
            logs.logger.info("secondo messaggio")
            self.assertIs(handler.stream, stream)

        self.assertTrue(os.path.isabs(handler.baseFilename))
        self.assertTrue(os.path.exists(os.path.join("logs", "bot_2030-01-01.log")))

    def test_old_logs_are_deleted_on_day_change(self):
        vecchio = os.path.join("logs", "bot_2029-12-01.log")
        recente = os.path.join("logs", "bot_2029-12-30.log")
        for nome in (vecchio, recente):
            with open(nome, "w") as f:
                f.write("log\n")

        with patch.object(logs, "datetime", fake_datetime(datetime(2030, 1, 2, 10, 0))):
            logs.logger.info("nuovo giorno")

        self.assertFalse(os.path.exists(vecchio))
        self.assertTrue(os.path.exists(recente))

    # --- Avvio del bot ---

    def test_token_from_environment_overrides_config(self):
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "999:ENV"}), \
             patch.object(Application, "run_polling", autospec=True) as run_polling:
            app.main()

        self.assertEqual(run_polling.call_args.args[0].bot.token, "999:ENV")

    def test_token_from_config_without_environment(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_TOKEN", None)
            with patch.object(Application, "run_polling", autospec=True) as run_polling:
                app.main()

        self.assertEqual(run_polling.call_args.args[0].bot.token, "123:TEST")

    def test_data_dir_from_environment(self):
        cartella = tempfile.mkdtemp(prefix="trash_bot_data_")
        with open(os.path.join(cartella, "config.json"), "w") as f:
            json.dump({"token": "123:DIR", "calendar_file": "cal.json"}, f)
        with open(os.path.join(cartella, "cal.json"), "w") as f:
            json.dump({"01-01-30": ["CARTA"]}, f)

        with patch.dict(os.environ, {"BOT_DATA_DIR": cartella}):
            cfg, calendario = config.load_config()
            storage.add_chat_id(7)
            storage.save_medico_utente(7, "marzo")

        self.assertEqual(cfg["token"], "123:DIR")
        self.assertEqual(calendario, {"01-01-30": ["CARTA"]})
        with open(os.path.join(cartella, "subscribers.json")) as f:
            self.assertEqual(json.load(f), [7])
        self.assertTrue(os.path.exists(os.path.join(cartella, storage.MEDICI_UTENTI_FILE)))
        self.assertFalse(os.path.exists("subscribers.json"))

    def test_import_has_no_side_effects(self):
        cartella_vuota = tempfile.mkdtemp(prefix="trash_bot_import_")
        risultato = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, {PROJECT_DIR!r}); import trash_bot"],
            cwd=cartella_vuota, capture_output=True, text=True
        )
        self.assertEqual(risultato.returncode, 0, risultato.stderr)
        self.assertEqual(os.listdir(cartella_vuota), [])

    def test_main_registers_handlers_and_daily_job(self):
        with patch.object(Application, "run_polling", autospec=True) as run_polling:
            app.main()

        self.assertEqual(sources.calendar_data, CALENDARIO)
        self.assertEqual(len(logs.logger.handlers), 1)
        application = run_polling.call_args.args[0]
        comandi = sorted(c for h in application.handlers[0] if hasattr(h, "commands") for c in h.commands)
        self.assertEqual(comandi, ["biblioteca", "ecocentro", "medico", "start", "trash"])
        self.assertEqual(len(application.handlers[0]), 7)
        self.assertGreater(application.update_processor.max_concurrent_updates, 1)
        self.assertIn(handlers.error_handler, application.error_handlers)
        job = application.job_queue.get_jobs_by_name("daily_trash_notification")
        self.assertEqual(len(job), 1)
        trigger = job[0].job.trigger
        self.assertIn("hour='20'", str(trigger))
        self.assertIn("minute='0'", str(trigger))
        self.assertEqual(str(trigger.timezone), "Europe/Rome")

    # --- Testi esatti di tutti i messaggi ---

    async def record_scenario(self, scenario, giorno, chat_id=42):
        """Esegue uno scenario e registra, in ordine, tutti i messaggi inviati o modificati dal bot."""
        chiamate = []

        def recorder(tipo):
            async def registra(*args, **kwargs):
                chiamate.append({
                    "tipo": tipo,
                    "testo": args[0] if args else kwargs.get("text"),
                    "parse_mode": kwargs.get("parse_mode"),
                    "markup": describe_markup(kwargs.get("reply_markup"))
                })
                return SimpleNamespace(message_id=100)
            return registra

        message = SimpleNamespace(reply_text=AsyncMock(side_effect=recorder("reply_text")), delete=AsyncMock())
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), message=message, effective_message=message)
        query = SimpleNamespace(
            data=None,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(side_effect=recorder("edit_message_text")),
            message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), reply_text=AsyncMock(side_effect=recorder("reply_text")))
        )
        callback_update = SimpleNamespace(callback_query=query)
        self.context.bot.send_message = AsyncMock(side_effect=recorder("send_message"))

        with patch.object(utils, "datetime", fake_datetime(giorno)):
            await scenario(update, callback_update)
        return chiamate

    async def collect_all_scenarios(self):
        lun, mar, mer, sab = datetime(2026, 1, 5, 18), datetime(2026, 1, 6, 10), datetime(2026, 1, 7, 10), datetime(2026, 1, 10, 10)
        estate_lun, estate_sab = datetime(2026, 6, 1, 10), datetime(2026, 6, 6, 10)
        ctx = self.context
        htet = patch("urllib.request.urlopen", fake_urlopen(HTET_HTML))
        biblioteca = patch("urllib.request.urlopen", fake_urlopen(BIBLIOTECA_HTML))
        rete_assente = patch("urllib.request.urlopen", side_effect=OSError("rete assente"))

        def reset(subscribers=(), medici=None):
            storage.subscribers = list(subscribers)
            storage.medici_utenti = dict(medici or {})
            web._page_cache.clear()
            ctx.chat_data.clear()

        async def scelta(dato, cu):
            cu.callback_query.data = dato
            await handlers.handle_medico_choice(cu, ctx)

        scenari = []

        def add(nome, funzione, giorno, setup=None, rete=None):
            scenari.append((nome, funzione, giorno, setup or {}, rete))

        add("start", lambda u, cu: handlers.start(u, ctx), lun)
        add("trash_nuovo_iscritto", lambda u, cu: handlers.send_trash_exposure(u, ctx), lun)
        add("trash_iscritto", lambda u, cu: handlers.send_trash_exposure(u, ctx), lun, {"subscribers": [42]})
        add("trash_niente_domani", lambda u, cu: handlers.send_trash_exposure(u, ctx), sab, {"subscribers": [42]})
        add("trash_rifiuto_sconosciuto", lambda u, cu: handlers.send_trash_exposure(u, ctx), mer, {"subscribers": [42]})
        add("notifica_serale", lambda u, cu: handlers.send_daily_notification(ctx), mar, {"subscribers": [1, 2]})
        add("ecocentro_inverno_lunedi", lambda u, cu: handlers.send_ecocentro_openings(u, ctx), lun)
        add("ecocentro_inverno_chiuso", lambda u, cu: handlers.send_ecocentro_openings(u, ctx), mar)
        add("ecocentro_inverno_sabato", lambda u, cu: handlers.send_ecocentro_openings(u, ctx), sab)
        add("ecocentro_estate_lunedi", lambda u, cu: handlers.send_ecocentro_openings(u, ctx), estate_lun)
        add("ecocentro_estate_sabato", lambda u, cu: handlers.send_ecocentro_openings(u, ctx), estate_sab)
        add("medico_domanda", lambda u, cu: handlers.send_medico_hours(u, ctx), lun)
        add("medico_scelta_marzo", lambda u, cu: scelta("medico:marzo", cu), lun)
        add("medico_scelta_htet", lambda u, cu: scelta("medico:htet", cu), mar, rete=htet)
        add("medico_cambia", lambda u, cu: scelta("medico:cambia", cu), lun, {"medici": {"42": "marzo"}})
        add("medico_marzo_martedi", lambda u, cu: handlers.send_medico_hours(u, ctx), mar, {"medici": {"42": "marzo"}})
        add("medico_marzo_sabato", lambda u, cu: handlers.send_medico_hours(u, ctx), sab, {"medici": {"42": "marzo"}})
        add("medico_htet_mercoledi", lambda u, cu: handlers.send_medico_hours(u, ctx), mer, {"medici": {"42": "htet"}}, htet)
        add("medico_htet_errore", lambda u, cu: handlers.send_medico_hours(u, ctx), mar, {"medici": {"42": "htet"}}, rete_assente)
        add("biblioteca_aperta", lambda u, cu: handlers.send_biblioteca_hours(u, ctx), mer, rete=biblioteca)
        add("biblioteca_chiusa", lambda u, cu: handlers.send_biblioteca_hours(u, ctx), mar, rete=biblioteca)
        add("biblioteca_errore", lambda u, cu: handlers.send_biblioteca_hours(u, ctx), mar, rete=rete_assente)
        add("messaggio_libero_nuovo", lambda u, cu: handlers.handle_message(u, ctx), lun)
        add("messaggio_libero_iscritto", lambda u, cu: handlers.handle_message(u, ctx), lun, {"subscribers": [42]})

        risultati = {}
        for nome, funzione, giorno, setup, rete in scenari:
            reset(**setup)
            if rete:
                with rete:
                    risultati[nome] = await self.record_scenario(funzione, giorno)
            else:
                risultati[nome] = await self.record_scenario(funzione, giorno)
        return risultati

    async def test_exact_message_texts(self):
        risultati = await self.collect_all_scenarios()

        if os.environ.get("UPDATE_SNAPSHOTS"):
            os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
            with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(risultati, f, ensure_ascii=False, indent=2)
            self.skipTest("snapshot rigenerati")

        with open(SNAPSHOT_FILE, encoding="utf-8") as f:
            attesi = json.load(f)
        self.assertEqual(sorted(risultati), sorted(attesi))
        for nome in attesi:
            with self.subTest(scenario=nome):
                self.assertEqual(risultati[nome], attesi[nome])


if __name__ == "__main__":
    unittest.main()
