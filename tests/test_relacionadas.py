"""Pruebas para la sugerencia de tarjetas relacionadas."""
import unittest

from tests.apoyo import BaseTemporal
from appstudy import db


class TestRelacionadas(BaseTemporal):
    def test_related_cards_mismo_tema(self):
        deck_id = self.mazo("linux", "Linux")
        c1 = self.tarjeta(deck_id, "Comando ls", "Lista archivos y directorios", tags="bash,archivos", level=1)
        c2 = self.tarjeta(deck_id, "Comando dir", "Equivalente a ls para listar archivos", tags="bash,archivos", level=1)
        c3 = self.tarjeta(deck_id, "Comando tree", "Muestra directorios en forma de árbol", tags="archivos", level=1)
        c4 = self.tarjeta(deck_id, "Comando kill", "Envía señales a procesos", tags="procesos", level=2)

        card1 = self.con.execute("SELECT * FROM cards WHERE id=?", (c1,)).fetchone()
        relacionadas = db.related_cards_for_card(self.con, card1, limit=3)

        self.assertGreaterEqual(len(relacionadas), 1)
        rel_ids = [r["id"] for r in relacionadas]
        self.assertIn(c2, rel_ids)
        self.assertNotIn(c1, rel_ids)

    def test_related_cards_sin_coincidencias(self):
        deck_id = self.mazo("linux", "Linux")
        c1 = self.tarjeta(deck_id, "Unicornio", "Animal mitológico", tags="mitologia", level=1)
        card1 = self.con.execute("SELECT * FROM cards WHERE id=?", (c1,)).fetchone()
        relacionadas = db.related_cards_for_card(self.con, card1, limit=3)
        self.assertEqual(len(relacionadas), 0)


if __name__ == "__main__":
    unittest.main()
