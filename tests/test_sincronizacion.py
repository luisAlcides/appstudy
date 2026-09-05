import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from appstudy import db, scheduler, sincronizacion
from tests.apoyo import BaseTemporal


EQUIPO_A = "a" * 32
EQUIPO_B = "b" * 32


class SincronizacionTest(BaseTemporal):
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

    def tarjeta_a(self, pregunta="Pregunta", respuesta="Respuesta"):
        did = db.upsert_deck(self.con, "mio", "Mi mazo", "🧠", "#123456", 1)
        cid, _ = db.add_card(self.con, did, "mio", "card", pregunta, respuesta)
        self.con.commit()
        return cid

    def sync_a(self):
        return sincronizacion.sincronizar(self.con, self.compartida, EQUIPO_A)

    def sync_b(self):
        return sincronizacion.sincronizar(self.otra, self.compartida, EQUIPO_B)

    def test_transfiere_tarjeta_y_mazo_sin_ids_locales(self):
        self.tarjeta_a()
        self.sync_a()
        resultado = self.sync_b()
        fila = self.otra.execute(
            """SELECT c.front,c.back,d.key FROM cards c
               JOIN decks d ON d.id=c.deck_id""").fetchone()
        self.assertEqual(tuple(fila), ("Pregunta", "Respuesta", "mio"))
        self.assertEqual(resultado["tarjetas"], 1)

    def test_edicion_mas_reciente_gana_y_el_borrado_viaja(self):
        cid = self.tarjeta_a()
        db.touch_sync(self.con, "card", db.card_by_id(self.con, cid)["uid"], modified=10)
        self.con.commit()
        self.sync_a(); self.sync_b()

        uid = db.card_by_id(self.con, cid)["uid"]
        self.con.execute("UPDATE cards SET back='Nueva' WHERE id=?", (cid,))
        db.touch_sync(self.con, "card", uid, modified=20)
        self.con.commit()
        self.sync_a(); self.sync_b()
        self.assertEqual(self.otra.execute(
            "SELECT back FROM cards WHERE uid=?", (uid,)).fetchone()[0], "Nueva")

        # La lápida impide que una copia vieja resucite la tarjeta.
        db.delete_card(self.con, cid)
        self.sync_a(); self.sync_b()
        self.assertIsNone(self.otra.execute(
            "SELECT id FROM cards WHERE uid=?", (uid,)).fetchone())

    def test_repasos_se_unen_una_sola_vez_y_llevan_el_estado(self):
        cid = self.tarjeta_a()
        self.sync_a(); self.sync_b()
        scheduler.apply_review(self.con, cid, scheduler.GOOD, 1200)
        estado_a = self.con.execute(
            "SELECT last,stability FROM state WHERE card_id=?", (cid,)).fetchone()
        self.sync_a()
        primero = self.sync_b()
        segundo = self.sync_b()
        self.assertEqual(primero["repasos"], 1)
        self.assertEqual(segundo["repasos"], 0)
        self.assertEqual(self.otra.execute("SELECT COUNT(*) FROM log").fetchone()[0], 1)
        estado_b = self.otra.execute(
            "SELECT last,stability FROM state WHERE reps>0").fetchone()
        self.assertEqual(tuple(estado_b), tuple(estado_a))

    def test_sincroniza_avance_de_lectura(self):
        did = db.upsert_deck(self.con, "mio", "Mi mazo", "🧠", "#123456", 1)
        cap, _ = db.upsert_chapter(self.con, did, "mio", {
            "title": "Apuntes", "body": [{"p": "Texto"}], "propio": True})
        self.con.execute("UPDATE reading SET avance=.6,ts=? WHERE chapter_id=?",
                         (time.time(), cap))
        self.con.commit()
        self.sync_a(); resultado = self.sync_b()
        fila = self.otra.execute("SELECT avance FROM reading WHERE avance>0").fetchone()
        self.assertAlmostEqual(fila[0], .6)
        self.assertEqual(resultado["capitulos"], 1)
        self.assertEqual(resultado["lecturas"], 1)

    def test_archivo_corrupto_se_ignora_sin_frenar_los_validos(self):
        self.tarjeta_a(); self.sync_a()
        (self.compartida / f"appstudy-{'c' * 32}.sync.json").write_text("{roto")
        resultado = self.sync_b()
        self.assertEqual(resultado["ignorados"], 1)
        self.assertEqual(self.otra.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 1)

    def test_el_archivo_del_propio_equipo_tambien_sirve_para_recuperar(self):
        self.tarjeta_a(); self.sync_a()
        recuperada = sqlite3.connect(self.tmp / "recuperada.db")
        recuperada.row_factory = sqlite3.Row
        recuperada.executescript(db.SCHEMA)
        db.migrate(recuperada)
        self.addCleanup(recuperada.close)
        sincronizacion.sincronizar(recuperada, self.compartida, EQUIPO_A)
        self.assertEqual(recuperada.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 1)

    def test_la_fuente_de_una_tarjeta_viaja_con_ella(self):
        cid = self.tarjeta_a()
        db.set_card_source(self.con, cid, {
            "kind": "book", "ruta": "/libros/manual.pdf", "page_start": 12,
            "page_end": 14, "title": "Manual"})
        self.con.commit()
        self.sync_a(); self.sync_b()
        card_b = self.otra.execute("SELECT id FROM cards").fetchone()[0]
        fuente = db.source_for_card(self.otra, card_b)
        self.assertEqual((fuente["ruta"], fuente["page_start"], fuente["page_end"]),
                         ("/libros/manual.pdf", 12, 14))


if __name__ == "__main__":
    unittest.main()
