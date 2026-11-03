"""Test del bot Rifiuti Taino.

Esecuzione dalla cartella del progetto:
    python -m unittest discover test -v

I test non usano la rete né Telegram: le chiamate al bot e la pagina del Comune sono simulate.
Per provare anche il parsing sulla pagina reale del Comune:
    RUN_LIVE_TESTS=1 python -m unittest discover test -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# trash_bot legge config.json e il calendario all'import e scrive log e file JSON
# nella cartella corrente: lavoriamo in una cartella temporanea per non toccare i file veri.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = tempfile.mkdtemp(prefix="trash_bot_test_")
CALENDARIO = {
    "06-01-26": ["UMIDO", "CARTA", "PLASTICA"],
    "07-01-26": ["umido ", "VETRO E LATTINE"],
    "08-01-26": ["INGOMBRANTI"]
}
with open(os.path.join(TEST_DIR, "config.json"), "w") as f:
    json.dump({"token": "123:TEST", "calendar_file": "calendario.json"}, f)
with open(os.path.join(TEST_DIR, "calendario.json"), "w") as f:
    json.dump(CALENDARIO, f)
os.chdir(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

import trash_bot as tb  # noqa: E402

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
        tb.subscribers = []
        tb.medici_utenti = {}
        for nome in ("subscribers.json", tb.MEDICI_UTENTI_FILE):
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

    def make_callback_update(self, data, chat_id=42):
        query = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(chat=SimpleNamespace(id=chat_id), reply_text=AsyncMock())
        )
        return SimpleNamespace(callback_query=query)

    def sent_texts(self):
        return [c.kwargs["text"] for c in self.context.bot.send_message.call_args_list]

    # --- Tastiera dei comandi ---

    def test_commands_keyboard_has_all_commands(self):
        testi = [b.text for riga in tb.COMMANDS_KEYBOARD.keyboard for b in riga]
        self.assertEqual(testi, ["/trash", "/ecocentro", "/medico", "/biblioteca"])
        self.assertTrue(tb.COMMANDS_KEYBOARD.is_persistent)
        self.assertTrue(tb.COMMANDS_KEYBOARD.resize_keyboard)

    # --- Messaggio dei rifiuti ---

    def test_format_trash_message_empty(self):
        self.assertIn("non c'è niente da esporre", tb.format_trash_message([]))

    def test_format_trash_message_known_items(self):
        messaggio = tb.format_trash_message(["UMIDO", "CARTA", "PLASTICA", "VETRO E LATTINE", "SECCO"])
        for voce in tb.TRASH_ICONS.values():
            self.assertIn(voce, messaggio)

    def test_format_trash_message_normalizes_case_and_spaces(self):
        self.assertIn(tb.TRASH_ICONS["UMIDO"], tb.format_trash_message([" umido "]))

    def test_format_trash_message_unknown_item(self):
        self.assertIn("🔹 *INGOMBRANTI*", tb.format_trash_message(["INGOMBRANTI"]))

    def test_get_trash_exposure_date_returns_tomorrow(self):
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 18, 0))):
            self.assertEqual(tb.get_trash_exposure_date(), ["UMIDO", "CARTA", "PLASTICA"])

    def test_get_trash_exposure_date_no_collection(self):
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 10, 18, 0))):
            self.assertEqual(tb.get_trash_exposure_date(), [])

    # --- Iscritti alle notifiche ---

    def test_add_chat_id_saves_new_subscriber(self):
        self.assertTrue(tb.add_chat_id(42))
        with open("subscribers.json") as f:
            self.assertEqual(json.load(f), [42])
        self.assertEqual(tb.load_subscribers(), [42])

    def test_add_chat_id_ignores_duplicates(self):
        tb.add_chat_id(42)
        self.assertFalse(tb.add_chat_id(42))
        self.assertEqual(tb.subscribers, [42])

    def test_load_subscribers_without_file(self):
        self.assertEqual(tb.load_subscribers(), [])

    # --- Comandi /start, /trash e messaggi liberi ---

    async def test_start_subscribes_and_shows_keyboard(self):
        update = self.make_update()
        await tb.start(update, self.context)

        self.assertEqual(tb.subscribers, [42])
        kwargs = update.message.reply_text.call_args.kwargs
        self.assertIs(kwargs["reply_markup"], tb.COMMANDS_KEYBOARD)
        self.assertIn("/medico", update.message.reply_text.call_args.args[0])
        self.assertIn("/biblioteca", update.message.reply_text.call_args.args[0])

    async def test_trash_command_new_subscriber(self):
        update = self.make_update()
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 18, 0))):
            await tb.send_trash_exposure(update, self.context)

        self.assertEqual(tb.subscribers, [42])
        self.assertIn("aggiunto", update.message.reply_text.call_args.args[0])
        self.assertIn(tb.TRASH_ICONS["CARTA"], self.sent_texts()[0])
        self.assertIs(self.context.bot.send_message.call_args.kwargs["reply_markup"], tb.COMMANDS_KEYBOARD)

    async def test_trash_command_existing_subscriber(self):
        tb.subscribers = [42]
        update = self.make_update()
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 18, 0))):
            await tb.send_trash_exposure(update, self.context)

        update.message.reply_text.assert_not_called()
        self.context.bot.send_message.assert_called_once()

    def test_commands_keyboard_has_placeholder(self):
        self.assertIn("bottoni", tb.COMMANDS_KEYBOARD.input_field_placeholder)

    async def test_handle_message_new_user_is_subscribed(self):
        update = self.make_update()
        await tb.handle_message(update, self.context)

        self.assertEqual(tb.subscribers, [42])
        update.message.delete.assert_awaited_once()
        self.assertIn("aggiunto", self.sent_texts()[0])

    async def test_handle_message_deletes_text_and_shows_keyboard(self):
        tb.subscribers = [42]
        update = self.make_update()
        await tb.handle_message(update, self.context)

        update.message.delete.assert_awaited_once()
        self.assertIn("solo con i bottoni", self.sent_texts()[0])
        self.assertIs(self.context.bot.send_message.call_args.kwargs["reply_markup"], tb.COMMANDS_KEYBOARD)
        self.assertEqual(self.context.chat_data["hint_message_id"], 100)

    async def test_handle_message_replaces_previous_hint(self):
        tb.subscribers = [42]
        self.context.chat_data["hint_message_id"] = 99
        await tb.handle_message(self.make_update(), self.context)

        self.context.bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=99)
        self.assertEqual(self.context.chat_data["hint_message_id"], 100)

    async def test_handle_message_works_if_delete_fails(self):
        tb.subscribers = [42]
        update = self.make_update()
        update.message.delete.side_effect = Exception("messaggio troppo vecchio")
        self.context.chat_data["hint_message_id"] = 99
        self.context.bot.delete_message.side_effect = Exception("promemoria già cancellato")
        await tb.handle_message(update, self.context)

        self.context.bot.send_message.assert_awaited_once()
        self.assertEqual(self.context.chat_data["hint_message_id"], 100)

    # --- Notifica giornaliera ---

    async def test_daily_notification_sends_to_all_subscribers(self):
        tb.subscribers = [1, 2]
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 20, 0))):
            await tb.send_daily_notification(self.context)

        chat_ids = [c.kwargs["chat_id"] for c in self.context.bot.send_message.call_args_list]
        self.assertEqual(chat_ids, [1, 2])

    async def test_daily_notification_skipped_without_collection(self):
        tb.subscribers = [1]
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 10, 20, 0))):
            await tb.send_daily_notification(self.context)

        self.context.bot.send_message.assert_not_called()

    async def test_daily_notification_without_subscribers(self):
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 20, 0))):
            await tb.send_daily_notification(self.context)

        self.context.bot.send_message.assert_not_called()

    async def test_daily_notification_continues_after_error(self):
        tb.subscribers = [1, 2]
        self.context.bot.send_message.side_effect = [Exception("bot bloccato"), None]
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 20, 0))):
            await tb.send_daily_notification(self.context)

        self.assertEqual(self.context.bot.send_message.call_count, 2)

    # --- Ecocentro ---

    async def ecocentro_reply(self, giorno):
        update = self.make_update()
        with patch.object(tb, "datetime", fake_datetime(giorno)):
            await tb.send_ecocentro_openings(update, self.context)
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
            studi, contatti = tb.fetch_medico_info()

        self.assertEqual([s["nome"] for s in studi], ["Taino", "Angera"])
        self.assertEqual(studi[0]["indirizzo"], "c/o Centro Bielli - Via Europa, 15")
        self.assertEqual(studi[1]["indirizzo"], "Piazza Parrocchiale, 8")
        self.assertEqual(studi[0]["orari"]["Martedì"], [("09:00 - 11:00", "Ambulatorio"), ("11:30 - 12:00", "Ritiro Ricette")])
        self.assertEqual(studi[1]["orari"]["Lunedì"], [("13:00 - 16:00", "Ambulatorio")])
        self.assertEqual(set(studi[0]["orari"]), {"Martedì", "Giovedì"})
        self.assertEqual(set(studi[1]["orari"]), {"Lunedì", "Mercoledì", "Venerdì"})

    def test_fetch_medico_info_unlabeled_slot_is_ambulatorio(self):
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)):
            studi, _ = tb.fetch_medico_info()

        self.assertEqual(studi[1]["orari"]["Mercoledì"], [("15:00 - 18:00", "Ambulatorio"), ("18:30 - 19:00", "Ritiro Ricette")])

    def test_fetch_medico_info_parses_contacts(self):
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)):
            _, contatti = tb.fetch_medico_info()

        self.assertEqual(len(contatti), 2)
        self.assertTrue(contatti[0].startswith("Richiesta ricette"))
        self.assertTrue(contatti[1].startswith("Richiesta appuntamenti"))
        self.assertIn("lunedì", contatti[1])

    def test_fetch_medico_info_page_without_description(self):
        with patch("urllib.request.urlopen", fake_urlopen("<html><body>Pagina cambiata</body></html>")):
            with self.assertRaises(ValueError):
                tb.fetch_medico_info()

    @unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS"), "imposta RUN_LIVE_TESTS=1 per usare la pagina reale")
    def test_fetch_medico_info_live_page(self):
        studi, contatti = tb.fetch_medico_info()
        self.assertTrue(studi)
        self.assertTrue(all(s["orari"] for s in studi))
        self.assertTrue(contatti)

    # --- Orari della dr. Marzo ---

    def test_marzo_schedule_covers_weekdays(self):
        giorni = [g for s in tb.MARZO_STUDI for g in s["orari"]]
        self.assertEqual(sorted(giorni, key=tb.GIORNI_IT.index), tb.GIORNI_IT[:5])

    # --- Scelta del medico ---

    def test_medico_choice_keyboard_lists_all_doctors(self):
        bottoni = [b for riga in tb.medico_choice_keyboard().inline_keyboard for b in riga]
        self.assertEqual([b.callback_data for b in bottoni], [f"medico:{m}" for m in tb.MEDICI])
        self.assertEqual([b.text for b in bottoni], list(tb.MEDICI.values()))

    def test_save_and_load_medico_utente(self):
        tb.save_medico_utente(42, "marzo")
        self.assertEqual(tb.load_medici_utenti(), {"42": "marzo"})

    def test_load_medici_utenti_without_file(self):
        self.assertEqual(tb.load_medici_utenti(), {})

    async def test_medico_without_choice_asks_doctor(self):
        update = self.make_update()
        await tb.send_medico_hours(update, self.context)

        self.assertIn("Chi è il tuo medico", update.message.reply_text.call_args.args[0])
        markup = update.message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(len(markup.inline_keyboard), len(tb.MEDICI))
        self.context.bot.send_message.assert_not_called()

    async def test_medico_with_unknown_saved_choice_asks_again(self):
        tb.medici_utenti = {"42": "medico_rimosso"}
        update = self.make_update()
        await tb.send_medico_hours(update, self.context)

        self.assertIn("Chi è il tuo medico", update.message.reply_text.call_args.args[0])

    async def test_choose_marzo_saves_and_sends_hours(self):
        update = self.make_callback_update("medico:marzo")
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 5, 10, 0))):  # lunedì
            await tb.handle_medico_choice(update, self.context)

        update.callback_query.answer.assert_awaited_once()
        self.assertEqual(tb.load_medici_utenti(), {"42": "marzo"})
        self.assertIn("Valentina Marzo", update.callback_query.edit_message_text.call_args.args[0])

        messaggio = self.sent_texts()[0]
        self.assertIn("Lunedì", messaggio)
        self.assertIn("Taino", messaggio)
        self.assertIn("Via Europa, 11", messaggio)
        self.assertIn("16:00 - 19:00", messaggio)
        self.assertNotIn("Angera", messaggio)

    async def test_saved_marzo_choice_is_used(self):
        tb.medici_utenti = {"42": "marzo"}
        update = self.make_update()
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 6, 10, 0))):  # martedì
            await tb.send_medico_hours(update, self.context)

        update.message.reply_text.assert_not_called()
        messaggio = self.sent_texts()[0]
        self.assertIn("Angera", messaggio)
        self.assertIn("📞 09:00 - 11:00 Segreteria", messaggio)

        markup = self.context.bot.send_message.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "medico:cambia")

    async def test_saved_htet_choice_uses_comune_page(self):
        tb.medici_utenti = {"42": "htet"}
        update = self.make_update()
        with patch("urllib.request.urlopen", fake_urlopen(HTET_HTML)), \
             patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 6, 10, 0))):  # martedì
            await tb.send_medico_hours(update, self.context)

        messaggio = self.sent_texts()[0]
        self.assertIn("Htet Htet Ne Win", messaggio)
        self.assertIn("Centro Bielli", messaggio)
        self.assertIn("💊 11:30 - 12:00 Ritiro Ricette", messaggio)
        self.assertIn("Richiesta appuntamenti", messaggio)

    async def test_medico_weekend_not_available(self):
        tb.medici_utenti = {"42": "marzo"}
        with patch.object(tb, "datetime", fake_datetime(datetime(2026, 1, 10, 10, 0))):  # sabato
            await tb.send_medico_hours(self.make_update(), self.context)

        self.assertIn("non riceve", self.sent_texts()[0])

    async def test_htet_page_error_sends_error_message(self):
        tb.medici_utenti = {"42": "htet"}
        with patch("urllib.request.urlopen", side_effect=OSError("rete assente")):
            await tb.send_medico_hours(self.make_update(), self.context)

        self.assertIn("Non sono riuscito", self.sent_texts()[0])

    async def test_change_doctor_button_asks_again(self):
        tb.medici_utenti = {"42": "marzo"}
        update = self.make_callback_update("medico:cambia")
        await tb.handle_medico_choice(update, self.context)

        self.assertIn("Chi è il tuo medico", update.callback_query.message.reply_text.call_args.args[0])
        self.assertEqual(tb.medici_utenti, {"42": "marzo"})
        self.context.bot.send_message.assert_not_called()

    async def test_unknown_doctor_choice_is_ignored(self):
        update = self.make_callback_update("medico:sconosciuto")
        await tb.handle_medico_choice(update, self.context)

        self.assertEqual(tb.medici_utenti, {})
        update.callback_query.edit_message_text.assert_not_called()
        self.context.bot.send_message.assert_not_called()

    # --- Biblioteca ---

    def test_giorno_da_testo_handles_typos(self):
        self.assertEqual(tb.giorno_da_testo("Lunerdì"), "Lunedì")
        self.assertEqual(tb.giorno_da_testo("martedi"), "Martedì")
        self.assertEqual(tb.giorno_da_testo("Mercoledì"), "Mercoledì")
        self.assertIsNone(tb.giorno_da_testo("Orario"))

    def test_fetch_biblioteca_info_parses_page(self):
        with patch("urllib.request.urlopen", fake_urlopen(BIBLIOTECA_HTML)):
            info = tb.fetch_biblioteca_info()

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
            info = tb.fetch_biblioteca_info()

        self.assertEqual(info["orari"]["Sabato"], ["09:00 - 12:00", "14:00 - 17:00"])

    def test_fetch_biblioteca_info_page_without_hours(self):
        with patch("urllib.request.urlopen", fake_urlopen("<html><body>Pagina cambiata</body></html>")):
            with self.assertRaises(ValueError):
                tb.fetch_biblioteca_info()

    @unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS"), "imposta RUN_LIVE_TESTS=1 per usare la pagina reale")
    def test_fetch_biblioteca_info_live_page(self):
        info = tb.fetch_biblioteca_info()
        self.assertTrue(info["orari"])
        self.assertIsNotNone(info["email"])

    async def biblioteca_reply(self, giorno, pagina=BIBLIOTECA_HTML):
        update = self.make_update()
        with patch("urllib.request.urlopen", fake_urlopen(pagina)), \
             patch.object(tb, "datetime", fake_datetime(giorno)):
            await tb.send_biblioteca_hours(update, self.context)
        self.assertIs(update.message.reply_text.call_args.kwargs["reply_markup"], tb.COMMANDS_KEYBOARD)
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
            await tb.send_biblioteca_hours(update, self.context)

        self.assertIn("Non sono riuscito", update.message.reply_text.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
