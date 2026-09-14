"""El cuaderno de bitácora: que exista, que no moleste y que recoja lo que pasa.

Lo que se prueba aquí no es el módulo `logging`, es la política: importar
`appstudy` no debe crear ficheros, y un fallo que la aplicación decide tragarse
para no interrumpirte tiene que quedar escrito en algún sitio.
"""
import logging
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from appstudy import pomodoro, registro, sonido
from tests.apoyo import BaseTemporal


class ConCuaderno(BaseTemporal):
    """Montaje común: un cuaderno de usar y tirar, desmontado al terminar."""
    def setUp(self):
        super().setUp()
        self.carpeta = self.tmp / "bitacora"
        self.addCleanup(self._desmontar)

    def _desmontar(self):
        raiz = logging.getLogger(registro.NOMBRE)
        for m in list(raiz.handlers):
            if not isinstance(m, logging.NullHandler):
                m.close()
                raiz.removeHandler(m)
        registro._configurado = False

    def abrir(self, debug=False):
        entorno = {"APPSTUDY_DEBUG": "1"} if debug else {}
        with patch.dict("os.environ", entorno, clear=not debug):
            return registro.configurar(self.carpeta)

    def leido(self):
        archivo = self.carpeta / registro.ARCHIVO
        return archivo.read_text(encoding="utf-8") if archivo.exists() else ""


class CuadernoTest(ConCuaderno):
    def test_sin_configurar_no_se_escribe_en_ningun_sitio(self):
        registro.log("appstudy.prueba").warning("esto no debería ir a disco")
        self.assertFalse(self.carpeta.exists(),
                         "importar appstudy no puede crear ficheros")

    def test_configurar_abre_el_cuaderno_y_recoge_los_avisos(self):
        self.abrir()
        registro.log("appstudy.voz").warning("Piper no arrancó")
        self.assertIn("Piper no arrancó", self.leido())

    def test_en_marcha_normal_el_detalle_no_ensucia(self):
        self.abrir()
        registro.log("appstudy.voz").debug("cerrando una tubería")
        registro.log("appstudy.voz").warning("esto sí")
        texto = self.leido()
        self.assertNotIn("cerrando una tubería", texto)
        self.assertIn("esto sí", texto)

    def test_con_APPSTUDY_DEBUG_se_recoge_tambien_el_detalle(self):
        self.abrir(debug=True)
        registro.log("appstudy.voz").debug("cerrando una tubería")
        self.assertIn("cerrando una tubería", self.leido())

    def test_sin_sitio_donde_escribir_se_sigue_sin_cuaderno(self):
        # Un disco lleno o un permiso denegado no puede impedir que arranque.
        with patch.object(Path, "mkdir", side_effect=OSError("sin sitio")):
            registro.configurar(self.carpeta)      # no levanta

    def test_la_traza_del_error_queda_entera(self):
        self.abrir()
        try:
            raise ValueError("el motivo de verdad")
        except ValueError:
            registro.log("appstudy.voz").warning("algo falló", exc_info=True)
        texto = self.leido()
        self.assertIn("el motivo de verdad", texto)
        self.assertIn("Traceback", texto)


class SitiosRealesTest(ConCuaderno):
    """Dos sitios de los que antes hacían `pass`, de punta a punta."""

    def test_un_sonido_que_no_suena_deja_constancia(self):
        self.abrir()
        with patch.object(sonido, "archivo", return_value=self.tmp / "v.wav"), \
                patch.object(sonido, "_gsound", return_value=None), \
                patch.object(sonido, "_reproductor", "falso-player"), \
                patch.object(subprocess, "Popen",
                             side_effect=FileNotFoundError("falso-player")):
            sonido.reproducir({"activo": True, "volumen": 0.7}, "victoria")
        texto = self.leido()
        self.assertIn("No se pudo tocar", texto)
        self.assertIn("falso-player", texto)

    def test_la_campana_del_pomodoro_suena_de_verdad(self):
        """Llamaba a `sonido.tocar`, que no existe, y el `pass` se lo comía."""
        self.abrir()
        control = pomodoro.PomodoroControl(self.con)
        with patch.object(sonido, "reproducir") as suena:
            control._al_completar_trabajo()
            control._al_completar_descanso()
        self.assertEqual([c.args[1] for c in suena.call_args_list],
                         ["victoria", "subida"])
        self.assertNotIn("Sin campana", self.leido())


if __name__ == "__main__":
    unittest.main()
