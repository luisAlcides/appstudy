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


INDICE_DE_SITEMAPS = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://espanol.libretexts.org/sitemap0.xml</loc></sitemap>
</sitemapindex>"""

HOJA = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://espanol.libretexts.org/Matematicas/Derivadas</loc></url>
</urlset>"""

CON_NAVEGACION = b"""<html><body><main>
<a href="/a.html">Skip to main content</a>
<a href="/e.html">Skip to main Navigation</a>
<a href="/b.html">Sign Up</a>
<a href="/c.html">Chapter 2: OHM'S LAW</a>
<a href="/d.html">ok</a>
</main></body></html>"""


class SitemapIndiceTest(BaseTemporal):
    def test_un_indice_de_sitemaps_se_sigue_un_nivel(self):
        original = fuentes.descargar
        respuestas = [INDICE_DE_SITEMAPS, HOJA]

        def falso(url, dominios, limite=None):
            return respuestas.pop(0), "application/xml"
        fuentes.descargar = falso
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))
        r = fuentes.indice(catalogo.por_id("libretexts_esp"))
        self.assertEqual([x["title"] for x in r], ["Derivadas"])

    def test_los_enlaces_de_navegacion_no_entran(self):
        original = fuentes.descargar
        fuentes.descargar = lambda u, d, limite=None: (CON_NAVEGACION, "text/html")
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))
        r = fuentes.indice(catalogo.por_id("ibiblio"))
        self.assertEqual([x["title"] for x in r], ["Chapter 2: OHM'S LAW"])


class FiltroIndiceTest(BaseTemporal):
    def preparar(self):
        original = fuentes.descargar
        fuentes.descargar = lambda u, d, limite=None: (SITEMAP, "application/xml")
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))

    def test_basta_con_que_coincida_un_termino(self):
        self.preparar()
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"), "brakes hidraulica")
        self.assertEqual([x["title"] for x in r], ["Brakes"])

    def test_lo_que_coincide_en_mas_terminos_va_primero(self):
        self.preparar()
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"), "engines brakes")
        self.assertEqual(len(r), 2)

    def test_si_no_coincide_nada_no_se_devuelve_todo(self):
        self.preparar()
        self.assertEqual(fuentes.indice(catalogo.por_id("libretexts_workforce"), "cocina"), [])
