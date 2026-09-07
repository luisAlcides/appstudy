"""Mapas de conexión: emparejar tarjetas que den juego y calificar la relación."""
import unittest
from unittest.mock import patch

from appstudy import conexiones
from tests.apoyo import BaseTemporal


class AfinidadTest(unittest.TestCase):
    @staticmethod
    def carta(cid, deck=1, level=1, tags="", front="alternador", back="carga la batería"):
        return {"id": cid, "deck_id": deck, "level": level, "tags": tags,
                "front": front, "back": back}

    def test_la_misma_tarjeta_no_hace_pareja(self):
        c = self.carta(1)
        self.assertEqual(conexiones.afinidad(c, c), 0)

    def test_de_mazos_distintos_no_hay_pareja(self):
        self.assertEqual(conexiones.afinidad(self.carta(1, deck=1),
                                             self.carta(2, deck=2)), 0)

    def test_las_etiquetas_compartidas_suben_la_afinidad(self):
        sin_tags = conexiones.afinidad(self.carta(1), self.carta(2, front="batería"))
        con_tags = conexiones.afinidad(self.carta(1, tags="electrico"),
                                       self.carta(2, tags="electrico", front="batería"))
        self.assertGreater(con_tags, sin_tags)

    def test_el_termino_tecnico_compartido_cuenta(self):
        sueltas = conexiones.afinidad(self.carta(1, front="tornillo", back="sujeta"),
                                      self.carta(2, front="martillo", back="golpea"))
        juntas = conexiones.afinidad(
            self.carta(1, front="alternador", back="mantiene la batería cargada"),
            self.carta(2, front="batería", back="alimenta el alternador al arrancar"))
        self.assertGreater(juntas, sueltas)


class ParesTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()
        self.ids = []
        for i in range(6):
            cid = self.tarjeta(self.deck, f"componente eléctrico {i}",
                               f"alimenta el circuito eléctrico {i}", tags="electrico")
            self.repasar(cid, 3)
            self.ids.append(cid)

    def test_sin_material_estudiado_no_hay_parejas(self):
        vacio = self.mazo(key="vacio", name="Vacío")
        self.tarjeta(vacio, "sin estrenar", key="vacio")
        self.assertEqual(conexiones.pares(self.con, deck_key="vacio"), [])

    def test_saca_las_parejas_pedidas_sin_repetir_tarjeta(self):
        parejas = conexiones.pares(self.con, cuantos=3)
        self.assertEqual(len(parejas), 3)
        vistas = [c["id"] for par in parejas for c in par]
        self.assertEqual(len(vistas), len(set(vistas)))

    def test_las_dos_de_cada_pareja_son_distintas(self):
        for uno, otro in conexiones.pares(self.con, cuantos=3):
            self.assertNotEqual(uno["id"], otro["id"])


class SesionTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()
        for i in range(4):
            cid = self.tarjeta(self.deck, f"pieza {i}", f"hace la función {i}",
                               tags="sistema")
            self.repasar(cid, 3)
        self.parejas = conexiones.pares(self.con, cuantos=2)

    def sesion(self):
        return conexiones.SesionConexiones(self.con, {"activa": True}, self.parejas)

    def test_recorre_las_preguntas_y_cierra_acta(self):
        s = self.sesion()
        with patch("appstudy.ia.pregunta_de_conexion", return_value="¿Qué relación hay?"), \
             patch("appstudy.ia.calificar_conexion",
                   side_effect=[{"nota": 90, "veredicto": "v", "falto": ""},
                                {"nota": 40, "veredicto": "v", "falto": "el porqué"}]):
            while not s.terminado():
                s.siguiente_pregunta()
                s.responder("porque uno alimenta al otro")
        acta = s.acta()
        self.assertEqual(acta["nota"], 65)
        self.assertEqual(len(acta["flojas"]), 1)

    def test_no_saberlo_es_cero_sin_preguntar_a_la_ia(self):
        s = self.sesion()
        with patch("appstudy.ia.calificar_conexion") as calificar:
            s.siguiente_pregunta()
            resultado = s.responder("ni idea")
            calificar.assert_not_called()
        self.assertEqual(resultado["nota"], 0)

    def test_sin_ia_pregunta_en_crudo(self):
        s = self.sesion()
        with patch("appstudy.ia.pregunta_de_conexion", side_effect=RuntimeError("sin modelo")):
            pregunta = s.siguiente_pregunta()
        self.assertIn("relación", pregunta.lower())
        self.assertIn("pieza", pregunta)


if __name__ == "__main__":
    unittest.main()
