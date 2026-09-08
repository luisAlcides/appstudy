"""Prueba de widgets reales; se omite si no hay servidor gráfico disponible."""
import unittest
from unittest.mock import patch

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from appstudy import db, fuentes, multimedia
from appstudy.fuentes_window import FuentesWindow
from appstudy.main_window import MainWindow
from tests.apoyo import BaseTemporal
from tests.test_fuentes_extensiones import PNG


class FuentesUITest(BaseTemporal):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla: ejecutar con xvfb-run o en una sesión gráfica")
        Adw.init()

    def setUp(self):
        super().setUp()
        self.did = self.mazo()
        self.parent = Adw.Window()
        self.parent.con = self.con
        self.parent.refresh = lambda: None
        self.parent.importar_tarjetas = lambda: None
        self.parent.notify_user = lambda _t: None
        self.window = FuentesWindow(self.parent)
        self.addCleanup(self.parent.destroy)
        self.addCleanup(self.window.destroy)

    def test_construye_tres_secciones_y_nueve_extensiones(self):
        self.assertEqual(self.window.stack.get_pages().get_n_items(), 3)
        self.assertEqual(len(self.window.proveedores), 4)
        self.assertIsNotNone(self.window.lista_ext.get_first_child())

    def test_preview_y_configuracion_no_fallan(self):
        doc = fuentes.documento("markdown", "/a.md", "Tema", "Contenido")
        with patch.object(Adw.AlertDialog, "present") as present:
            self.window.preview(doc)
            self.window.configurar(self.window.proveedores[0])
            self.window.ver_indice()
            self.window.exportar()
        self.assertEqual(present.call_count, 4)

    def test_renderiza_imagen_real(self):
        cid = self.tarjeta(self.did, "Imagen")
        multimedia.guardar(self.con, cid, [{"side": "front", "name": "a.png", "data": PNG}])
        widget = multimedia.widget(self.con, cid, "front")
        self.assertIsInstance(widget.get_first_child(), Gtk.Picture)

    def test_importacion_de_ui_conserva_adjuntos_opciones_y_nivel(self):
        mazo = dict(self.con.execute("SELECT * FROM decks WHERE id=?", (self.did,)).fetchone())
        self.parent._importacion = {"tarjetas": [{"front": "Pregunta", "back": "B", "kind": "quiz",
            "choices": ["A", "B"], "answer": 1, "level": 2,
            "media": [{"side": "front", "name": "a.png", "data": PNG}]}],
            "pos": 0, "nuevas": 0, "mazo": mazo}
        MainWindow._importar_lote(self.parent)
        row = self.con.execute("SELECT * FROM cards WHERE front='Pregunta'").fetchone()
        self.assertEqual(row["level"], 2)
        self.assertEqual(row["answer"], 1)
        self.assertEqual(len(multimedia.leer(self.con, row["id"])), 1)


if __name__ == "__main__":
    unittest.main()
