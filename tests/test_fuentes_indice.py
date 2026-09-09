"""Las fuentes sin buscador se recorren por su índice, y el índice se cachea.

El sitemap de LibreTexts pesa más de 3 MB: bajarlo en cada arranque sería
maltratar la fuente y la conexión del usuario.
"""
import json
import time

from appstudy import catalogo, db, fuentes
from tests.apoyo import BaseTemporal

SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://workforce.libretexts.org/Bookshelves/Automotive/Brakes</loc></url>
<url><loc>https://workforce.libretexts.org/Bookshelves/Automotive/Engines</loc></url>
<url><loc>https://workforce.libretexts.org/Special:Search</loc></url>
<url><loc>https://otrositio.example/malo</loc></url>
</urlset>"""

INDICE_HTML = b"""<html><body><main>
<a href="/linux/man-pages/man1/ls.1.html">ls(1)</a>
<a href="/linux/man-pages/man2/open.2.html">open(2)</a>
<a href="https://otrositio.example/x">fuera de la lista blanca</a>
<a href="/linux/man-pages/index.html">indice</a>
</main></body></html>"""


class IndiceTest(BaseTemporal):
    def grabar(self, cuerpo, tipo="application/xml"):
        original = fuentes.descargar
        self.pedidas = []

        def falso(url, dominios, limite=None):
            self.pedidas.append(url)
            return cuerpo, tipo
        fuentes.descargar = falso
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))

    def test_el_sitemap_da_paginas_y_descarta_las_de_servicio(self):
        self.grabar(SITEMAP)
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"))
        self.assertEqual([x["title"] for x in r], ["Brakes", "Engines"])
        self.assertTrue(self.pedidas[0].endswith("/sitemap.xml"))

    def test_una_url_de_otro_dominio_no_entra(self):
        self.grabar(SITEMAP)
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"))
        self.assertTrue(all("libretexts.org" in x["origin"] for x in r))

    def test_una_pagina_indice_html_da_sus_enlaces(self):
        self.grabar(INDICE_HTML, "text/html")
        r = fuentes.indice(catalogo.por_id("man7"))
        self.assertEqual([x["title"] for x in r], ["ls(1)", "open(2)"])
        self.assertEqual(r[0]["origin"], "https://man7.org/linux/man-pages/man1/ls.1.html")

    def test_la_consulta_filtra_por_titulo(self):
        self.grabar(SITEMAP)
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"), "brakes")
        self.assertEqual(len(r), 1)

    def test_el_indice_se_cachea_y_no_se_vuelve_a_descargar(self):
        self.grabar(SITEMAP)
        f = catalogo.por_id("libretexts_workforce")
        fuentes.indice(f)
        fuentes.indice(f)
        self.assertEqual(len(self.pedidas), 1, "el índice se descargó dos veces")

    def test_un_indice_caducado_se_vuelve_a_pedir(self):
        self.grabar(SITEMAP)
        f = catalogo.por_id("libretexts_workforce")
        fuentes.indice(f)
        ruta = db.DATA_DIR / "fuentes" / "indices" / "libretexts_workforce.json"
        datos = json.loads(ruta.read_text())
        datos["ts"] = time.time() - fuentes.CADUCIDAD_INDICE - 1
        ruta.write_text(json.dumps(datos))
        fuentes.indice(f)
        self.assertEqual(len(self.pedidas), 2)

    def test_si_la_descarga_falla_se_usa_la_copia_guardada(self):
        self.grabar(SITEMAP)
        f = catalogo.por_id("libretexts_workforce")
        fuentes.indice(f)

        def revienta(url, dominios, limite=None):
            raise fuentes.FuenteError("sin conexión")
        fuentes.descargar = revienta
        r = fuentes.indice(f, refrescar=True)
        self.assertEqual(len(r), 2, "sin red debería servir la copia guardada")

    def test_sin_copia_y_sin_red_se_propaga_el_error(self):
        original = fuentes.descargar

        def revienta(url, dominios, limite=None):
            raise fuentes.FuenteError("sin conexión")
        fuentes.descargar = revienta
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))
        with self.assertRaises(fuentes.FuenteError):
            fuentes.indice(catalogo.por_id("libretexts_eng"))
