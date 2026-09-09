"""Integración con widgets GTK reales y una base temporal."""
import unittest

from tests.apoyo import BaseTemporal
from appstudy import potencial as plan
from appstudy.potencial_window import PotencialWindow
from gi.repository import Adw, Gdk, Gtk


class PotencialUITest(BaseTemporal):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla GTK")
        Adw.init()

    def setUp(self):
        super().setUp()
        self.parent = Adw.Window()
        self.parent.con = self.con
        self.window = PotencialWindow(self.parent)
        self.addCleanup(self.parent.destroy)
        self.addCleanup(self.window.destroy)
        self.addCleanup(self.window.cerrar)

    def test_pagina_y_cambio_de_preferencias(self):
        self.assertEqual(self.window.stack.get_pages().get_n_items(), 5)
        self.window.presupuesto.set_selected(0)
        self.window.fase.set_selected(3)
        self.assertEqual(plan.leer(self.con, "minutos"), 60)
        self.assertEqual(plan.leer(self.con, "fase"), 2)

    def test_cuaderno_cambia_tipo_sin_perder_texto(self):
        self.window.nueva_entrada("problema")
        self.window.buffers["Problema"].set_text("\nComparar dos camiones")
        self.window.buffers["Mi hipótesis"].set_text("Revisar producción por litro")
        self.window.nueva_entrada("lectura")
        self.assertEqual(plan.entradas(self.con)[0]["campos"]["Mi hipótesis"], "Revisar producción por litro")
        self.assertEqual(self.window.editor_tipo, "lectura")

    def test_revision_y_lectura_sin_contenido(self):
        self.window.notas["Data"].set_value(4)
        self.window.reflexion.set_text("Construí una consulta SQL")
        self.window.guardar_semana()
        self.assertIn("Construí una consulta", self.window.historial_semanal.get_label())
        self.window.abrir_lectura()
        self.assertIn("No hay lecturas", self.window.estado.get_label())

    def test_reloj_limpia_fuente_y_pausa(self):
        self.window.alternar_reloj()
        self.assertIsNotNone(self.window.timer)
        self.window.alternar_reloj()
        self.assertIsNone(self.window.reloj.inicio)
        self.window.cerrar()
        self.assertIsNone(self.window.timer)


if __name__ == "__main__":
    unittest.main()
