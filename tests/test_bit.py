import unittest

from appstudy import ia, pet, scheduler
from tests.apoyo import BaseTemporal


class EvolucionBitTest(unittest.TestCase):
    def test_empieza_como_companero(self):
        estado = pet.evolucion(0)
        self.assertEqual(estado["nombre"], "Compañero")
        self.assertEqual(estado["siguiente"]["min"], 25)
        self.assertEqual(estado["avance"], 0)

    def test_cambia_en_cada_umbral(self):
        esperados = ((24, "Compañero"), (25, "Curioso"), (100, "Aplicado"),
                     (500, "Sabio"), (1500, "Maestro"))
        for repasos, nombre in esperados:
            self.assertEqual(pet.evolucion(repasos)["nombre"], nombre)

    def test_avance_es_acotado_y_el_maximo_no_tiene_siguiente(self):
        self.assertAlmostEqual(pet.evolucion(50)["avance"], 25 / 75)
        maestro = pet.evolucion(99999)
        self.assertEqual(maestro["avance"], 1)
        self.assertIsNone(maestro["siguiente"])

    def test_accesorios_se_desbloquean_gradualmente(self):
        self.assertEqual([a["key"] for a in pet.accesorios_disponibles(0)], ["ninguno"])
        self.assertEqual([a["key"] for a in pet.accesorios_disponibles(100)],
                         ["ninguno", "panuelo", "gafas"])

    def test_un_accesorio_bloqueado_o_desconocido_no_se_aplica(self):
        self.assertEqual(pet.accesorio_valido("corona", 499), "ninguno")
        self.assertEqual(pet.accesorio_valido("corona", 500), "corona")
        self.assertEqual(pet.accesorio_valido("sombrero", 9999), "ninguno")


class TotalRepasosBitTest(BaseTemporal):
    def test_cuenta_el_trabajo_real(self):
        did = self.mazo()
        cid = self.tarjeta(did, "Una")
        self.assertEqual(pet.total_repasos(self.con), 0)
        scheduler.apply_review(self.con, cid, scheduler.GOOD)
        scheduler.apply_review(self.con, cid, scheduler.HARD)
        self.assertEqual(pet.total_repasos(self.con), 2)


if __name__ == "__main__":
    unittest.main()


class ConversacionHabladaTest(unittest.TestCase):
    """Las decisiones de la charla hablada, sin levantar la ventana de Bit."""

    def despedida(self, texto):
        return pet.PetWindow.es_despedida(texto)

    def test_reconoce_las_despedidas(self):
        for frase in ("adiós", "Adiós", "hasta luego", "ya está", "Gracias Bit", "chao"):
            self.assertTrue(self.despedida(frase), frase)

    def test_no_corta_la_charla_por_una_palabra_suelta(self):
        # "adiós" dentro de una pregunta es materia de estudio, no una despedida
        for frase in ("¿cómo se dice adiós en inglés?", "explícame el para qué",
                      "hasta luego se dice see you later"):
            self.assertFalse(self.despedida(frase), frase)


class RespuestaHabladaTest(unittest.TestCase):
    def test_acorta_por_la_ultima_frase_entera(self):
        largo = ("Primera frase corta. " * 30).strip()
        corto = ia.acortar_para_hablar(largo, maximo=10)
        self.assertTrue(corto.endswith("."))
        self.assertLessEqual(len(corto.split()), 10)

    def test_deja_en_paz_lo_que_ya_es_breve(self):
        breve = "Claro, el repaso espaciado sirve para no olvidar. ¿Seguimos?"
        self.assertEqual(ia.acortar_para_hablar(breve), breve)
        self.assertEqual(ia.acortar_para_hablar(""), "")

    def test_una_parrafada_sin_puntos_se_corta_igual(self):
        sin_puntos = " ".join(["palabra"] * 80)
        corto = ia.acortar_para_hablar(sin_puntos, maximo=12)
        self.assertEqual(len(corto.split()), 12)
        self.assertTrue(corto.endswith("."))


class AnimoTest(unittest.TestCase):
    """Cuándo se pone verde Bit. Antes: casi siempre."""

    @staticmethod
    def totales(**cambios):
        base = {"pendientes": 0, "hoy": 0, "nuevas": 0, "racha": 0, "objetivo": 0}
        return {**base, **cambios}

    def test_una_tarjeta_suelta_no_la_pone_verde(self):
        # Era el fallo: repasar una sola tarjeta la dejaba contenta
        self.assertEqual(pet.animo(self.totales(hoy=1), horas=0.5, energia=0.9), "normal")
        self.assertEqual(pet.animo(self.totales(hoy=9), horas=0.5, energia=0.9), "normal")

    def test_verde_al_llegar_al_minimo_sin_pendientes(self):
        t = self.totales(hoy=pet.MINIMO_FELIZ)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "feliz")

    def test_con_objetivo_manda_el_objetivo(self):
        t = self.totales(hoy=12, objetivo=30)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "normal")
        self.assertEqual(pet.animo({**t, "hoy": 30}, horas=0.5, energia=0.9), "feliz")
        # Un objetivo bajo también vale: no se exige el mínimo por encima de él
        t_bajo = self.totales(hoy=5, objetivo=5)
        self.assertEqual(pet.animo(t_bajo, horas=0.5, energia=0.9), "feliz")

    def test_con_repasos_vencidos_no_hay_verde(self):
        t = self.totales(hoy=50, pendientes=7)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "normal")

    def test_el_verde_no_dura_todo_el_dia(self):
        t = self.totales(hoy=40)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9), "feliz")
        self.assertEqual(pet.animo(t, horas=pet.HORAS_ABURRIDO, energia=0.9), "aburrido")
        self.assertEqual(pet.animo(t, horas=pet.HORAS_HAMBRE, energia=0.9), "hambre")
        self.assertEqual(pet.animo(t, horas=pet.HORAS_TRISTE, energia=0.9), "triste")

    def test_dormida_manda_sobre_todo(self):
        t = self.totales(hoy=40)
        self.assertEqual(pet.animo(t, horas=0.5, energia=0.9, dormida=True), "dormido")

    def test_sin_energia_tiene_hambre(self):
        t = self.totales(hoy=2, pendientes=30)
        self.assertEqual(pet.animo(t, horas=1.0, energia=0.2), "hambre")
