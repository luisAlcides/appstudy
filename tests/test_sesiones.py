import unittest

from appstudy import sesiones


class SesionesTest(unittest.TestCase):
    def tarjeta(self, id_=1, tags="", reps=2, deck="Linux"):
        return {"id": id_, "tags": tags, "reps": reps, "deck_name": deck}

    def test_termina_por_tarjetas_sin_interrumpir_una_sesion_vacia(self):
        s = sesiones.Sesion(sesiones.Plan(5, 2, "Prueba"), ahora=100)
        self.assertFalse(s.terminada(1000))
        s.registrar(self.tarjeta(), 2, 1200, ahora=101)
        self.assertFalse(s.terminada(102))
        s.registrar(self.tarjeta(2), 0, 1800, ahora=103)
        self.assertTrue(s.terminada(103))

    def test_termina_por_tiempo_despues_de_responder(self):
        s = sesiones.Sesion(sesiones.Plan(1, 99, "Prueba"), ahora=100)
        s.registrar(self.tarjeta(), 2, 900, ahora=101)
        self.assertFalse(s.terminada(159))
        self.assertTrue(s.terminada(160))

    def test_resumen_detecta_tema_debil_y_mediana(self):
        s = sesiones.Sesion(sesiones.Plan(5, 8, "Prueba"), ahora=100)
        s.registrar(self.tarjeta(1, "redes,linux", reps=0), 0, 1000, ahora=101)
        s.registrar(self.tarjeta(2, "redes"), 1, 3000, ahora=102)
        s.registrar(self.tarjeta(3, "shell"), 3, 2000, ahora=103)
        r = s.resumen()
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["recordadas"], 2)
        self.assertEqual(r["nuevas"], 1)
        self.assertEqual(r["mediana_ms"], 2000)
        self.assertEqual(r["tema_debil"]["tema"], "redes")

    def test_deshacer_y_ampliar(self):
        s = sesiones.Sesion(sesiones.Plan(1, 1, "Prueba"), ahora=100)
        s.registrar(self.tarjeta(7), 2, 1000, ahora=101)
        self.assertTrue(s.terminada(102))
        self.assertEqual(s.deshacer_ultima(7)["card_id"], 7)
        s.ampliar(5, 8, ahora=200)
        self.assertEqual(s.meta, 9)
        self.assertEqual(s.restantes(200), 300)


if __name__ == "__main__":
    unittest.main()
