import unittest
from tests.apoyo import BaseTemporal
from appstudy import examen


class TestExamen(BaseTemporal):

    def setUp(self):
        super().setUp()
        self.did = self.mazo("test_exam", "Test Examen", ("A2", "B1", "B2", "C1"))
        for i in range(1, 10):
            self.tarjeta(self.did, f"Pregunta {i}", f"Respuesta {i}", level=1 if i <= 5 else 2, tags=f"tag_{i % 3}")

    def test_generar_preguntas_examen(self):
        preguntas = examen.generar_preguntas_examen(self.con, self.did, n=5)
        self.assertEqual(len(preguntas), 5)
        for p in preguntas:
            self.assertIn("pregunta", p)
            self.assertIn("opciones", p)
            self.assertIn("correcta", p)
            self.assertGreaterEqual(len(p["opciones"]), 2)

    def test_sesion_evaluar(self):
        preguntas = examen.generar_preguntas_examen(self.con, self.did, n=4)
        sesion = examen.ExamenSesion(preguntas)

        # Responder correctamente las dos primeras
        sesion.responder(0, preguntas[0]["correcta"])
        sesion.responder(1, preguntas[1]["correcta"])
        # Responder mal la tercera
        incorrecta = (preguntas[2]["correcta"] + 1) % len(preguntas[2]["opciones"])
        sesion.responder(2, incorrecta)
        # La cuarta sin responder (None)

        res = sesion.evaluar()
        self.assertEqual(res["total"], 4)
        self.assertEqual(res["aciertos"], 2)
        self.assertEqual(res["pct"], 50.0)
        self.assertEqual(res["nota_10"], 5.0)
        self.assertFalse(res["aprobado"])
        self.assertEqual(len(res["falladas"]), 2)
        self.assertIn(1, res["por_nivel"])


if __name__ == "__main__":
    unittest.main()
