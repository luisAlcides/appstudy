import unittest

from appstudy.lectura_guiada import SesionGuiada, secciones


class LecturaGuiadaTest(unittest.TestCase):
    def setUp(self):
        self.ahora = 0
        self.partes = secciones([{"h": "Inicio"}, {"p": "Una idea"},
                                 {"h": "Ejemplo"}, {"p": "Otro ejemplo"}], "Tema")
        self.sesion = SesionGuiada(self.partes, 10, lambda: self.ahora)

    def test_conserva_todo_el_contenido_y_encabezados(self):
        body = [{"p": "Introducción"}, {"h": "Uno"}, {"code": {"code": "x = 1"}},
                {"h": "Dos"}, {"list": ["a", "b"]}]
        partes = secciones(body, "Tema")
        self.assertEqual([p["titulo"] for p in partes], ["Tema", "Uno", "Dos"])
        self.assertEqual([b for p in partes for b in p["body"]], body)

    def test_vacio_y_duraciones_invalidas(self):
        self.assertEqual(secciones([], "Tema"), [])
        for partes, minutos in [([], 10), (self.partes, 0), (self.partes, 181),
                                (self.partes, float("nan"))]:
            with self.assertRaises(ValueError):
                SesionGuiada(partes, minutos)

    def test_pausa_no_consume_tiempo_ni_reinicia(self):
        self.sesion.iniciar()
        self.ahora = 120
        self.sesion.iniciar()
        self.assertEqual(self.sesion.transcurrido, 120)
        self.sesion.pausar()
        self.ahora = 400
        self.assertEqual(self.sesion.transcurrido, 120)
        self.sesion.iniciar()
        self.ahora = 430
        self.assertEqual(self.sesion.transcurrido, 150)

    def test_reserva_quince_por_ciento_para_recordar(self):
        self.sesion.iniciar()
        self.ahora = 509
        self.assertLess(self.sesion.indice, len(self.partes))
        self.ahora = 510
        self.assertEqual(self.sesion.indice, len(self.partes))
        self.assertFalse(self.sesion.terminado)

    def test_reloj_retrasado_completa_sin_tiempo_negativo(self):
        self.sesion.iniciar()
        self.ahora = 900
        self.assertTrue(self.sesion.terminado)
        self.assertEqual(self.sesion.transcurrido, 600)
        self.sesion.pausar()
        self.sesion.iniciar()
        self.assertIsNone(self.sesion.inicio)

    def test_seccion_mas_larga_recibe_mas_tiempo(self):
        partes = secciones([{"h": "A"}, {"p": "palabra " * 100},
                             {"h": "B"}, {"p": "corta"}], "Tema")
        sesion = SesionGuiada(partes, 10)
        self.assertGreater(sesion.limites[0], 450)


if __name__ == "__main__":
    unittest.main()
