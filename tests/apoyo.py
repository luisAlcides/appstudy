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

# ---------------------------------------------- las críticas de GTK son fallos
#
# GTK no lanza excepciones: cuando se le pide un imposible —colgar un widget que
# ya tiene padre, dibujar sobre algo destruido— escupe un `Gtk-CRITICAL` por la
# salida de error y sigue como si nada. La prueba pasa en verde y el error sale
# a la luz en el escritorio del usuario. Aquí se recogen esos mensajes y se
# convierten en el fallo que deberían haber sido desde el principio.

_CRITICAS: list[str] = []


def _apuntar_critica(nivel, campos, _n_campos, _datos):
    """Anota lo grave y deja que el resto se imprima como siempre."""
    from gi.repository import GLib

    if nivel & (GLib.LogLevelFlags.LEVEL_CRITICAL | GLib.LogLevelFlags.LEVEL_ERROR):
        try:
            _CRITICAS.append(GLib.log_writer_format_fields(nivel, campos, False).strip())
        except Exception:                             # pragma: no cover - rarísimo
            _CRITICAS.append(f"mensaje de GTK de nivel {nivel} que no se pudo leer")
    return GLib.log_writer_default(nivel, campos, None)


def _vigilar_gtk():
    """Engancha el vigilante, si esta máquina tiene GTK. Si no, no pasa nada."""
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib
    except (ImportError, ValueError):                 # sin GTK no hay nada que vigilar
        return
    GLib.log_set_writer_func(_apuntar_critica, None)


def _no_hubo_criticas():
    """Se ejecuta al final de cada prueba, cuando los widgets ya están recogidos."""
    if not _CRITICAS:
        return
    mensajes = "\n".join(_CRITICAS)
    _CRITICAS.clear()
    raise AssertionError("GTK protestó durante esta prueba:\n" + mensajes)


_ejecutar_prueba = unittest.TestCase.run


def _run(self, result=None):
    # El enganche va en `TestCase` y no en `BaseTemporal` porque la mitad de las
    # pruebas que tocan GTK heredan directamente de `unittest.TestCase`. Se
    # apunta antes de arrancar para que, siendo las limpiezas LIFO, esta sea la
    # última en correr: para entonces la ventana del caso ya se ha desmontado.
    _CRITICAS.clear()
    self.addCleanup(_no_hubo_criticas)
    return _ejecutar_prueba(self, result)


unittest.TestCase.run = _run
_vigilar_gtk()


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
