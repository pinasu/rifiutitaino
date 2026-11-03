"""Log giornalieri in logs/bot_AAAA-MM-GG.log, conservati per 7 giorni."""
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger('trash_bot')


class DailyLogHandler(logging.FileHandler):
    def __init__(self, filename_template, max_days=7, **kwargs):
        self.filename_template = filename_template
        self.max_days = max_days
        super().__init__(self._get_current_filename(), **kwargs)
        self._cleanup_old_logs()

    def _get_current_filename(self):
        """Genera il nome del file basato sulla data corrente."""
        # replace e non format: il percorso di BOT_DATA_DIR potrebbe contenere parentesi graffe
        return self.filename_template.replace('{date}', datetime.now().strftime('%Y-%m-%d'))

    def _cleanup_old_logs(self):
        now = datetime.now()
        log_dir = os.path.dirname(self.filename_template) or '.'
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
            # Il bot resta acceso per mesi: la pulizia va fatta a ogni cambio di giorno, non solo all'avvio
            self._cleanup_old_logs()
        super().emit(record)


def setup_logging(log_dir):
    if logger.handlers:
        return logger
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    log_handler = DailyLogHandler(
        filename_template=os.path.join(log_dir, 'bot_{date}.log'),
        max_days=7,
        encoding='utf-8'
    )
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    return logger
