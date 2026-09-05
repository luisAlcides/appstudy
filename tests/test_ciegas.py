import unittest
from tests.apoyo import BaseTemporal
from appstudy import ciegas


class TestCiegas(BaseTemporal):

    def test_tarjetas_para_test_vacio(self):
        self.assertEqual(ciegas.tarjetas_para_test(self.con, {}), [])
        self.assertEqual(ciegas.tarjetas_para_test(self.con, None), [])

    def test_tarjetas_para_test_con_capitulo(self):
        did = self.mazo("test_ciegas", "Test Ciegas", ("A2", "B1"))
        self.tarjeta(did, "Hello world", "Hola mundo", tags="saludos,básico", level=1)
        self.tarjeta(did, "Good morning", "Buenos días", tags="saludos,básico", level=1)

        cap = {
            "deck_id": did,
            "level": 1,
            "title": "Saludos en inglés",
            "tags": "saludos,básico"
        }

        tarjetas = ciegas.tarjetas_para_test(self.con, cap, n=5)
        self.assertGreaterEqual(len(tarjetas), 1)
        self.assertIn("front", tarjetas[0])


if __name__ == "__main__":
    unittest.main()
