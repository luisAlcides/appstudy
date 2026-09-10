"""Los cuatro formatos con que la mascota cuenta una tarjeta.

Se sortean al pulsarla —ya no hay selector—, así que cualquiera de los cuatro
puede salir en cualquier momento y los cuatro tienen que montarse sin fallar y
sin dejarse la respuesta por el camino.
"""
from types import MethodType
import unittest

from appstudy import pet
from gi.repository import Gtk, Gdk


class GloboSinVentana:
    """Presta los métodos de PetWindow sin abrir ninguna ventana."""

    def __init__(self):
        self.card_scale = 1.15

    def __getattr__(self, nombre):
        if nombre == "nombre":
            return "Bit"
        valor = getattr(pet.PetWindow, nombre)
        return valor.fget(self) if isinstance(valor, property) else \
            MethodType(valor, self)


def textos(widget) -> str:
    """Todo el texto que se ve en un trozo de globo, junto."""
    trozos = []
    if isinstance(widget, Gtk.Label):
        trozos.append(widget.get_label())
    hijo = widget.get_first_child()
    while hijo is not None:
        trozos.append(textos(hijo))
        hijo = hijo.get_next_sibling()
    return "\n".join(t for t in trozos if t)


class SorteoDeFormatoTest(unittest.TestCase):
    def test_nunca_repite_el_formato_anterior(self):
        for anterior in pet.FORMATOS_ENSENANZA:
            for _ in range(40):
                self.assertNotEqual(pet.formato_ensenanza(anterior), anterior)

    def test_con_el_tiempo_salen_los_cuatro(self):
        vistos, anterior = set(), None
        for _ in range(200):
            anterior = pet.formato_ensenanza(anterior)
            vistos.add(anterior)
        self.assertEqual(vistos, set(pet.FORMATOS_ENSENANZA))

    def test_sin_anterior_tambien_elige(self):
        self.assertIn(pet.formato_ensenanza(), pet.FORMATOS_ENSENANZA)


class TrozosDeRespuestaTest(unittest.TestCase):
    def test_parte_por_frases(self):
        self.assertEqual(pet.trozos_de_respuesta("Uno. Dos. Tres."),
                         ["Uno.", "Dos.", "Tres."])

    def test_si_no_hay_frases_parte_por_comas(self):
        self.assertEqual(pet.trozos_de_respuesta("uno, dos, tres"),
                         ["uno", "dos", "tres"])

    def test_lo_que_pasa_del_maximo_se_pega_al_ultimo_paso(self):
        trozos = pet.trozos_de_respuesta("A. B. C. D. E. F.", maximo=3)
        self.assertEqual(len(trozos), 3)
        self.assertEqual(trozos[-1], "C. D. E. F.")

    def test_sin_texto_no_hay_pasos(self):
        self.assertEqual(pet.trozos_de_respuesta("   "), [])


class FormatosSeMontanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla GTK")

    def carta(self, **cambios):
        c = {"front": "¿Qué hace chmod?", "back": "Cambia los permisos. Se usa con octal.",
             "hint": "chmod = change mode", "deck_name": "Linux"}
        c.update(cambios)
        return c

    def montar(self, formato, c):
        globo = GloboSinVentana()
        return textos(getattr(globo, f"_render_formato_{formato}")(c))

    def test_los_cuatro_cuentan_pregunta_y_respuesta(self):
        for formato in pet.FORMATOS_ENSENANZA:
            with self.subTest(formato=formato):
                visto = self.montar(formato, self.carta())
                self.assertIn("chmod", visto)
                self.assertIn("permisos", visto)

    def test_sin_respuesta_ninguno_se_rompe(self):
        for formato in pet.FORMATOS_ENSENANZA:
            with self.subTest(formato=formato):
                visto = self.montar(formato, self.carta(back="", hint="solo una pista"))
                self.assertIn("pista", visto)

    def test_el_esquema_numera_los_pasos_sin_perder_frases(self):
        visto = self.montar("esquema", self.carta(
            back="Primero esto. Después lo otro. Y al final lo de más allá."))
        for numero in ("1", "2", "3"):
            self.assertIn(numero, visto)
        self.assertIn("más allá", visto)

    def test_las_capas_empiezan_con_una_sola_abierta(self):
        globo = GloboSinVentana()
        caja = globo._render_formato_capas(self.carta())
        reveladores = []
        hijo = caja.get_first_child()
        while hijo is not None:
            nieto = hijo.get_first_child()
            while nieto is not None:
                if isinstance(nieto, Gtk.Revealer):
                    reveladores.append(nieto)
                nieto = nieto.get_next_sibling()
            hijo = hijo.get_next_sibling()
        self.assertEqual(len(reveladores), 3)
        self.assertEqual([r.get_reveal_child() for r in reveladores], [True, False, False])

    def test_una_capa_cerrada_se_abre_al_pulsarla(self):
        globo = GloboSinVentana()
        caja = globo._capa(2, 3, "El detalle", "as-card-back-box", "lo de dentro", abierta=False)
        boton, revelador = caja.get_first_child(), caja.get_last_child()
        self.assertFalse(revelador.get_reveal_child())
        boton.emit("clicked")
        self.assertTrue(revelador.get_reveal_child())
        self.assertTrue(boton.get_label().startswith("▼"))


if __name__ == "__main__":
    unittest.main()
