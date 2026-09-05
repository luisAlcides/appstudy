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
