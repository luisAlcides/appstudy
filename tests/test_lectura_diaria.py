"""La lectura del día: una sola, fija hasta terminarla o hasta que cambie el día.

Lo que se prueba aquí es la promesa que se le hace a quien estudia: si abres la
aplicación tres veces esta tarde, la lectura propuesta es la misma las tres. No
puede bailar cada vez que se recalculan las recomendaciones, porque entonces
deja de ser un plan y pasa a ser una sugerencia más.
"""
import time
import unittest

from appstudy import db, lectura_diaria
from tests.apoyo import BaseTemporal


def dia_a_segundos(dias_atras: float) -> float:
    return time.time() - dias_atras * 86400


class LecturaDelDiaTest(BaseTemporal):
    def capitulo(self, deck_id, key, titulo, **campos):
        cid, _ = db.upsert_chapter(self.con, deck_id, key, dict(title=titulo, **campos))
        self.con.commit()
        return cid

    def tres_capitulos(self):
        deck = self.mazo()
        return [self.capitulo(deck, "linux", f"Capítulo {i}", pos=i, minutes=8)
                for i in range(1, 4)]

    # --------------------------------------------------------------- elegir

    def test_sin_capitulos_no_hay_lectura(self):
        self.mazo()
        self.assertIsNone(lectura_diaria.del_dia(self.con))

    def test_elige_uno_y_lo_mantiene_el_resto_del_dia(self):
        self.tres_capitulos()
        primera = lectura_diaria.del_dia(self.con)
        self.assertIsNotNone(primera)
        for _ in range(3):
            self.assertEqual(lectura_diaria.del_dia(self.con)["id"], primera["id"])

    def test_al_cambiar_el_dia_propone_otra(self):
        ids = self.tres_capitulos()
        ayer = dia_a_segundos(1)
        primera = lectura_diaria.del_dia(self.con, ahora=ayer)
        db.mark_read(self.con, primera["id"])
        segunda = lectura_diaria.del_dia(self.con)
        self.assertNotEqual(segunda["id"], primera["id"])
        self.assertIn(segunda["id"], ids)

    def test_la_de_hoy_sigue_siendo_la_misma_aunque_ya_esté_leída(self):
        # Terminarla no la reemplaza por otra: el día ya está cumplido y el
        # panel debe poder decir «hecha», no proponer otra tarea.
        self.tres_capitulos()
        elegida = lectura_diaria.del_dia(self.con)
        db.mark_read(self.con, elegida["id"])
        self.assertEqual(lectura_diaria.del_dia(self.con)["id"], elegida["id"])
        self.assertTrue(lectura_diaria.hecha(self.con))

    def test_sin_terminarla_no_cuenta_como_hecha(self):
        self.tres_capitulos()
        lectura_diaria.del_dia(self.con)
        self.assertFalse(lectura_diaria.hecha(self.con))

    def test_si_el_capitulo_del_dia_desaparece_propone_otro(self):
        ids = self.tres_capitulos()
        elegida = lectura_diaria.del_dia(self.con)
        self.con.execute("DELETE FROM chapters WHERE id=?", (elegida["id"],))
        self.con.commit()
        otra = lectura_diaria.del_dia(self.con)
        self.assertIsNotNone(otra)
        self.assertNotEqual(otra["id"], elegida["id"])

    def test_no_propone_capitulos_de_un_mazo_apagado(self):
        self.tres_capitulos()
        otro = db.upsert_deck(self.con, "ingles", "Inglés", "🇬🇧", "#f00", 2, ["A2"])
        ajeno = self.capitulo(otro, "ingles", "De otro mazo")
        self.con.execute("UPDATE decks SET enabled=0 WHERE key='linux'")
        self.con.commit()
        self.assertEqual(lectura_diaria.del_dia(self.con)["id"], ajeno)

    # ---------------------------------------------------------------- racha

    def test_sin_lecturas_la_racha_es_cero(self):
        self.tres_capitulos()
        self.assertEqual(lectura_diaria.racha(self.con), 0)

    def test_leer_hoy_arranca_la_racha(self):
        ids = self.tres_capitulos()
        db.mark_read(self.con, ids[0])
        self.assertEqual(lectura_diaria.racha(self.con), 1)

    def test_dias_seguidos_se_encadenan(self):
        ids = self.tres_capitulos()
        for cid, atras in zip(ids, (0, 1, 2)):
            db.mark_read(self.con, cid)
            self.con.execute("UPDATE reading SET ts=? WHERE chapter_id=?",
                             (dia_a_segundos(atras), cid))
        self.con.commit()
        self.assertEqual(lectura_diaria.racha(self.con), 3)

    def test_un_dia_en_blanco_corta_la_racha(self):
        ids = self.tres_capitulos()
        for cid, atras in zip(ids, (0, 1, 3)):
            db.mark_read(self.con, cid)
            self.con.execute("UPDATE reading SET ts=? WHERE chapter_id=?",
                             (dia_a_segundos(atras), cid))
        self.con.commit()
        self.assertEqual(lectura_diaria.racha(self.con), 2)

    def test_haber_leido_ayer_y_no_hoy_conserva_la_racha(self):
        # Aún estás a tiempo: la racha se rompe al terminar el día, no al
        # empezarlo. Es la misma regla que la racha de repasos.
        ids = self.tres_capitulos()
        db.mark_read(self.con, ids[0])
        self.con.execute("UPDATE reading SET ts=? WHERE chapter_id=?",
                         (dia_a_segundos(1), ids[0]))
        self.con.commit()
        self.assertEqual(lectura_diaria.racha(self.con), 1)

    def test_lo_marcado_como_no_leido_no_suma(self):
        ids = self.tres_capitulos()
        db.mark_read(self.con, ids[0])
        db.mark_read(self.con, ids[0], leido=False)
        self.assertEqual(lectura_diaria.racha(self.con), 0)


if __name__ == "__main__":
    unittest.main()
