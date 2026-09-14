"""La respuesta escrita se corrige contra el hueco que ve el usuario."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.apoyo import BaseTemporal
from appstudy import cloze, pet, reto


class TestRespuestasEscritas(BaseTemporal):
    def preparar(self, formato, indice=0):
        deck = self.mazo()
        cid = self.tarjeta(
            deck, "El comando {{chmod}} cambia los {{permisos}}.",
            "Los permisos controlan quién puede leer, escribir y ejecutar.",
            kind="cloze")
        card = self.con.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        with patch.object(reto.random, "choices", return_value=[formato]), \
                patch.object(cloze, "elegir", return_value=indice):
            return reto.preparar(self.con, card)

    def comprobar(self, ejercicio, texto, estricto=False):
        ventana = SimpleNamespace(reto=ejercicio, con=self.con, resolver=Mock())
        entrada = Mock()
        entrada.get_text.return_value = texto
        with patch.object(pet, "estricto", return_value=estricto):
            pet.PetWindow.comprobar_escrito(ventana, entrada)
        return ventana.resolver

    def test_escribir_acepta_la_palabra_sin_exigir_la_explicacion(self):
        ejercicio = self.preparar("escribir")
        for estricto in (False, True):
            with self.subTest(estricto=estricto):
                self.comprobar(ejercicio, "chmod", estricto).assert_called_once_with(
                    True, elegida="chmod")

    def test_escribir_rechaza_otra_palabra(self):
        self.comprobar(self.preparar("escribir"), "grep").assert_called_once_with(
            False, elegida="grep")

    def test_solo_se_oculta_el_hueco_que_se_evalua(self):
        for formato, indice, visible, oculta in (
                ("escribir", 0, "permisos", "chmod"),
                ("hueco", 1, "chmod", "permisos")):
            with self.subTest(formato=formato):
                ejercicio = self.preparar(formato, indice)
                self.assertIn(visible, ejercicio["pregunta"])
                self.assertNotIn(oculta, ejercicio["pregunta"])
                self.assertEqual(ejercicio["pregunta"].count(cloze.HUECO), 1)
                self.comprobar(ejercicio, oculta).assert_called_once_with(
                    True, elegida=oculta)

    def test_tarjeta_normal_sigue_evaluando_su_respuesta(self):
        self.comprobar({"respuesta": "chmod"}, "chmod").assert_called_once_with(
            True, elegida="chmod")

    def test_entrada_vacia_no_registra_un_fallo(self):
        self.comprobar({"respuesta": "chmod"}, "  ").assert_not_called()
