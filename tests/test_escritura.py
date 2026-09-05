import unittest
from tests.apoyo import BaseTemporal
from appstudy import escritura


class TestEscritura(BaseTemporal):

    def test_obtener_tema(self):
        tema_en = escritura.obtener_tema(self.con, "ingles")
        self.assertIn("titulo", tema_en)
        self.assertIn("instrucciones", tema_en)
        self.assertIn("nivel", tema_en)
        self.assertGreaterEqual(tema_en["min_palabras"], 50)

        tema_linux = escritura.obtener_tema(self.con, "linux")
        self.assertIn("titulo", tema_linux)

    def test_prompt_correccion_ia(self):
        tema = {
            "titulo": "Formal Complaint",
            "instrucciones": "Write a complaint email.",
            "nivel": "C1",
        }
        prompt = escritura.prompt_correccion_ia(tema, "Dear Sir, I am writing to express my dissatisfaction.")
        self.assertIn("Formal Complaint", prompt)
        self.assertIn("dissatisfaction", prompt)
        self.assertIn("Gramática", prompt)


if __name__ == "__main__":
    unittest.main()
