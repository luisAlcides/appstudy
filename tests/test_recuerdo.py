"""Recuerdo libre: qué material entra, cómo se contrasta y qué se guarda."""
import unittest
from unittest.mock import patch

from appstudy import recuerdo
from tests.apoyo import BaseTemporal


class MaterialTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()
        for i in range(5):
            self.tarjeta(self.deck, f"pregunta {i}", f"respuesta {i}", level=1 + i % 2)

    def test_reune_el_material_del_mazo(self):
        material = recuerdo.material_de(self.con, deck_key="linux")
        self.assertEqual(len(material), 5)

    def test_se_puede_acotar_por_nivel(self):
        material = recuerdo.material_de(self.con, deck_key="linux", level=2)
        self.assertTrue(material)
        self.assertTrue(all("pregunta" in m["front"] for m in material))

    def test_el_texto_no_se_pasa_de_largo(self):
        largas = [{"front": "x" * 400, "back": "y" * 400} for _ in range(20)]
        texto = recuerdo.texto_material(largas)
        self.assertLessEqual(len(texto), recuerdo.MAX_CARACTERES + 400)

    def test_solo_ofrece_temas_con_material(self):
        flojo = self.mazo(key="flojo", name="Flojo")
        self.tarjeta(flojo, "única", key="flojo")
        temas = [t["key"] for t in recuerdo.temas_disponibles(self.con, minimo=4)]
        self.assertIn("linux", temas)
        self.assertNotIn("flojo", temas)


class EvaluarTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()
        for i in range(3):
            self.tarjeta(self.deck, f"pregunta {i}", f"respuesta {i}")
        self.material = recuerdo.material_de(self.con, deck_key="linux")

    def test_sin_decir_nada_no_se_llama_a_la_ia(self):
        with patch("appstudy.ia.evaluar_recuerdo") as evaluar:
            informe = recuerdo.evaluar({"activa": True}, self.material, "   ")
            evaluar.assert_not_called()
        self.assertEqual(informe["nota"], 0)
        self.assertTrue(informe["falto"])          # se le dice qué había que recordar

    def test_sin_ia_lo_dice_claramente(self):
        informe = recuerdo.evaluar({"activa": False}, self.material, "algo recordado")
        self.assertTrue(informe["sin_ia"])
        self.assertIn("IA", informe["veredicto"])

    def test_devuelve_lo_que_falto(self):
        respuesta = {"nota": 60, "cubierto": ["lo uno"], "falto": ["lo otro"],
                     "veredicto": "Vas bien"}
        with patch("appstudy.ia.evaluar_recuerdo", return_value=respuesta):
            informe = recuerdo.evaluar({"activa": True}, self.material, "lo uno")
        self.assertEqual(informe["falto"], ["lo otro"])
        self.assertFalse(informe["sin_ia"])

    def test_si_la_ia_falla_no_revienta(self):
        with patch("appstudy.ia.evaluar_recuerdo", side_effect=RuntimeError("sin modelo")):
            informe = recuerdo.evaluar({"activa": True}, self.material, "lo que sea")
        self.assertEqual(informe["nota"], 0)
        self.assertTrue(informe["sin_ia"])

    def test_el_historial_se_guarda_y_se_acota(self):
        for i in range(25):
            recuerdo.guardar(self.con, "linux", {"nota": i})
        hist = recuerdo.historial(self.con)
        self.assertLessEqual(len(hist), 20)
        self.assertEqual(hist[-1]["deck_key"], "linux")


class NotaCoherenteTest(unittest.TestCase):
    """La nota no puede pasarse de lo que el propio informe dice que recordaste."""

    MATERIAL = ("- ¿Cuándo usar media, mediana o moda? → mediana con valores extremos\n"
                "- ¿Qué es la correlación? → relación entre variables, no causalidad")

    def test_hablar_de_otra_cosa_no_puntua(self):
        # El fallo real: 65 de nota recordando mecánica sobre material de datos
        informe = {"nota": 65, "cubierto": [], "falto": ["a", "b", "c", "d"]}
        nota = recuerdo._nota_coherente(
            informe, self.MATERIAL,
            "Me acuerdo de revisar el aceite hidráulico antes de arrancar")
        self.assertLessEqual(nota, 5)

    def test_un_recuerdo_de_verdad_no_se_castiga(self):
        # El otro fallo: el modelo dejó vacío el recuento y hundía la nota a 0
        informe = {"nota": 70, "cubierto": [], "falto": ["a", "b"]}
        nota = recuerdo._nota_coherente(
            informe, self.MATERIAL,
            "La mediana se usa con valores extremos y la correlación no es causalidad")
        self.assertEqual(nota, 70)

    def test_el_solape_distingue_de_que_hablas(self):
        del_tema = recuerdo.solape(self.MATERIAL, "la mediana y la correlación")
        de_otro = recuerdo.solape(self.MATERIAL, "el aceite hidráulico del motor")
        self.assertGreater(del_tema, 0.5)
        self.assertLess(de_otro, recuerdo.SOLAPE_MINIMO)

    def test_la_nota_se_ata_a_la_proporcion(self):
        informe = {"nota": 90, "cubierto": ["a"], "falto": ["b", "c", "d"]}
        self.assertEqual(recuerdo._nota_coherente(informe), 25)

    def test_una_nota_ya_coherente_no_se_toca(self):
        informe = {"nota": 40, "cubierto": ["a", "b"], "falto": ["c", "d"]}
        self.assertEqual(recuerdo._nota_coherente(informe), 40)

    def test_sin_material_no_se_mira_el_solape(self):
        informe = {"nota": 55, "cubierto": ["a"], "falto": []}
        self.assertEqual(recuerdo._nota_coherente(informe), 55)

    def test_no_sube_la_nota_si_el_modelo_fue_duro(self):
        informe = {"nota": 30, "cubierto": ["a", "b", "c"], "falto": []}
        self.assertEqual(recuerdo._nota_coherente(informe), 30)

    def test_sin_listas_se_respeta_lo_que_diga(self):
        self.assertEqual(recuerdo._nota_coherente({"nota": 70}), 70)


if __name__ == "__main__":
    unittest.main()
