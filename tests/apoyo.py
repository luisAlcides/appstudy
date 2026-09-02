"""Base común de las pruebas: una base de datos de usar y tirar.

`db.DATA_DIR` y `db.DB_PATH` se calculan al importar el módulo, así que aquí se
reapuntan a un directorio temporal *antes* de conectar. Ninguna prueba toca tu
progreso real en ~/.local/share/appstudy.
"""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

# Antes de que nada importe appstudy.db, para que DATA_DIR no salga del home
_TMP_RAIZ = tempfile.mkdtemp(prefix="appstudy-tests-")
os.environ["XDG_DATA_HOME"] = _TMP_RAIZ

from appstudy import db, respaldo, scheduler  # noqa: E402


class BaseTemporal(unittest.TestCase):
    """Cada prueba arranca con una base vacía y propia."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="appstudy-caso-"))
        self._data_dir, self._db_path = db.DATA_DIR, db.DB_PATH
        self._backups = respaldo.CARPETA
        db.DATA_DIR = self.tmp
        db.DB_PATH = self.tmp / "appstudy.db"
        respaldo.CARPETA = self.tmp / "backups"
        self.con = db.connect()
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        self.con.close()
        db.DATA_DIR, db.DB_PATH = self._data_dir, self._db_path
        respaldo.CARPETA = self._backups
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------- ayudantes

    def mazo(self, key="linux", name="Linux", niveles=("Básico", "Intermedio", "Avanzado")):
        return db.upsert_deck(self.con, key, name, "🐧", "#3584e4", 1, list(niveles))

    def tarjeta(self, deck_id, front, back="una respuesta cualquiera", *, key="linux",
                level=1, kind="card", choices=None, answer=-1, tags=""):
        cid, _ = db.add_card(self.con, deck_id, key, kind, front, back,
                             choices=choices, answer=answer, tags=tags, level=level)
        self.con.commit()
        return cid

    def repasar(self, card_id, rating, cuando=None):
        """Como apply_review, pero pudiendo fechar el repaso en el pasado."""
        st = scheduler.apply_review(self.con, card_id, rating)
        if cuando is not None:
            self.con.execute("UPDATE log SET ts=? WHERE card_id=? AND ts=(SELECT MAX(ts) "
                             "FROM log WHERE card_id=?)", (cuando, card_id, card_id))
            self.con.commit()
        return st

    def vencer(self, card_id, hace=60.0):
        """Deja la tarjeta vencida, para que next_card la considere pendiente."""
        self.con.execute("UPDATE state SET due=? WHERE card_id=?",
                         (time.time() - hace, card_id))
        self.con.commit()
