# ♻️ Rifiuti Taino

Un bot Telegram per i cittadini di **Taino (VA)**. Ti ricorda quali rifiuti esporre la sera prima della raccolta e ti dice se oggi l'ecocentro e la biblioteca sono aperti e dove riceve il medico di base.

> ℹ️ Il progetto è nato per iniziativa personale e **non è un servizio ufficiale** del Comune di Taino. Per qualsiasi dubbio fanno fede i canali ufficiali del Comune.

---

## 👋 Per i cittadini

### Cosa fa il bot

| Bottone | Cosa ti risponde |
|---|---|
| **/trash** | Quali rifiuti esporre domani (umido, carta, plastica, vetro e lattine, secco) |
| **/ecocentro** | Se l'ecocentro di Taino è aperto oggi e con quale orario |
| **/medico** | In quale studio (Taino o Angera) riceve oggi il **tuo** medico di base, con gli orari e i contatti per prendere appuntamento |
| **/biblioteca** | Se la biblioteca di Taino è aperta oggi, gli orari di tutta la settimana, l'indirizzo e i contatti |

In più, **ogni sera alle 20:00** il bot ti manda un promemoria con i rifiuti da esporre per il giorno dopo. Se il giorno dopo non c'è raccolta, non ricevi nessun messaggio.

### Come si usa

1. Apri il bot su Telegram e premi **Avvia** (oppure scrivi `/start`).
2. Al posto della tastiera compaiono i bottoni **/trash**, **/ecocentro**, **/medico** e **/biblioteca**. Premi quello che ti serve.
3. Da questo momento ricevi anche il promemoria serale delle 20:00.

La prima volta che premi **/medico** il bot ti chiede chi è il tuo medico di base (Htet Htet Ne Win o Valentina Marzo) e se lo ricorda per le volte successive. Per cambiarlo, premi **🔄 Cambia medico** sotto la risposta.

Il bot si usa **solo con i bottoni**. Se scrivi un messaggio a mano, il bot lo cancella e ti ricorda di usare i bottoni.

### Orari dei medici di base

Ecco gli orari settimanali che il bot conosce. Premendo **/medico** ti mostra solo quelli di oggi del tuo medico.

**Htet Htet Ne Win**

| Giorno | Studio | Ambulatorio | Ritiro ricette |
|---|---|---|---|
| Lunedì | Angera, Piazza Parrocchiale 8 | 13:00 - 16:00 | — |
| Martedì | Taino, c/o Centro Bielli - Via Europa 15 | 09:00 - 11:00 | 11:30 - 12:00 |
| Mercoledì | Angera | 15:00 - 18:00 | 18:30 - 19:00 |
| Giovedì | Taino | 09:00 - 11:00 | 11:30 - 12:00 |
| Venerdì | Angera | 15:00 - 18:00 | 18:30 - 19:00 |

Appuntamenti e ricette: chiamata o WhatsApp al 327 2704456, dal lunedì al venerdì dalle 8:00 alle 9:00.

**Valentina Marzo**

| Giorno | Studio | Segreteria | Medico (su appuntamento) |
|---|---|---|---|
| Lunedì | Taino, Via Europa 11 | 09:00 - 11:00 | 16:00 - 19:00 |
| Martedì | Angera, Piazza Parrocchiale 8 | 09:00 - 11:00 | 16:00 - 19:00 |
| Mercoledì | Taino | 09:00 - 11:00 | 15:00 - 18:00 |
| Giovedì | Angera | 09:00 - 11:00 | 15:00 - 18:00 |
| Venerdì | Taino | 09:00 - 11:00 | 16:30 - 19:30 |

Segreteria: 351 83 69 125 dalle 9:00 alle 10:00. Medico: 351 33 69 124, solo dopo un primo contatto con la segreteria. E-mail: dr.v.marzo@gmail.com.

> Queste tabelle sono un riepilogo e potrebbero non essere aggiornate. Il bot legge gli orari della dott.ssa Htet in tempo reale dal sito del Comune, quindi la risposta di **/medico** è sempre la fonte più aggiornata.

### Da dove vengono le informazioni

- **Raccolta rifiuti**: dal calendario della raccolta differenziata, copiato nel file del bot all'inizio di ogni anno.
- **Ecocentro**: dagli orari estivi (maggio-ottobre) e invernali (novembre-aprile) dell'ecocentro di Taino.
- **Medico**:
  - *Htet Htet Ne Win*: orari letti in tempo reale, ogni volta che premi il bottone, dalla [news del Comune di Taino](https://www.comune.taino.va.it/it/news/132139/nuovo-medico-di-medicina-generale).
  - *Valentina Marzo*: orari presi dal volantino dell'ambulatorio (`data/marzo.pdf`).
- **Biblioteca**: orari letti in tempo reale, ogni volta che premi il bottone, dalla [pagina della biblioteca](https://www.comune.taino.va.it/it/unita_organizzative/biblioteca) sul sito del Comune. In fondo alla risposta il bot indica la data dell'ultimo aggiornamento della pagina.

---

## 🛠️ Per gli sviluppatori

### Requisiti

- Python **3.9 o superiore** (serve `zoneinfo`)
- Un bot Telegram e il suo token, che si ottengono da [@BotFather](https://t.me/BotFather)
- Le librerie:
  - [`python-telegram-bot`](https://python-telegram-bot.org/) **v20 o superiore**, con l'extra `job-queue` per le notifiche programmate
  - `pytz`

### Installazione

```bash
git clone https://github.com/pinasu/rifiutitaino.git
cd rifiutitaino

python -m venv venv
source venv/bin/activate          # su Windows: venv\Scripts\activate

pip install "python-telegram-bot[job-queue]>=20" pytz
```

### Configurazione

Crea un file `config.json` nella cartella del progetto. Il file è escluso da Git perché contiene il token del bot.

```json
{
  "token": "123456789:ABC-IL-TUO-TOKEN",
  "calendar_file": "2026.json",
  "notifications": {
    "enabled": true,
    "time": "20:00"
  }
}
```

| Campo | Descrizione |
|---|---|
| `token` | Token del bot rilasciato da BotFather |
| `calendar_file` | File JSON con il calendario della raccolta |
| `notifications.enabled` | `true` per attivare il promemoria giornaliero |
| `notifications.time` | Orario del promemoria (`HH:MM`, fuso Europe/Rome) |

> Se cambi `notifications.time`, ricorda che il testo dei messaggi del bot cita ancora "le 20:00".

### Avvio

```bash
python trash_bot.py
```

Il bot usa il *long polling*, quindi non servono webhook, domini o porte aperte: basta una macchina sempre accesa con accesso a Internet, per esempio un Raspberry Pi o una piccola VPS.

### Test

I test sono in `test/test_trash_bot.py`, nella classe `TestTrashBot`, e usano solo `unittest` della libreria standard. Per eseguirli, dalla cartella del progetto:

```bash
python -m unittest discover test -v
```

I test non si collegano a Telegram né alla rete: le risposte del bot e la pagina del Comune sono simulate, e la data di "oggi" è fissata in ogni test. Lavorano in una cartella temporanea, con un `config.json` e un calendario di prova, quindi non toccano `config.json`, `subscribers.json` o `medici_utenti.json` veri.

Coprono la tastiera dei comandi, il messaggio dei rifiuti, le iscrizioni, la notifica serale, gli orari dell'ecocentro (estivi e invernali), il parsing delle pagine del Comune (medico e biblioteca), tutto il flusso di scelta del medico e la risposta di `/biblioteca`.

Per controllare anche che il parsing funzioni sulle **pagine reali** del Comune (utile se si sospetta che siano cambiate):

```bash
RUN_LIVE_TESTS=1 python -m unittest discover test -v      # su Windows PowerShell: $env:RUN_LIVE_TESTS=1; python -m unittest discover test -v
```

### Calendario della raccolta

Il calendario è un file JSON. Ogni chiave è una data in formato `GG-MM-AA` e il valore è la lista dei rifiuti da esporre quel giorno:

```json
{
  "02-01-26": ["UMIDO", "CARTA", "PLASTICA"],
  "05-01-26": ["UMIDO", "VETRO E LATTINE"],
  "12-01-26": ["UMIDO", "SECCO"]
}
```

Il bot cerca la data di **domani**, perché i rifiuti si espongono la sera prima. Questi valori hanno un'icona dedicata: `UMIDO`, `CARTA`, `PLASTICA`, `VETRO E LATTINE`, `SECCO`. Qualsiasi altro valore viene mostrato con un'icona generica.

**Ogni anno** va creato il nuovo file (per esempio `2027.json`) e aggiornato `calendar_file` in `config.json`.

### Struttura del progetto

```
rifiutitaino/
├── trash_bot.py        # Codice del bot
├── 2026.json           # Calendario della raccolta dell'anno corrente
├── config.json         # Configurazione e token (non versionato)
├── data/
│   └── marzo.pdf       # Volantino con gli orari della dr. Marzo
├── test/
│   └── test_trash_bot.py  # Test automatici del bot
├── subscribers.json    # Chat iscritte alle notifiche (generato, non versionato)
├── medici_utenti.json  # Medico scelto da ogni chat (generato, non versionato)
└── logs/               # Log giornalieri (generati, non versionati)
```

### Come funziona

- **Comandi e bottoni**: i bottoni sono una `ReplyKeyboardMarkup` persistente. Quando l'utente preme un bottone, Telegram invia in chat il testo del bottone (`/trash`, ...) come se l'avesse scritto l'utente, e lo gestisce il `CommandHandler` corrispondente.
- **Solo bottoni**: Telegram non permette ai bot di disattivare il campo di testo, quindi:
  - nel campo di testo compare la scritta "Usa i bottoni qui sotto 👇" (`input_field_placeholder`);
  - `handle_message`, registrato per ultimo con `filters.ALL`, riceve tutto ciò che non è un comando dei bottoni (testo libero, comandi sconosciuti, foto, messaggi modificati). Cancella il messaggio e risponde con un promemoria;
  - l'id del promemoria viene salvato in `context.chat_data`, e il promemoria precedente viene cancellato prima di mandarne uno nuovo, così in chat ne resta sempre uno solo.
- **Iscrizioni**: ogni chat che usa `/start`, `/trash` o scrive un messaggio viene aggiunta a `subscribers.json` e riceve il promemoria serale.
- **Promemoria**: è un job giornaliero della `JobQueue`, all'orario indicato in `config.json`.
- **Ecocentro**: gli orari sono scritti direttamente nel codice (`send_ecocentro_openings`). Se il Comune li cambia, vanno aggiornati lì.
- **Medico**: i medici disponibili sono elencati nel dizionario `MEDICI`. La prima volta che una chat usa `/medico`, il bot mostra dei bottoni inline per scegliere. La scelta arriva a `handle_medico_choice` (un `CallbackQueryHandler` con `callback_data` `medico:<id>`) e viene salvata in `medici_utenti.json`, con l'id della chat come chiave.
  - *Htet*: `fetch_medico_info` scarica la pagina del Comune e ne legge il testo riga per riga. Una riga in maiuscolo come `TAINO …` apre un nuovo studio, una riga come `Martedì - 9.00/11.00 Ambulatorio …` aggiunge gli orari di quel giorno. Usa solo la libreria standard (`urllib`, `re`, `html`).
  - *Marzo*: gli orari sono scritti a mano in `MARZO_STUDI` e `MARZO_CONTATTI`, copiati da `data/marzo.pdf`. Se esce un volantino nuovo, vanno aggiornati lì.
- **Biblioteca**: `fetch_biblioteca_info` scarica la pagina della biblioteca e legge l'elenco degli orari nella sezione "Ulteriori informazioni" (righe come `Mercoledì dalle 15:00 alle 18:00`), più sede, email, telefono e data di ultimo aggiornamento. Il giorno viene riconosciuto dalle prime tre lettere (`giorno_da_testo`), così il bot regge refusi come il "Lunerdì" presente oggi sulla pagina. Gli orari vengono letti a coppie, quindi funziona anche con più fasce nello stesso giorno ("dalle 9 alle 12 e dalle 15 alle 18").
- **Pagine web**: `fetch_page` scarica le pagine e `html_to_text` ne estrae il testo. Le usano sia `/medico` sia `/biblioteca`.
- **Log**: i log finiscono in `logs/bot_AAAA-MM-GG.log`, un file al giorno, e i file più vecchi di 7 giorni vengono cancellati.

### Limiti noti

- Gli orari della dr. Marzo non si aggiornano da soli: vanno ricopiati nel codice a ogni nuovo volantino.
- La pagina della dott.ssa Htet è scritta a mano sul sito del Comune. Se cambia il formato del testo, o se gli orari nuovi escono in un'altra news, `/medico` va adattato (`MEDICO_URL` e `fetch_medico_info`).
- Anche `/biblioteca` dipende dalla struttura della pagina del Comune. Se gli orari spariscono dall'elenco della sezione "Ulteriori informazioni", il bot risponde che non riesce a recuperarli e `fetch_biblioteca_info` va adattato.
- Non si può impedire del tutto di scrivere: è un limite di Telegram. Toccando il campo di testo compare comunque la tastiera del telefono, ma i messaggi scritti vengono cancellati. Scrivere a mano un comando valido (es. `/trash`) funziona come premere il bottone.
- L'id dell'ultimo promemoria è tenuto in memoria: dopo un riavvio del bot, il promemoria precedente non viene cancellato.
- Il calendario della raccolta va aggiornato a mano ogni anno.
- Un utente non può disiscriversi dal promemoria: per ora bisogna togliere la sua chat da `subscribers.json`.

### Aggiungere un comando

1. Scrivi la funzione `async def mio_comando(update, context)` in `trash_bot.py`.
2. Registrala in `main()` con `application.add_handler(CommandHandler("miocomando", mio_comando))`.
3. Aggiungi `KeyboardButton("/miocomando")` a `COMMANDS_KEYBOARD`, così compare anche come bottone.
4. Aggiungilo all'elenco del messaggio di `/start`.

### Aggiungere un medico

1. Aggiungi il medico al dizionario `MEDICI` con un id breve e il nome da mostrare, per esempio `"rossi": "Mario Rossi"`. Compare in automatico tra i bottoni di scelta.
2. Prepara i suoi orari nello stesso formato di `MARZO_STUDI`: una lista di studi, ciascuno con `nome`, `indirizzo` e `orari`. `orari` è un dizionario che associa al giorno (`"Lunedì"`, ...) una lista di coppie `("HH:MM - HH:MM", "tipo")`. Prepara anche una lista di contatti.
3. In `send_medico_message`, aggiungi un ramo per il nuovo id che usi quegli orari, oppure una funzione che li legga da un sito come fa `fetch_medico_info`.

Le icone dipendono dal tipo della fascia oraria: se contiene "ricett" compare 💊, se contiene "segreteria" compare 📞, altrimenti 🕒.
