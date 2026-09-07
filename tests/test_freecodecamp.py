"""Pruebas unitarias para el módulo de integración con freeCodeCamp."""
import json
import unittest
from unittest import mock

from appstudy import freecodecamp

from .apoyo import BaseTemporal


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


def _indice_falso():
    """Un índice del currículo como el que publica freeCodeCamp, en pequeño."""
    def nodo(sb, bloque, titulo, dashed, orden):
        return {"challenge": {
            "fields": {"slug": f"/learn/{sb}/{bloque}/{dashed}"},
            "block": bloque, "title": titulo, "order": orden, "superBlock": sb,
            "dashedName": dashed}}
    return {"result": {"data": {"allChallengeNode": {"nodes": [
        nodo("python-v9", "bloque-b", "Step 1", "step-1", 1),
        nodo("python-v9", "bloque-a", "Step 1", "step-1", 0),
        nodo("python-v9", "bloque-a", "Step 2", "step-2", 0),
        nodo("javascript-v9", "bloque-js", "Step 1", "step-1", 0),
        {"challenge": {"block": "sin-slug", "superBlock": "python-v9"}},
    ]}}}}


class TestCatalogoFCC(BaseTemporal):
    """El catálogo de cursos: descarga, reparto por curso y caché en disco."""

    def setUp(self):
        super().setUp()
        self.parche = mock.patch(
            "appstudy.freecodecamp._peticion_http",
            return_value=json.dumps(_indice_falso()).encode("utf-8"))
        self.peticion = self.parche.start()
        self.addCleanup(self.parche.stop)

    def test_catalogo_agrupa_bloques_y_ordena(self):
        cat = freecodecamp.catalogo("python-v9")
        self.assertEqual([b["block"] for b in cat["bloques"]], ["bloque-a", "bloque-b"])
        self.assertEqual(cat["lecciones"], 3)
        self.assertEqual(cat["bloques"][0]["titulo"], "Bloque A")
        self.assertEqual([l["titulo"] for l in cat["bloques"][0]["lecciones"]],
                         ["Step 1", "Step 2"])
        self.assertEqual(cat["bloques"][0]["lecciones"][0]["url"],
                         "https://www.freecodecamp.org/learn/python-v9/bloque-a/step-1")

    def test_una_sola_descarga_reparte_todos_los_cursos(self):
        freecodecamp.catalogo("python-v9")
        freecodecamp.catalogo("javascript-v9")
        self.assertEqual(self.peticion.call_count, 1)
        self.assertEqual(freecodecamp.catalogo_en_cache("javascript-v9")["lecciones"], 1)

    def test_catalogo_en_cache_sin_descargar(self):
        self.assertIsNone(freecodecamp.catalogo_en_cache("python-v9"))
        freecodecamp.catalogo("python-v9")
        self.assertIsNotNone(freecodecamp.catalogo_en_cache("python-v9"))

    def test_refrescar_vuelve_a_descargar(self):
        freecodecamp.catalogo("python-v9")
        freecodecamp.catalogo("python-v9", refrescar=True)
        self.assertEqual(self.peticion.call_count, 2)

    def test_curso_inexistente_avisa(self):
        with self.assertRaises(freecodecamp.FCCError):
            freecodecamp.catalogo("curso-que-no-existe")


class TestRutasFCC(unittest.TestCase):

    def test_superblock_bloque_y_ruta(self):
        url = "https://www.freecodecamp.org/learn/python-v9/bloque-a/step-1"
        self.assertEqual(freecodecamp.superblock_de(url), "python-v9")
        self.assertEqual(freecodecamp.bloque_de(url), "bloque-a")
        self.assertEqual(freecodecamp.ruta_de(url), "/learn/python-v9/bloque-a/step-1")

    def test_superblock_con_año_en_la_ruta(self):
        url = "https://www.freecodecamp.org/learn/2022/responsive-web-design/cafe/step-1"
        self.assertEqual(freecodecamp.superblock_de(url), "2022/responsive-web-design")

    def test_url_ajena_no_da_curso(self):
        self.assertEqual(freecodecamp.superblock_de("https://ejemplo.com/learn/x"), "")
        self.assertEqual(freecodecamp.ruta_de("https://www.freecodecamp.org/news/algo"), "")

    def test_nombre_curso_conocido_y_desconocido(self):
        self.assertEqual(freecodecamp.nombre_curso("python-v9"), "Python desde cero")
        self.assertEqual(freecodecamp.nombre_curso("algo-nuevo"), "Algo Nuevo")


class TestAvanceFCC(BaseTemporal):
    """El avance del currículo se guarda en la base de AppStudy."""

    def test_visitar_y_completar(self):
        from appstudy import db as base
        ruta = "/learn/python-v9/bloque-a/step-1"
        base.fcc_marcar(self.con, "python-v9", "bloque-a", ruta, "Step 1")
        self.assertEqual(base.fcc_hechas(self.con, "python-v9")[ruta]["hecho"], 0)

        base.fcc_marcar(self.con, "python-v9", "bloque-a", ruta, "", hecho=True)
        self.assertEqual(base.fcc_hechas(self.con, "python-v9")[ruta]["hecho"], 1)
        self.assertEqual(base.fcc_hechas(self.con, "python-v9")[ruta]["title"], "Step 1")

    def test_revisitar_no_desmarca(self):
        from appstudy import db as base
        ruta = "/learn/python-v9/bloque-a/step-1"
        base.fcc_marcar(self.con, "python-v9", "bloque-a", ruta, "Step 1", hecho=True)
        base.fcc_marcar(self.con, "python-v9", "bloque-a", ruta, "Step 1")
        self.assertEqual(base.fcc_hechas(self.con, "python-v9")[ruta]["hecho"], 1)

    def test_resumen_y_ultima(self):
        from appstudy import db as base
        base.fcc_marcar(self.con, "python-v9", "b", "/learn/python-v9/b/s1", "S1", hecho=True)
        base.fcc_marcar(self.con, "python-v9", "b", "/learn/python-v9/b/s2", "S2")
        base.fcc_marcar(self.con, "javascript-v9", "j", "/learn/javascript-v9/j/s1", "J1")
        resumen = base.fcc_resumen(self.con)
        self.assertEqual(resumen["python-v9"], {"hechas": 1, "vistas": 2})
        self.assertEqual(base.fcc_ultima(self.con)["superblock"], "javascript-v9")
        self.assertEqual(base.fcc_ultima(self.con, "python-v9")["title"], "S2")

    def test_slug_vacio_no_guarda_nada(self):
        from appstudy import db as base
        base.fcc_marcar(self.con, "python-v9", "b", "  ", "Sin ruta")
        self.assertEqual(base.fcc_hechas(self.con), {})


if __name__ == "__main__":
    unittest.main()
