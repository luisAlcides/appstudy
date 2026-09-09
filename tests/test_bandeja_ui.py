"""La pantalla de Novedades: lista lo pendiente, acepta y descarta."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from appstudy import bandeja, db, fuentes, selector  # noqa: E402
from tests.apoyo import BaseTemporal  # noqa: E402

Adw.init()

TEXTO = "La ley de Ohm relaciona tensión, corriente y resistencia. " * 90


class BandejaUITest(BaseTemporal):
    def setUp(self):
        super().setUp()
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "#3584e4", 1,
                       ["Básico", "Intermedio", "Avanzado"])
        self.con.commit()
        self.plan = selector.plan(self.con)

    def guardar(self, cards=(), titulo="Ley de Ohm"):
        doc = fuentes.documento("wikipedia_es",
                                "https://es.wikipedia.org/wiki/" + titulo.replace(" ", "_"),
                                titulo, text=TEXTO, author="Colaboradores",
                                license="CC BY-SA 4.0")
        doc["cards"] = list(cards)
        return bandeja.guardar(self.con, doc, self.plan,
                               {"ok": True, "score": 0.9, "nivel": 1,
                                "motivo": "porque fallas ohm"})

    def pagina(self):
        from appstudy.bandeja_ui import PaginaBandeja
        p = PaginaBandeja(self.con, notificar=lambda _t: None)
        self.addCleanup(p.unparent)
        return p

    def test_lista_lo_pendiente_con_su_motivo(self):
        self.guardar()
        p = self.pagina()
        self.assertEqual(len(p.filas), 1)
        self.assertIn("porque fallas ohm", p.filas[0].motivo)
        self.assertIn("CC BY-SA 4.0", p.filas[0].licencia)

    def test_aceptar_crea_el_capitulo_y_vacia_la_bandeja(self):
        self.guardar([{"front": "¿Qué dice la ley de Ohm?", "back": "V = I · R"}])
        p = self.pagina()
        p.filas[0].aceptar()
        self.assertEqual(bandeja.cuantas(self.con), 0)
        self.assertEqual(len(p.filas), 0)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) c FROM chapters").fetchone()["c"], 1)

    def test_una_tarjeta_desmarcada_no_se_crea(self):
        self.guardar([{"front": "Uno", "back": "La ley de Ohm relaciona tensión"},
                      {"front": "Dos", "back": "La corriente y la resistencia"}])
        p = self.pagina()
        p.filas[0].casillas[1].set_active(False)
        p.filas[0].aceptar()
        frentes = [r["front"] for r in self.con.execute("SELECT front FROM cards")]
        self.assertEqual(frentes, ["Uno"])

    def test_descartar_lo_quita_de_la_lista(self):
        self.guardar()
        p = self.pagina()
        p.filas[0].descartar()
        self.assertEqual(bandeja.cuantas(self.con), 0)
        self.assertEqual(len(p.filas), 0)

    def test_la_bandeja_vacia_lo_dice_en_vez_de_quedarse_en_blanco(self):
        p = self.pagina()
        self.assertEqual(len(p.filas), 0)
        self.assertTrue(p.vacio.get_visible())

    def test_lo_mejor_puntuado_va_primero(self):
        self.guardar(titulo="Peor")
        self.con.execute("UPDATE inbox SET score=0.2 WHERE title='Peor'")
        self.con.commit()
        self.guardar(titulo="Mejor")
        p = self.pagina()
        self.assertEqual([f.fila["title"] for f in p.filas], ["Mejor", "Peor"])


class InsigniaTest(BaseTemporal):
    def test_la_insignia_cuenta_lo_pendiente_desde_cualquier_seccion(self):
        from appstudy.main_window import MainWindow
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "#3584e4", 1,
                       ["Básico"])
        self.con.commit()
        ventana = MainWindow(None, self.con)
        self.addCleanup(ventana.destroy)
        plan = selector.plan(self.con)
        doc = fuentes.documento("wikipedia_es", "https://es.wikipedia.org/wiki/Ohm",
                                "Ley de Ohm", text=TEXTO)
        bandeja.guardar(self.con, doc, plan,
                        {"ok": True, "score": 0.9, "nivel": 1, "motivo": "porque sí"})
        ventana.stack.set_visible_child_name("estadisticas")
        ventana.refresh()
        pagina = ventana.stack.get_page(ventana.bandeja)
        self.assertEqual(pagina.get_badge_number(), 1)
        self.assertTrue(pagina.get_needs_attention())


class AjustesFuentesTest(BaseTemporal):
    def ventana(self):
        from appstudy.fuentes_window import FuentesWindow
        padre = Adw.Window()
        padre.con = self.con
        padre.refresh = lambda: None
        padre.importar_tarjetas = lambda: None
        padre.notify_user = lambda _t: None
        w = FuentesWindow(padre)
        self.addCleanup(padre.destroy)
        self.addCleanup(w.destroy)
        return w

    def test_el_interruptor_apaga_y_enciende_la_autoalimentacion(self):
        w = self.ventana()
        self.assertTrue(w.auto_switch.get_active(), "de fábrica viene encendida")
        w.auto_switch.set_active(False)
        self.assertEqual(db.get_meta(self.con, "cosecha_auto", "1"), "0")
        w.auto_switch.set_active(True)
        self.assertEqual(db.get_meta(self.con, "cosecha_auto", "1"), "1")

    def test_se_ve_el_ultimo_error_y_lo_descartado(self):
        db.set_meta(self.con, "cosecha_error", "sin conexión")
        db.set_meta(self.con, "cosecha_rechazos",
                    '["Ohm (wikipedia_es): demasiado corto: 12 palabras"]')
        w = self.ventana()
        self.assertIn("sin conexión", w.auto_estado.get_text())
        self.assertIn("demasiado corto", w.auto_rechazos.get_text())

    def test_sin_errores_se_dice_que_todo_va_bien(self):
        w = self.ventana()
        self.assertNotIn("Error", w.auto_estado.get_text())
