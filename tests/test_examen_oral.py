"""El examen oral: elegir de qué preguntar, calificar y cerrar el acta.

La IA se sustituye por una falsa, así que estas pruebas fijan el comportamiento
del examen —qué entra, qué nota sale, qué se guarda— sin depender de que haya
un modelo descargado ni de lo que ese modelo conteste hoy.
"""
import time
import unittest
from unittest.mock import patch

from appstudy import db, examen_oral
from tests.apoyo import BaseTemporal


class TarjetasParaExamenTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()

    def test_solo_entra_lo_que_ya_has_estudiado(self):
        vista = self.tarjeta(self.deck, "vista")
        self.tarjeta(self.deck, "sin estrenar")
        self.repasar(vista, 3)
        elegidas = examen_oral.tarjetas_para_examen(self.con)
        self.assertEqual([c["id"] for c in elegidas], [vista])

    def test_primero_lo_que_llevas_más_tiempo_sin_repasar(self):
        vieja = self.tarjeta(self.deck, "vieja")
        reciente = self.tarjeta(self.deck, "reciente")
        self.repasar(vieja, 3, cuando=time.time() - 30 * 86400)
        self.con.execute("UPDATE state SET last=? WHERE card_id=?",
                         (time.time() - 30 * 86400, vieja))
        self.repasar(reciente, 3)
        self.con.commit()
        elegidas = examen_oral.tarjetas_para_examen(self.con, cuantas=2)
        self.assertEqual(elegidas[0]["id"], vieja)

    def test_se_puede_acotar_a_un_mazo(self):
        otro = self.mazo(key="mecanica", name="Mecánica")
        propia = self.tarjeta(self.deck, "de linux")
        ajena = self.tarjeta(otro, "de mecánica", key="mecanica")
        self.repasar(propia, 3)
        self.repasar(ajena, 3)
        elegidas = examen_oral.tarjetas_para_examen(self.con, deck_key="mecanica")
        self.assertEqual([c["id"] for c in elegidas], [ajena])

    def test_nunca_devuelve_más_de_lo_pedido(self):
        for i in range(6):
            cid = self.tarjeta(self.deck, f"tarjeta {i}")
            self.repasar(cid, 3)
        self.assertEqual(len(examen_oral.tarjetas_para_examen(self.con, cuantas=3)), 3)


class ExamenOralTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.deck = self.mazo()
        self.ids = []
        for i in range(3):
            cid = self.tarjeta(self.deck, f"¿Qué es {i}?", f"La respuesta {i}")
            self.repasar(cid, 3)
            self.ids.append(cid)
        self.tarjetas = examen_oral.tarjetas_para_examen(self.con, cuantas=3)

    def examen(self):
        return examen_oral.ExamenOral(self.con, {"activa": True}, self.tarjetas)

    def test_recorre_todas_las_preguntas_y_termina(self):
        ex = self.examen()
        with patch("appstudy.ia.preguntar_de_viva_voz", return_value="¿Me lo explicas?"), \
             patch("appstudy.ia.calificar_respuesta",
                   return_value={"nota": 80, "veredicto": "Bien", "falto": ""}):
            for i in range(3):
                self.assertFalse(ex.terminado())
                self.assertEqual(ex.marcador(), f"Pregunta {i + 1} de 3")
                self.assertEqual(ex.siguiente_pregunta(), "¿Me lo explicas?")
                self.assertEqual(ex.responder("lo que sea")["nota"], 80)
        self.assertTrue(ex.terminado())
        self.assertEqual(ex.nota_media(), 80)

    def test_no_responder_es_un_cero_sin_llamar_a_la_ia(self):
        ex = self.examen()
        with patch("appstudy.ia.calificar_respuesta") as calificar:
            ex.siguiente_pregunta()
            resultado = ex.responder("   ")
            calificar.assert_not_called()
        self.assertEqual(resultado["nota"], 0)

    def test_si_la_ia_falla_el_examen_sigue(self):
        ex = self.examen()
        with patch("appstudy.ia.preguntar_de_viva_voz", side_effect=RuntimeError("sin modelo")), \
             patch("appstudy.ia.calificar_respuesta", side_effect=RuntimeError("sin modelo")):
            pregunta = ex.siguiente_pregunta()
            resultado = ex.responder("algo")
        # Sin IA se pregunta el frente de la tarjeta tal cual
        self.assertEqual(pregunta, "¿Qué es 0?")
        self.assertEqual(resultado["nota"], 0)
        self.assertTrue(ex.terminado() is False)

    def test_el_acta_separa_lo_flojo(self):
        ex = self.examen()
        notas = [95, 30, 55]
        with patch("appstudy.ia.preguntar_de_viva_voz", return_value="¿?"), \
             patch("appstudy.ia.calificar_respuesta",
                   side_effect=[{"nota": n, "veredicto": "v", "falto": "f"} for n in notas]):
            for _ in notas:
                ex.siguiente_pregunta()
                ex.responder("respuesta")
        acta = ex.acta()
        self.assertEqual(acta["nota"], 60)
        self.assertEqual(acta["aprobadas"], 1)          # solo el 95 llega a 60
        self.assertEqual([f["nota"] for f in acta["flojas"]], [30, 55])

    def test_el_acta_se_guarda_y_se_puede_releer(self):
        ex = self.examen()
        with patch("appstudy.ia.preguntar_de_viva_voz", return_value="¿?"), \
             patch("appstudy.ia.calificar_respuesta",
                   return_value={"nota": 70, "veredicto": "v", "falto": ""}):
            for _ in range(3):
                ex.siguiente_pregunta()
                ex.responder("respuesta")
        ex.guardar()
        hist = examen_oral.historial(self.con)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["nota"], 70)
        self.assertEqual(hist[0]["aciertos"], "3/3")

    def test_el_historial_no_crece_sin_freno(self):
        for i in range(25):
            db.set_meta(self.con, "examenes_orales",
                        (db.get_meta(self.con, "examenes_orales", "") or ""))
            ex = self.examen()
            with patch("appstudy.ia.preguntar_de_viva_voz", return_value="¿?"), \
                 patch("appstudy.ia.calificar_respuesta",
                       return_value={"nota": i, "veredicto": "v", "falto": ""}):
                ex.siguiente_pregunta()
                ex.responder("r")
            ex.guardar()
        self.assertLessEqual(len(examen_oral.historial(self.con)), 20)


class NoRespuestaTest(unittest.TestCase):
    """Decir que no lo sabes es un cero, y eso no se le pregunta al modelo."""

    def test_reconoce_las_formas_de_no_saber(self):
        for texto in ("no sé", "ni idea", "nada", "no me acuerdo", "   ",
                      "pues no me acuerdo", "no lo sé la verdad", "NI IDEA"):
            self.assertTrue(examen_oral.es_no_respuesta(texto), texto)

    def test_una_respuesta_de_verdad_no_lo_es(self):
        for texto in ("El aceite hidráulico se revisa en frío y en suelo llano",
                      "Sirve para separar los campos de un archivo de texto",
                      "creo que es para repasar antes de olvidar"):
            self.assertFalse(examen_oral.es_no_respuesta(texto), texto)

    def test_no_confundir_una_negación_con_contenido(self):
        # «no se usa en caliente» empieza por «no se» pero está respondiendo
        self.assertFalse(examen_oral.es_no_respuesta(
            "no se revisa en caliente porque el aceite se dilata"))


if __name__ == "__main__":
    unittest.main()
