import time
import unittest

from appstudy import recordatorios
from tests.apoyo import BaseTemporal


def fecha(dia_semana, hora):
    # 1/9/2025 fue lunes; mktime aplica correctamente la zona local del equipo.
    return time.mktime((2025, 9, 1 + dia_semana, hora, 0, 0, 0, 0, -1))


class RecordatoriosTest(BaseTemporal):
    def test_configuracion_por_defecto(self):
        self.assertEqual(recordatorios.config(self.con),
                         {"dias": "todos", "inicio": 8, "fin": 22})

    def test_respeta_dias_laborales(self):
        cfg = {"dias": "laborales", "inicio": 8, "fin": 22}
        self.assertTrue(recordatorios.permitido(cfg, fecha(0, 10)))
        self.assertFalse(recordatorios.permitido(cfg, fecha(5, 10)))

    def test_respeta_fin_de_semana(self):
        cfg = {"dias": "fin_de_semana", "inicio": 8, "fin": 22}
        self.assertFalse(recordatorios.permitido(cfg, fecha(2, 10)))
        self.assertTrue(recordatorios.permitido(cfg, fecha(6, 10)))

    def test_franja_normal_y_nocturna(self):
        dia = {"dias": "todos", "inicio": 8, "fin": 20}
        self.assertTrue(recordatorios.permitido(dia, fecha(0, 8)))
        self.assertFalse(recordatorios.permitido(dia, fecha(0, 22)))
        noche = {"dias": "todos", "inicio": 22, "fin": 6}
        self.assertTrue(recordatorios.permitido(noche, fecha(0, 23)))
        self.assertTrue(recordatorios.permitido(noche, fecha(0, 4)))
        self.assertFalse(recordatorios.permitido(noche, fecha(0, 12)))

    def test_guardar_es_atomico_y_acotado(self):
        recordatorios.guardar(self.con, dias="laborales", inicio=-5, fin=99)
        self.assertEqual(recordatorios.config(self.con),
                         {"dias": "laborales", "inicio": 0, "fin": 24})


if __name__ == "__main__":
    unittest.main()
