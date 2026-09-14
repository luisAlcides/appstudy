"""Lo que pasa cuando un trabajo de fondo falla o la ventana ya no está.

Son los dos fallos que no se ven: un modelo que no responde dejaba la interfaz
esperando para siempre sin decir nada, y un resultado que llega tarde pintaba
sobre una ventana ya cerrada.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from appstudy import util
from tests.apoyo import BaseTemporal


def vaciar_idles(limite=200):
    """Gasta los `idle_add` pendientes, que es lo que haría el bucle de GTK."""
    from gi.repository import GLib

    contexto = GLib.MainContext.default()
    for _ in range(limite):
        if not contexto.iteration(False):
            return


def esperar(hilo):
    hilo.join(timeout=5)
    vaciar_idles()


class VentanaFalsa:
    """Lo mínimo que `util.en_pie` le pregunta a un widget."""

    def __init__(self, visible=True):
        self.visible = visible

    def get_root(self):
        return self

    def get_visible(self):
        return self.visible


class HiloTest(unittest.TestCase):
    def test_un_trabajo_que_revienta_avisa_en_vez_de_callarse(self):
        fallo = Mock()
        esperar(util.hilo(lambda: 1 / 0, Mock(), fallo, largo=True))
        fallo.assert_called_once()
        self.assertIsInstance(fallo.call_args.args[0], ZeroDivisionError)

    def test_sin_al_fallar_el_error_no_tumba_la_aplicacion(self):
        terminar = Mock()
        esperar(util.hilo(lambda: 1 / 0, terminar, largo=True))
        terminar.assert_not_called()

    def test_el_resultado_llega_al_hilo_de_la_interfaz(self):
        terminar = Mock()
        esperar(util.hilo(lambda: "listo", terminar, largo=True))
        terminar.assert_called_once_with("listo")

    def test_un_callback_que_devuelve_cierto_no_se_repite(self):
        # `idle_add` reprograma el callback mientras devuelva algo cierto: sin
        # cortarlo, un `al_terminar` que devuelva True gira sin parar.
        veces = []
        esperar(util.hilo(lambda: 1, lambda _r: veces.append(1) or True, largo=True))
        vaciar_idles()
        self.assertEqual(len(veces), 1)


class VentanaCerradaTest(unittest.TestCase):
    def test_en_pie_distingue_la_ventana_viva_de_la_cerrada(self):
        self.assertTrue(util.en_pie(VentanaFalsa(visible=True)))
        self.assertFalse(util.en_pie(VentanaFalsa(visible=False)))
        self.assertFalse(util.en_pie(None))

    def test_en_pie_con_una_ventana_de_verdad(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, Gtk

        Gtk.init()
        if Gdk.Display.get_default() is None:
            self.skipTest("Requiere pantalla GTK")
        ventana = Gtk.Window()
        etiqueta = Gtk.Label()
        ventana.set_child(etiqueta)
        ventana.present()
        self.assertTrue(util.en_pie(etiqueta), "abierta: el resultado sí se pinta")
        ventana.destroy()
        self.assertFalse(util.en_pie(etiqueta), "cerrada: pintar aquí es una crítica")

    def test_si_la_ventana_se_cierra_no_se_toca_nada(self):
        ventana = VentanaFalsa()
        terminar, fallo = Mock(), Mock()
        # El trabajo tarda: cuando acabe, la ventana ya no estará.
        esperar(util.hilo(lambda: ventana.__setattr__("visible", False) or "tarde",
                          terminar, fallo, largo=True, vivo=ventana))
        terminar.assert_not_called()
        fallo.assert_not_called()

    def test_con_la_ventana_abierta_el_resultado_sí_llega(self):
        ventana = VentanaFalsa()
        terminar = Mock()
        esperar(util.hilo(lambda: "a tiempo", terminar, largo=True, vivo=ventana))
        terminar.assert_called_once_with("a tiempo")


class MicrofonoQueFallaTest(BaseTemporal):
    """El caso real: Vosk no está, o el modelo no contesta."""

    def bit(self):
        grabador = Mock()
        grabador.esta_grabando.return_value = True
        grabador.detener.return_value = "/tmp/no-importa.wav"
        ventana = SimpleNamespace(
            con=self.con, grabador_mic=grabador, btn_mic=None,
            card={"id": 1, "back": "una respuesta", "front": "una pregunta"},
            creature=Mock(), say=Mock(), sonar=Mock(), cara_de_la_voz=Mock(),
            voz_cfg={"activo": True}, on_voz_terminada=Mock(),
            get_root=lambda: VentanaFalsa())
        return ventana

    def test_si_no_se_puede_transcribir_se_dice_en_vez_de_quedarse_mudo(self):
        from appstudy import pet, voz_rec

        ventana = self.bit()
        with patch.object(voz_rec, "transcribir_audio",
                          side_effect=RuntimeError("falta el modelo de Vosk")):
            pet.PetWindow.alternar_microfono(ventana)
            vaciar_idles()
            for _ in range(50):          # el trabajo va en su propio hilo
                vaciar_idles()
                if ventana.say.called:
                    break
        ventana.say.assert_called_once()
        self.assertIn("falta el modelo de Vosk", ventana.say.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
