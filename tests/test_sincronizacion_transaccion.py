"""Los bordes de `fusionar`: la transacción y el identificador de la tarjeta.

Ninguno de los dos se veía desde fuera. La transacción funcionaba por el orden
en que estaban escritas las cosas, y el identificador se volvía a buscar tres
veces por tarjeta sin comprobar que estuviera.
"""
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from appstudy import db, multimedia, sincronizacion
from tests.apoyo import BaseTemporal

EQUIPO_A = "a" * 32
EQUIPO_B = "b" * 32

PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)


class FusionarTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.compartida = Path(tempfile.mkdtemp(dir=self.tmp))
        self.otra = sqlite3.connect(self.tmp / "otro.db")
        self.otra.row_factory = sqlite3.Row
        self.otra.execute("PRAGMA foreign_keys = ON")
        self.otra.executescript(db.SCHEMA)
        db.migrate(self.otra)
        self.otra.executescript(db.INDEXES)
        self.addCleanup(self.otra.close)

    def tarjeta(self, pregunta="Pregunta", respuesta="Respuesta"):
        did = db.upsert_deck(self.con, "mio", "Mi mazo", "🧠", "#123456", 1)
        cid, _ = db.add_card(self.con, did, "mio", "card", pregunta, respuesta)
        self.con.commit()
        return cid

    def test_aplicar_card_devuelve_el_id_de_la_fila_que_acaba_de_escribir(self):
        cid = sincronizacion._aplicar_card(
            self.con, {"uid": "u-1", "deck_key": "mio", "front": "P", "back": "R"}, None)
        fila = self.con.execute("SELECT id FROM cards WHERE uid='u-1'").fetchone()
        self.assertEqual(cid, fila["id"])
        # Y deja el estado creado, que es lo que hacía antes de devolver nada
        self.assertIsNotNone(
            self.con.execute("SELECT 1 FROM state WHERE card_id=?", (cid,)).fetchone())

    def test_los_adjuntos_llegan_al_otro_equipo(self):
        # Es la rama que usaba el id rebuscado: si se pierde, la imagen no viaja.
        cid = self.tarjeta()
        multimedia.guardar(self.con, cid,
                           [{"side": "front", "name": "foto.png",
                             "mime": "image/png", "data": PNG}])
        self.con.commit()
        sincronizacion.sincronizar(self.con, self.compartida, EQUIPO_A)
        sincronizacion.sincronizar(self.otra, self.compartida, EQUIPO_B)
        cid_b = self.otra.execute("SELECT id FROM cards").fetchone()["id"]
        adjuntos = multimedia.leer(self.otra, cid_b)
        self.assertEqual([(a["name"], a["data"]) for a in adjuntos],
                         [("foto.png", PNG)])

    def test_una_escritura_antes_del_begin_no_rompe_la_fusion(self):
        """El `BEGIN IMMEDIATE` de `fusionar` es lo único que sostiene el todo-o-nada.

        Hoy llega con la transacción cerrada porque justo antes hay un `commit`
        y lo de en medio solo lee. Pero `sqlite3` abre transacción implícita en
        cuanto alguien escribe, y un `BEGIN` dentro de otra transacción es
        `cannot start a transaction within a transaction`: la sincronización
        entera se caería. Aquí se mete esa escritura a propósito.
        """
        self.tarjeta()
        sincronizacion.sincronizar(self.con, self.compartida, EQUIPO_A)
        remotos = [sincronizacion._leer(r)
                   for r in self.compartida.glob("appstudy-*.sync.json")]

        real = sincronizacion._mazos

        def _mazos_que_escribe(datos):
            # Como si alguien añadiese aquí una estadística, una marca de tiempo…
            self.otra.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('visto','1')")
            return real(datos)

        with patch.object(sincronizacion, "_mazos", _mazos_que_escribe):
            self.assertTrue(remotos, "el montaje de la prueba no vale")
            resultado = sincronizacion.fusionar(self.otra, remotos, EQUIPO_B)

        self.assertEqual(resultado["tarjetas"], 1)
        self.assertEqual(
            self.otra.execute("SELECT front FROM cards").fetchone()["front"], "Pregunta")
