"""El diálogo de la bitácora: guardar al instante, revisar y abrir un caso."""
from types import SimpleNamespace
from unittest import mock

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from appstudy import bitacora, db  # noqa: E402
from tests.apoyo import BaseTemporal  # noqa: E402

Adw.init()

PROPUESTAS = [{"front": "¿Por qué falla un sello de vástago?", "back": "Rayas y suciedad."},
              {"front": "¿Cómo se prueba una fuga interna?", "back": "Deriva bajo carga."}]


class BitacoraUITest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.mazo("maquinaria", "Maquinaria")
        self.mazo("automotriz", "Mecánica")
        self.avisos = []
        self.ventana = SimpleNamespace(con=self.con, notify_user=self.avisos.append,
                                       get_application=lambda: None, refresh=mock.Mock(),
                                       toast=Adw.ToastOverlay(), card_editor=mock.Mock())

    def dialogo(self, caso_id=None):
        from appstudy.bitacora_window import BitacoraDialog
        return BitacoraDialog(self.ventana, caso_id)

    def test_guardar_registra_la_nota_y_lanza_la_ia(self):
        d = self.dialogo()
        d.entrada.set_text("CAT 320D, fuga en cilindro del brazo")
        with mock.patch.object(bitacora, "lanzar", return_value=True) as lanzar:
            d.guardar()
        casos = bitacora.casos(self.con)
        self.assertEqual(len(casos), 1)
        self.assertEqual(casos[0]["equipo"], "CAT 320D")
        lanzar.assert_called_once()
        self.assertIn("CAT 320D", self.avisos[-1])

    def test_nota_vacia_no_guarda_nada(self):
        d = self.dialogo()
        d.guardar()
        self.assertEqual(bitacora.casos(self.con), [])

    def test_revisar_guarda_solo_las_marcadas_en_el_mazo_elegido(self):
        caso = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.proponer(self.con, caso["id"], PROPUESTAS)
        d = self.dialogo(caso["id"])
        marcas = d.revision["marcas"]
        self.assertEqual(len(marcas), 2)
        marcas[1][0].set_active(False)
        d.revision["combo"].set_selected(d.revision["claves"].index("automotriz"))
        ids = d.aceptar_revision()
        self.assertEqual(len(ids), 1)
        self.assertEqual(db.card_by_id(self.con, ids[0])["front"], PROPUESTAS[0]["front"])
        self.assertEqual(bitacora.caso(self.con, caso["id"])["deck_key"], "automotriz")

    def test_abrir_un_caso_listo_o_pendiente_no_falla(self):
        listo = bitacora.registrar(self.con, "CAT 320D, fuga")
        bitacora.proponer(self.con, listo["id"], PROPUESTAS)
        bitacora.aceptar(self.con, listo["id"], PROPUESTAS)
        pendiente = bitacora.registrar(self.con, "Komatsu PC200, humo")
        bitacora.fallar(self.con, pendiente["id"], "Ollama no responde")
        for caso_id in (listo["id"], pendiente["id"]):
            d = self.dialogo(caso_id)
            self.assertNotEqual(d.nav.get_visible_page().get_title(), "Bitácora del taller")
