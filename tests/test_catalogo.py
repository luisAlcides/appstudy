"""El catálogo son datos: se comprueba que estén bien declarados.

Una errata en un host o en una clave de mazo rompería la cosecha en silencio,
y estas comprobaciones son baratas.
"""
import unittest

from appstudy import catalogo, fuentes

MAZOS = {"ingles", "linux", "datos", "ia", "matematicas",
         "electricidad", "python", "automotriz", "maquinaria"}


class CatalogoTest(unittest.TestCase):
    def test_cada_fuente_esta_bien_declarada(self):
        for f in catalogo.FUENTES:
            with self.subTest(f["id"]):
                self.assertTrue(f["hosts"], "sin hosts")
                self.assertIn(f["tipo"], ("buscador", "indice", "catalogo"))
                self.assertIn(f["licencia"], ("abierta", "solo-enlace"))
                self.assertTrue(f["nombre"].strip())
                self.assertTrue(f["base"].startswith("https://"))
                self.assertTrue(f["mazos"], "no sirve a ningún mazo")
                self.assertLessEqual(set(f["mazos"]), MAZOS)

    def test_los_identificadores_no_se_repiten(self):
        ids = [f["id"] for f in catalogo.FUENTES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_el_host_de_la_base_esta_entre_los_hosts_declarados(self):
        import urllib.parse
        for f in catalogo.FUENTES:
            with self.subTest(f["id"]):
                self.assertIn(urllib.parse.urlsplit(f["base"]).hostname, f["hosts"])

    def test_todos_los_hosts_estan_en_la_lista_blanca_de_fuentes(self):
        permitidos = set().union(*fuentes.DOMINIOS.values())
        self.assertLessEqual(catalogo.hosts(), permitidos)

    def test_cada_mazo_tiene_al_menos_una_fuente(self):
        for mazo in MAZOS:
            with self.subTest(mazo):
                self.assertTrue(catalogo.fuentes_de(mazo))

    def test_filtrar_por_nivel_respeta_lo_declarado(self):
        ids = {f["id"] for f in catalogo.fuentes_de("ingles", "A2")}
        self.assertIn("wikipedia_simple", ids)
        self.assertNotIn("wikipedia_en", ids)

    def test_arxiv_es_solo_enlace_y_wikipedia_abierta(self):
        self.assertFalse(catalogo.abierta("arxiv"))
        self.assertTrue(catalogo.abierta("wikipedia_es"))
