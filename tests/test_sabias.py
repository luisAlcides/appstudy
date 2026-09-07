"""Los datos de «¿Sabías que…?» y su paso a tarjeta.

Un dato que solo se lee se olvida; lo que se prueba aquí es sobre todo que se
pueda guardar bien, que es lo que lo convierte en algo que sabrás dentro de
tres meses.
"""
import unittest

from appstudy import db, sabias
from tests.apoyo import BaseTemporal


class DatosTest(unittest.TestCase):
    def test_todos_los_datos_estan_completos(self):
        for dato, categoria, porque in sabias.DATOS:
            self.assertTrue(dato.strip(), dato)
            self.assertTrue(categoria.strip(), dato)
            self.assertTrue(porque.strip(), dato)
            # Un dato sin desarrollo se queda en anécdota de barra de bar
            self.assertGreater(len(dato), 40, dato)

    def test_no_hay_datos_repetidos(self):
        textos = [d[0] for d in sabias.DATOS]
        self.assertEqual(len(textos), len(set(textos)))

    def test_hay_variedad_de_categorias(self):
        self.assertGreaterEqual(len(sabias.categorias()), 8)
        self.assertIn("Lo que crees y no es", sabias.categorias())

    def test_ninguna_categoria_se_queda_coja(self):
        # Con dos datos, pedir esa categoría es oír siempre lo mismo
        from collections import Counter
        cuenta = Counter(d[1] for d in sabias.DATOS)
        flacas = [c for c, n in cuenta.items() if n < 3]
        self.assertEqual(flacas, [], f"categorías con menos de 3 datos: {flacas}")

    def test_evita_repetir_lo_recien_visto(self):
        vistos = [d[0] for d in sabias.DATOS[:-1]]
        dato, _, _ = sabias.aleatorio(evitar=vistos)
        self.assertEqual(dato, sabias.DATOS[-1][0])

    def test_agotados_todos_vuelve_a_empezar(self):
        # Tras una vuelta entera, repetir es repasar: no debe quedarse sin dato
        vistos = [d[0] for d in sabias.DATOS]
        self.assertIsNotNone(sabias.aleatorio(evitar=vistos)[0])

    def test_se_puede_pedir_una_categoria(self):
        for _ in range(8):
            dato, categoria, _ = sabias.aleatorio(categoria="Historia")
            self.assertEqual(categoria, "Historia")

    def test_una_categoria_inventada_no_deja_sin_dato(self):
        self.assertIsNotNone(sabias.aleatorio(categoria="Alquimia")[0])

    def test_el_titular_corta_por_palabras(self):
        largo = "La Universidad de Oxford es más antigua que el Imperio azteca y esto sigue"
        corto = sabias.titular(largo, limite=30)
        self.assertLessEqual(len(corto), 31)
        self.assertTrue(corto.endswith("…"))
        self.assertNotIn("  ", corto)
        # Lo que ya es corto se deja tal cual
        self.assertEqual(sabias.titular("Un dato breve"), "Un dato breve")


class GuardarTest(BaseTemporal):
    def test_guardar_crea_el_mazo_y_la_tarjeta(self):
        dato, categoria, porque = sabias.DATOS[0]
        cid = sabias.guardar_como_tarjeta(self.con, dato, categoria, porque)
        self.assertIsNotNone(cid)
        self.assertEqual(sabias.cuantas_guardadas(self.con), 1)
        fila = self.con.execute("SELECT front, back, tags FROM cards WHERE id=?",
                                (cid,)).fetchone()
        self.assertIn(categoria, fila["front"])
        self.assertIn(dato, fila["back"])
        self.assertIn("cultura", fila["tags"])

    def test_el_mismo_dato_no_entra_dos_veces(self):
        dato, categoria, porque = sabias.DATOS[1]
        self.assertIsNotNone(sabias.guardar_como_tarjeta(self.con, dato, categoria, porque))
        self.assertIsNone(sabias.guardar_como_tarjeta(self.con, dato, categoria, porque))
        self.assertEqual(sabias.cuantas_guardadas(self.con), 1)

    def test_dos_datos_distintos_no_se_pisan(self):
        # El identificador de una tarjeta sale de su frente: con frentes
        # genéricos, el segundo dato machacaría al primero
        for dato, categoria, porque in sabias.DATOS[:4]:
            sabias.guardar_como_tarjeta(self.con, dato, categoria, porque)
        self.assertEqual(sabias.cuantas_guardadas(self.con), 4)

    def test_se_puede_guardar_con_la_pregunta_de_la_ia(self):
        dato, categoria, porque = sabias.DATOS[2]
        cid = sabias.guardar_como_tarjeta(self.con, dato, categoria, porque,
                                          pregunta="¿Qué se inventó antes, el fax o el teléfono?")
        fila = self.con.execute("SELECT front FROM cards WHERE id=?", (cid,)).fetchone()
        self.assertEqual(fila["front"], "¿Qué se inventó antes, el fax o el teléfono?")

    def test_las_guardadas_entran_en_el_repaso(self):
        from appstudy import scheduler
        dato, categoria, porque = sabias.DATOS[3]
        sabias.guardar_como_tarjeta(self.con, dato, categoria, porque)
        carta = scheduler.next_card(self.con, deck_key=sabias.DECK_CULTURA)
        self.assertIsNotNone(carta)
        self.assertIn(dato, carta["back"])


if __name__ == "__main__":
    unittest.main()
