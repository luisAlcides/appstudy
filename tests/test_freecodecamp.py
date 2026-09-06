"""Pruebas unitarias para el módulo de integración con freeCodeCamp."""
import json
import unittest
from unittest import mock

from appstudy import freecodecamp


class TestFreeCodeCamp(unittest.TestCase):

    def test_normalizar_url_completa(self):
        url = "https://www.freecodecamp.org/learn/scientific-computing-with-python/step-1"
        self.assertEqual(freecodecamp.normalizar_url(url), url)

    def test_normalizar_slug_relativo(self):
        slug = "/learn/data-analysis-with-python/"
        self.assertEqual(
            freecodecamp.normalizar_url(slug),
            "https://www.freecodecamp.org/learn/data-analysis-with-python/"
        )

    def test_normalizar_nombre_certificacion(self):
        nombre = "scientific-computing-with-python"
        self.assertEqual(
            freecodecamp.normalizar_url(nombre),
            "https://www.freecodecamp.org/learn/scientific-computing-with-python/"
        )

    def test_normalizar_url_vacia_lanza_error(self):
        with self.assertRaises(freecodecamp.FCCError):
            freecodecamp.normalizar_url("   ")

    def test_limpiar_html_fcc(self):
        raw = "<p>Hola mundo</p><pre><code>print(123)</code></pre><ul><li>Item 1</li></ul>"
        limpio = freecodecamp._limpiar_html_fcc(raw)
        self.assertIn("Hola mundo", limpio)
        self.assertIn("```\nprint(123)\n```", limpio)
        self.assertIn("• Item 1", limpio)

    def test_listar_certificaciones(self):
        certs = freecodecamp.listar_certificaciones()
        self.assertGreater(len(certs), 5)
        ids = [c["id"] for c in certs]
        self.assertIn("scientific-computing-with-python", ids)
        self.assertIn("data-analysis-with-python", ids)

    @mock.patch("appstudy.freecodecamp._peticion_http")
    def test_obtener_leccion_desde_page_data(self, mock_http):
        payload = {
            "result": {
                "data": {
                    "challengeNode": {
                        "challenge": {
                            "title": "Build a Cipher",
                            "block": "python-basics",
                            "superBlock": "scientific-computing-with-python",
                            "description": "<p>Learn how variables work in Python.</p>",
                            "instructions": "<p>Create a variable named text.</p>",
                            "tests": [{"text": "text should exist"}]
                        }
                    }
                }
            }
        }
        mock_http.return_value = json.dumps(payload).encode("utf-8")

        leccion = freecodecamp.obtener_leccion(
            "https://www.freecodecamp.org/learn/scientific-computing-with-python/build-a-cipher/step-1"
        )
        self.assertEqual(leccion["titulo"], "Build a Cipher")
        self.assertEqual(leccion["bloque"], "python-basics")
        self.assertIn("Learn how variables work", leccion["descripcion"])
        self.assertIn("Create a variable named text", leccion["instrucciones"])
        self.assertIn("text should exist", leccion["texto_para_ia"])

    @mock.patch("appstudy.ia._mensaje")
    def test_generar_tarjetas_fcc(self, mock_ia_mensaje):
        cfg = {"activa": True, "url": "http://localhost:11434", "modelo": "gemma"}
        leccion = {
            "titulo": "Variables en Python",
            "bloque": "fundamentos",
            "texto_para_ia": "Las variables guardan referencias a objetos.",
            "fuente": "https://www.freecodecamp.org/learn/python/step-1"
        }
        mock_ia_mensaje.return_value = json.dumps({
            "tarjetas": [
                {"front": "¿Qué es una variable?", "back": "Una referencia a un objeto."}
            ]
        })

        tarjetas = freecodecamp.generar_tarjetas_fcc(cfg, leccion, cuantas=1)
        self.assertEqual(len(tarjetas), 1)
        self.assertEqual(tarjetas[0]["front"], "¿Qué es una variable?")
        self.assertIn("freecodecamp", tarjetas[0]["tags"])

    def test_generar_tarjetas_con_ia_desactivada_lanza_error(self):
        cfg = {"activa": False}
        leccion = {"titulo": "Test", "bloque": "test", "texto_para_ia": "Contenido"}
        with self.assertRaises(freecodecamp.FCCError):
            freecodecamp.generar_tarjetas_fcc(cfg, leccion)

    def test_leccion_a_markdown(self):
        leccion = {
            "titulo": "Variables en Python",
            "bloque": "python-basics",
            "descripcion": "Una variable guarda un valor.\n\n```\nx = 10\n```",
            "instrucciones": "Asigna 20 a y.",
            "fuente": "https://www.freecodecamp.org/learn/python/step-1"
        }
        md = freecodecamp.leccion_a_markdown(leccion, deck_key="python", nivel=1)
        self.assertIn("mazo: python", md)
        self.assertIn("nivel: 1", md)
        self.assertIn("# Variables en Python", md)
        self.assertIn("```\nx = 10\n```", md)
        self.assertIn("## Instrucciones y Desafío", md)
        self.assertIn("Asigna 20 a y.", md)


if __name__ == "__main__":
    unittest.main()
