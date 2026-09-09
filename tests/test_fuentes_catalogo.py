"""Los buscadores de las fuentes nuevas, con respuestas grabadas.

Las respuestas imitan la forma real de cada API, comprobada el 2026-09-09.
Ninguna prueba sale a la red.
"""
import json
import unittest

from appstudy import fuentes


class BuscadoresTest(unittest.TestCase):
    def grabar(self, cuerpo, tipo="application/json"):
        original = fuentes.descargar
        self.pedidas = []

        def falso(url, dominios, limite=None):
            self.pedidas.append(url)
            return cuerpo, tipo
        fuentes.descargar = falso
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))

    def test_mediawiki_sirve_para_cualquier_host_del_catalogo(self):
        self.grabar(json.dumps({"pages": [
            {"key": "Systemd", "title": "systemd",
             "excerpt": "gestor de <b>servicios</b>"}]}).encode())
        r = fuentes.buscar("archwiki", "systemd")
        self.assertEqual(r[0]["title"], "systemd")
        self.assertEqual(r[0]["origin"], "https://wiki.archlinux.org/title/Systemd")
        self.assertIn("gestor de servicios", r[0]["summary"])

    def test_wikimedia_usa_la_ruta_larga(self):
        self.grabar(json.dumps({"pages": [{"key": "Ohm", "title": "Ohm", "excerpt": ""}]}).encode())
        r = fuentes.buscar("wikibooks_es", "ohm")
        self.assertEqual(r[0]["origin"], "https://es.wikibooks.org/wiki/Ohm")
        self.assertIn("/w/rest.php/v1/search/page", self.pedidas[0])

    def test_arxiv_lee_el_atom_y_se_queda_con_el_resumen(self):
        self.grabar(b"""<?xml version='1.0' encoding='UTF-8'?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry><id>https://arxiv.org/abs/2401.00001v1</id>
                <title>Retrieval Augmented Generation</title>
                <summary>Un resumen de prueba.</summary>
                <author><name>A. Autora</name></author></entry>
            </feed>""", "application/atom+xml")
        r = fuentes.buscar("arxiv", "rag")
        self.assertEqual(r[0]["title"], "Retrieval Augmented Generation")
        self.assertEqual(r[0]["origin"], "https://arxiv.org/abs/2401.00001v1")
        self.assertIn("resumen de prueba", r[0]["summary"])
        self.assertEqual(r[0]["author"], "A. Autora")

    def test_mdn_devuelve_la_url_absoluta(self):
        self.grabar(json.dumps({"documents": [
            {"mdn_url": "/es/docs/Web/API/fetch", "title": "fetch()",
             "summary": "Hace una petición"}]}).encode())
        r = fuentes.buscar("mdn", "fetch")
        self.assertEqual(r[0]["origin"], "https://developer.mozilla.org/es/docs/Web/API/fetch")

    def test_gutendex_solo_devuelve_libros_con_texto_plano(self):
        self.grabar(json.dumps({"results": [
            {"title": "Hard Times", "authors": [{"name": "Dickens, Charles"}],
             "formats": {"text/plain; charset=utf-8":
                         "https://www.gutenberg.org/ebooks/786.txt.utf-8"}},
            {"title": "Solo imagen", "authors": [], "formats": {"image/jpeg": "x"}}]}).encode())
        r = fuentes.buscar("gutenberg", "dickens")
        self.assertEqual([x["title"] for x in r], ["Hard Times"])
        self.assertEqual(r[0]["author"], "Dickens, Charles")

    def test_una_respuesta_ilegible_da_un_error_de_fuente(self):
        self.grabar(b"esto no es json")
        with self.assertRaises(fuentes.FuenteError):
            fuentes.buscar("wikipedia_es", "ohm")

    def test_un_atom_roto_da_un_error_de_fuente(self):
        self.grabar(b"<feed><entry>", "application/atom+xml")
        with self.assertRaises(fuentes.FuenteError):
            fuentes.buscar("arxiv", "rag")

    def test_una_consulta_vacia_no_pide_nada(self):
        self.grabar(b"{}")
        self.assertEqual(fuentes.buscar("wikipedia_es", "   "), [])
        self.assertEqual(self.pedidas, [])

    def test_los_proveedores_de_siempre_siguen_funcionando(self):
        self.grabar(json.dumps({"pages": [{"key": "Ohm", "title": "Ohm", "excerpt": ""}]}).encode())
        r = fuentes.buscar("wikipedia", "ohm", {"idioma": "es"})
        self.assertEqual(r[0]["origin"], "https://es.wikipedia.org/wiki/Ohm")
