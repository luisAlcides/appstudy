"""Pruebas para el módulo de reconocimiento de voz y juicio de respuestas."""
import unittest

from appstudy import voz_rec


class TestVozRec(unittest.TestCase):
    def test_juzgar_respuesta_exacta(self):
        res = voz_rec.juzgar_respuesta("hello world", "Hello World")
        self.assertTrue(res["acierto"])
        self.assertGreaterEqual(res["similitud"], 0.9)
        self.assertEqual(res["dicho"], "hello world")
        self.assertEqual(res["esperado"], "hello world")

    def test_juzgar_respuesta_vacia(self):
        res = voz_rec.juzgar_respuesta("", "Paris")
        self.assertFalse(res["acierto"])
        self.assertEqual(res["similitud"], 0.0)
        self.assertIn("No se detectó", res["feedback"])

    def test_juzgar_respuesta_parcial(self):
        res = voz_rec.juzgar_respuesta("The capital of France is Paris", "Paris")
        self.assertTrue(res["acierto"])
        self.assertIn("capital", res["dicho"])

    def test_grabador_microfono_init(self):
        grabador = voz_rec.GrabadorMicrofono()
        self.assertFalse(grabador.esta_grabando())

    def test_tiene_reconocimiento_voz(self):
        # No debe lanzar excepción
        disp = voz_rec.tiene_reconocimiento_voz("es")
        self.assertIsInstance(disp, bool)


if __name__ == "__main__":
    unittest.main()


class TestDetectorTurnos(unittest.TestCase):
    """El detector es lo que sustituye al botón de «he terminado de hablar»."""

    @staticmethod
    def bloque(amplitud, ms=125, rate=16000):
        import array
        import math
        n = int(rate * ms / 1000)
        muestras = array.array("h", (int(amplitud * math.sin(i * 0.05)) for i in range(n)))
        return muestras.tobytes()

    def test_cierra_el_turno_tras_un_silencio(self):
        det = voz_rec.DetectorTurnos(silencio_fin=1.0)
        silencio, habla = self.bloque(60), self.bloque(6000)
        for _ in range(8):
            self.assertEqual(det.procesar(silencio), "silencio")
        self.assertEqual(det.procesar(habla), "hablando")
        estados = [det.procesar(habla) for _ in range(11)]
        self.assertNotIn("fin", estados)
        # Ocho bloques de 125 ms son el segundo de silencio que cierra el turno
        estados = [det.procesar(silencio) for _ in range(8)]
        self.assertEqual(estados[-1], "fin")

    def test_un_ruido_corto_no_cierra_turno(self):
        det = voz_rec.DetectorTurnos()
        silencio, habla = self.bloque(60), self.bloque(6000)
        secuencia = ([det.procesar(silencio) for _ in range(5)]
                     + [det.procesar(habla)]                      # 125 ms: un carraspeo
                     + [det.procesar(silencio) for _ in range(12)])
        self.assertNotIn("fin", secuencia)

    def test_corta_un_turno_interminable(self):
        # Quien habla sin pausas largas nunca cerraría turno por silencio: el
        # tope de duración es lo que hace que Bit conteste igualmente.
        det = voz_rec.DetectorTurnos(maximo_turno=2.0)
        silencio, habla = self.bloque(60), self.bloque(6000)
        estados = []
        for i in range(40):
            estados.append(det.procesar(habla if i % 4 else silencio))
        self.assertIn("fin", estados)

    def test_un_ruido_constante_no_se_toma_por_voz(self):
        # Un ventilador o un aire acondicionado suben el suelo de ruido y dejan
        # de contar como voz; si no, el turno no se cerraría nunca.
        det = voz_rec.DetectorTurnos()
        ruido = self.bloque(4000)
        estados = [det.procesar(ruido) for _ in range(30)]
        self.assertEqual(estados[-1], "silencio")

    def test_el_umbral_se_adapta_al_ruido_de_la_sala(self):
        tranquila, ruidosa = voz_rec.DetectorTurnos(), voz_rec.DetectorTurnos()
        for _ in range(60):
            tranquila.procesar(self.bloque(50))
            ruidosa.procesar(self.bloque(4000))
        self.assertGreater(ruidosa.umbral, tranquila.umbral)
        # Con un ventilador al lado, ese mismo ruido ya no se toma por voz
        self.assertEqual(ruidosa.procesar(self.bloque(4000)), "silencio")
        self.assertEqual(tranquila.procesar(self.bloque(4000)), "hablando")


class TestEscuchaContinua(unittest.TestCase):
    """El bucle completo: micrófono → turno → texto, sin tocar el micrófono."""

    def escucha_con_audio(self, pcm: bytes):
        import os
        import tempfile
        fd, ruta = tempfile.mkstemp(suffix=".raw")
        with os.fdopen(fd, "wb") as f:
            f.write(pcm)
        self.addCleanup(os.unlink, ruta)

        esc = voz_rec.EscuchaContinua(idioma="es")
        esc._comando = staticmethod(lambda: ["cat", ruta])
        esc._transcribir = lambda pcm_turno: "hola bit"
        return esc

    def test_entrega_el_turno_cuando_te_callas(self):
        import time
        bloque = TestDetectorTurnos.bloque
        # Silencio, un par de segundos hablando y silencio otra vez
        pcm = bloque(60) * 4 + bloque(6000) * 16 + bloque(60) * 12
        oidos, estados = [], []
        esc = self.escucha_con_audio(pcm)
        esc.al_oir, esc.al_estado = oidos.append, estados.append
        self.assertTrue(esc.iniciar())
        self.addCleanup(esc.detener)

        limite = time.time() + 10
        while not oidos and time.time() < limite:
            time.sleep(0.05)
        self.assertEqual(oidos, ["hola bit"])
        self.assertEqual(estados[:2], ["escuchando", "procesando"])

    def test_lo_que_suena_mientras_bit_habla_se_descarta(self):
        import time
        bloque = TestDetectorTurnos.bloque
        pcm = bloque(6000) * 16 + bloque(60) * 12
        oidos = []
        esc = self.escucha_con_audio(pcm)
        esc.al_oir = oidos.append
        self.assertTrue(esc.iniciar())
        self.addCleanup(esc.detener)
        esc.pausar()          # Bit está hablando por los altavoces

        time.sleep(1.0)
        self.assertEqual(oidos, [])


class TestPalabraClave(unittest.TestCase):
    """«Hola bit» tiene que despertar a Bit, y nada más debería."""

    def test_reconoce_el_saludo_y_sus_confusiones(self):
        # Vosk oye «vit» o «bip» donde dices «bit»: se dan por buenas
        for oido in ("hola bit", "hola vit", "hola bip", "oye bit", "hola bit qué tal"):
            self.assertTrue(voz_rec.es_palabra_clave(oido), oido)

    def test_no_despierta_con_saludos_ni_charla(self):
        for oido in ("hola", "hola buenos días", "hola cómo estás", "adiós hasta luego",
                     "bit es la mascota", "el bit es la unidad mínima", ""):
            self.assertFalse(voz_rec.es_palabra_clave(oido), oido)

    def test_hace_falta_el_orden_correcto(self):
        # «bit hola» es lo que sale cuando el motor se lía; no es un saludo
        self.assertFalse(voz_rec.es_palabra_clave("bit hola"))

    def test_la_gramatica_lleva_senuelos(self):
        import json
        frases = json.loads(voz_rec.gramatica_clave())
        self.assertIn("hola bit", frases)
        self.assertIn("[unk]", frases)
        # Sin sitios donde caer, el motor mete cualquier saludo en «hola bit»
        for senuelo in voz_rec.SENUELOS_CLAVE:
            self.assertIn(senuelo, frases)


class PronunciacionTest(unittest.TestCase):
    """Puntuar cómo se dice una frase, no si la respuesta es correcta."""

    @staticmethod
    def oidas(*pares):
        return [{"palabra": p, "conf": c} for p, c in pares]

    def test_todo_limpio_es_sobresaliente(self):
        r = voz_rec.evaluar_pronunciacion(
            "She works on Sundays",
            self.oidas(("she", 1.0), ("works", 0.95), ("on", 0.99), ("sundays", 0.92)))
        self.assertEqual(r["nota"], 100)
        self.assertEqual(r["repasar"], [])

    def test_marca_la_palabra_dudosa(self):
        r = voz_rec.evaluar_pronunciacion(
            "She works on Sundays",
            self.oidas(("she", 1.0), ("works", 0.55), ("on", 0.99), ("sundays", 0.90)))
        estados = {d["palabra"]: d["estado"] for d in r["detalle"]}
        self.assertEqual(estados["works"], "floja")
        self.assertEqual(r["repasar"], ["works"])
        self.assertLess(r["nota"], 100)
        self.assertGreater(r["nota"], 70)

    def test_una_palabra_que_no_sale_cuenta_como_mal(self):
        r = voz_rec.evaluar_pronunciacion(
            "She works on Sundays",
            self.oidas(("she", 1.0), ("on", 0.99), ("sundays", 0.95)))
        estados = {d["palabra"]: d["estado"] for d in r["detalle"]}
        self.assertEqual(estados["works"], "mal")
        self.assertIn("works", r["repasar"])

    def test_el_detalle_sigue_el_orden_de_lo_esperado(self):
        r = voz_rec.evaluar_pronunciacion("uno dos tres", self.oidas(("tres", 1.0)))
        self.assertEqual([d["palabra"] for d in r["detalle"]], ["uno", "dos", "tres"])

    def test_sin_confianzas_se_juzga_por_las_palabras(self):
        # Con motores que no dan confianza (whisper), al menos se ve qué falta
        r = voz_rec.evaluar_pronunciacion("hello world", [], dicho="hello")
        estados = {d["palabra"]: d["estado"] for d in r["detalle"]}
        self.assertEqual(estados["hello"], "bien")
        self.assertEqual(estados["world"], "mal")

    def test_frase_vacia_no_revienta(self):
        r = voz_rec.evaluar_pronunciacion("", [])
        self.assertEqual(r["nota"], 0)
        self.assertEqual(r["detalle"], [])

    def test_ignora_el_formato_de_la_tarjeta(self):
        # La respuesta puede venir con HTML o cloze: se compara lo que se dice
        r = voz_rec.evaluar_pronunciacion(
            "<b>She</b> {{c1::works}} on Sundays",
            self.oidas(("she", 1.0), ("works", 1.0), ("on", 1.0), ("sundays", 1.0)))
        self.assertEqual(r["nota"], 100)
