"""Lectura y anotaciones con GTK real y una base de datos temporal."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.apoyo import BaseTemporal
from appstudy import db
from appstudy.biblioteca import Adw, Gdk, GLib, Gtk, Lector


def recorrer(widget):
    yield widget
    hijo = widget.get_first_child()
    while hijo:
        yield from recorrer(hijo)
        hijo = hijo.get_next_sibling()


class TestLectorPDF(BaseTemporal):
    def setUp(self):
        super().setUp()
        Gtk.init()
        Adw.init()
        ajustes = Gtk.Settings.get_default()
        animaciones = ajustes.get_property("gtk-enable-animations")
        self.addCleanup(ajustes.set_property, "gtk-enable-animations", animaciones)
        ajustes.set_property("gtk-enable-animations", False)
        self.libro = {"ruta": str(self.tmp / "libro.pdf"),
                      "nombre": "Libro de prueba", "tema": "Pruebas"}
        # El renderizado se verifica aparte; aquí se ejercita la interfaz y
        # SQLite sin hilos que sobrevivan a la base temporal de una prueba.
        for objetivo, valor in (("libros.paginas", 8),
                                ("libros.tamano_pagina", (600, 800)),
                                ("util.hilo", None)):
            parche = patch("appstudy.biblioteca." + objetivo, return_value=valor)
            parche.start()
            self.addCleanup(parche.stop)
        self.ventana = Adw.Window(default_width=1100, default_height=800)
        self.bib = SimpleNamespace(con=self.con, pintar=Mock(),
                                   ventana=SimpleNamespace(notify_user=Mock()))
        self.lector = Lector(self.bib, self.libro)
        self.ventana.set_content(self.lector.pagina)
        self.ventana.present()
        self.addCleanup(self.limpiar_lector)
        self.eventos()

    def eventos(self):
        contexto = GLib.MainContext.default()
        while contexto.pending():
            contexto.iteration(False)

    def limpiar_lector(self):
        self.lector.cerrar()
        self.ventana.destroy()
        self.eventos()

    def entrada(self):
        return next(w for w in recorrer(self.lector.editor_nota)
                    if isinstance(w, Gtk.TextView))

    def test_pagina_persistida_sin_esperar_y_reabierta(self):
        self.lector.ir(6)
        otra = db.connect()
        try:
            self.assertEqual(db.book(otra, self.libro["ruta"])["pagina"], 6)
        finally:
            otra.close()
        self.lector.cerrar()
        self.ventana.set_content(None)
        self.lector = Lector(self.bib, self.libro)
        self.ventana.set_content(self.lector.pagina)
        self.assertEqual(self.lector.n, 6)

    def test_anotar_sin_subrayar_guarda_al_escribir_y_al_salir(self):
        self.lector.ir(3)
        self.lector.anotar_pagina()
        self.entrada().get_buffer().set_text("Mi idea\ncon dos líneas")
        notas = db.notas_de(self.con, self.libro["ruta"])
        self.assertEqual(notas[0]["nota"], "Mi idea\ncon dos líneas")
        self.assertEqual(notas[0]["pagina"], 3)
        self.lector.ir(4)
        self.assertIsNone(self.lector.editor_nota)
        self.assertEqual(db.notas_de(self.con, self.libro["ruta"])[0]["nota"],
                         "Mi idea\ncon dos líneas")

    def test_nota_nueva_vacia_se_descarta(self):
        self.lector.anotar_pagina()
        self.lector.cerrar_editor_nota()
        self.assertEqual(db.notas_de(self.con, self.libro["ruta"]), [])

    def test_cerrar_ficha_conserva_subrayado_sin_comentario(self):
        nid = db.nota_add(self.con, self.libro["ruta"], 1,
                          (0.1, 0.2, 0.8, 0.3), texto="Cita")
        self.lector.abrir_nota(nid)
        self.lector.cerrar_editor_nota()
        self.assertEqual(db.notas_de(self.con, self.libro["ruta"])[0]["texto"], "Cita")

    def test_teclas_del_editor_no_navegan(self):
        self.lector.anotar_pagina()
        self.entrada().grab_focus()
        for tecla in ("space", "Left", "Right", "Home", "End", "s", "n", "m"):
            self.assertFalse(self.lector.on_key(None, Gdk.keyval_from_name(tecla), 0, 0))
        self.assertEqual(self.lector.n, 1)
        self.assertFalse(self.lector.subrayando)

    def test_lista_se_actualiza_y_permite_editar(self):
        nid = db.nota_add(self.con, self.libro["ruta"], 5,
                          (0.1, 0.2, 0.8, 0.3), texto="Cita", nota="Antes")
        self.lector.btn_notas.popup()
        pop = self.lector.btn_notas.get_popover()
        editar = next(w for w in recorrer(pop) if isinstance(w, Gtk.Button)
                      and w.get_tooltip_text() == "Editar anotación de la página 5")
        editar.emit("clicked")
        self.assertEqual(self.lector.n, 5)
        self.entrada().get_buffer().set_text("Después")
        self.lector.cerrar_editor_nota()
        self.assertEqual(db.notas_de(self.con, self.libro["ruta"])[0]["nota"], "Después")
        self.assertEqual(db.notas_de(self.con, self.libro["ruta"])[0]["id"], nid)

    def test_cerrar_dos_veces_no_duplica_minutos(self):
        self.lector.desde -= 120
        self.lector.cerrar()
        minutos = db.book(self.con, self.libro["ruta"])["minutos"]
        self.lector.cerrar()
        self.assertEqual(db.book(self.con, self.libro["ruta"])["minutos"], minutos)
