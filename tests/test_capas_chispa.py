"""El extractor de capas de Chispa.

Lo que se protege aquí es que las piezas se *encuentren*, no se estimen: un
intento anterior situaba un ojo 22 píxeles más abajo de donde está, y el
párpado se pintaba sobre el ojo abierto.
"""
import unittest

import cairo

from appstudy import capas_chispa as capas
from tests.apoyo import BaseTemporal


class ClasificarTest(unittest.TestCase):
    def test_cada_color_de_la_paleta_se_reconoce_a_si_mismo(self):
        for nombre, refs in capas.PALETA.items():
            for r, g, b in refs:
                with self.subTest(nombre, color=(r, g, b)):
                    self.assertEqual(capas.clasificar(r, g, b), nombre)

    def test_un_naranja_algo_apagado_sigue_siendo_naranja(self):
        self.assertEqual(capas.clasificar(0xE0, 0x80, 0x36), "naranja")

    def test_el_blanco_del_ojo_no_se_confunde_con_la_crema_del_hocico(self):
        self.assertEqual(capas.clasificar(255, 255, 255), "ojo")
        self.assertEqual(capas.clasificar(0xFB, 0xF3, 0xE6), "crema")

    def test_el_pardo_de_las_manoplas_no_es_el_marron_del_iris(self):
        self.assertEqual(capas.clasificar(0x48, 0x32, 0x24), "pardo")


class GruposTest(unittest.TestCase):
    def lienzo(self, manchas, lado=64, color=(1, 1, 1)):
        """Un atlas de mentira: cuadrados blancos sobre fondo naranja."""
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, lado, lado)
        cr = cairo.Context(s)
        cr.set_source_rgb(*[v / 255 for v in capas.PALETA["naranja"][1]])
        cr.paint()
        cr.set_source_rgb(*color)
        for x, y, w, h in manchas:
            cr.rectangle(x, y, w, h)
            cr.fill()
        s.flush()
        return s

    def test_dos_manchas_separadas_dan_dos_grupos(self):
        s = self.lienzo([(6, 6, 14, 14), (40, 6, 14, 14)])
        self.assertEqual(len(capas.grupos(s, {"ojo"}, minimo=20)), 2)

    def test_una_mancha_pegada_es_un_solo_grupo(self):
        s = self.lienzo([(6, 6, 14, 14), (20, 6, 14, 14)])
        self.assertEqual(len(capas.grupos(s, {"ojo"}, minimo=20)), 1)

    def test_el_grupo_sabe_donde_esta_y_cuanto_ocupa(self):
        s = self.lienzo([(16, 32, 16, 16)])
        g = capas.grupos(s, {"ojo"}, minimo=20)[0]
        self.assertAlmostEqual(g["centro"][0], 24 / 64, places=2)
        self.assertAlmostEqual(g["centro"][1], 40 / 64, places=2)
        self.assertEqual(g["n"], 16 * 16)
        self.assertEqual(g["color"], "ojo")

    def test_lo_demasiado_pequeño_se_descarta(self):
        s = self.lienzo([(6, 6, 2, 2)])
        self.assertEqual(capas.grupos(s, {"ojo"}, minimo=20), [])

    def test_solo_se_buscan_los_colores_pedidos(self):
        s = self.lienzo([(6, 6, 14, 14)])
        self.assertEqual(capas.grupos(s, {"turquesa"}, minimo=20), [])

    def test_lo_transparente_no_cuenta(self):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
        self.assertEqual(capas.grupos(s, set(PALETA_TODA), minimo=1), [])


PALETA_TODA = tuple(capas.PALETA)


class PiezasTest(unittest.TestCase):
    """Sobre el atlas de verdad: es donde importa que las reglas acierten."""

    @classmethod
    def setUpClass(cls):
        from appstudy.chispa import cargar_poses
        cls.poses = cargar_poses()
        if cls.poses is None:
            raise unittest.SkipTest("Requiere el atlas de Chispa")
        cls.encontradas = [capas.piezas(s, i) for i, s in enumerate(cls.poses)]

    def test_las_poses_con_los_ojos_abiertos_dan_dos_ojos(self):
        for indice in (0, 1, 2, 4):
            with self.subTest(pose=indice):
                p = self.encontradas[indice]
                self.assertIn("ojo_izq", p)
                self.assertIn("ojo_der", p)

    def test_las_poses_con_los_ojos_ya_cerrados_no_dan_capa_de_ojo(self):
        for indice in (3, 5):
            with self.subTest(pose=indice):
                self.assertNotIn("ojo_izq", self.encontradas[indice])

    def test_los_ojos_estan_arriba_y_separados(self):
        for indice in (0, 1, 2, 4):
            p = self.encontradas[indice]
            izq = capas.caja_de(self.poses[indice], p["ojo_izq"])
            der = capas.caja_de(self.poses[indice], p["ojo_der"])
            with self.subTest(pose=indice):
                self.assertLess((izq[1] + izq[3]) / 2, 0.62)
                self.assertLess(izq[2], der[2], "izquierdo debe quedar a la izquierda")
                self.assertGreater(der[0] - izq[0], 0.08)

    def test_ninguna_pieza_es_una_oreja(self):
        """Las orejas son anchas; los ojos, casi cuadrados."""
        for indice in (0, 1, 2, 4):
            for clave in ("ojo_izq", "ojo_der"):
                x0, y0, x1, y1 = capas.caja_de(self.poses[indice],
                                               self.encontradas[indice][clave])
                with self.subTest(pose=indice, pieza=clave):
                    self.assertLessEqual((x1 - x0) / (y1 - y0), 1.6)


class ReconstruirTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        from appstudy.chispa import cargar_poses
        self.poses = cargar_poses()
        if self.poses is None:
            self.skipTest("Requiere el atlas de Chispa")

    def test_detras_del_ojo_no_queda_ojo_visible(self):
        """No basta contar píxeles sueltos: lo que importa es que no quede mancha.

        Algunos píxeles del pelaje se clasifican como «ojo» sin serlo —el
        naranja oscuro se parece al iris y los brillos al blanco del ojo—, así
        que se exige que no quede ningún grupo lo bastante grande para verse.
        """
        p = capas.piezas(self.poses[0], 0)
        todos = p["ojo_izq"] | p["ojo_der"]
        base = capas.reconstruir(self.poses[0], todos)
        antes = capas.contar_color(self.poses[0], todos, "ojo")
        despues = capas.contar_color(base, todos, "ojo")
        self.assertLess(despues, antes * 0.10, "el ojo sigue ahí")
        grandes = [g for g in capas.grupos(base, {"ojo"}, capas.OJO_MIN)
                   if g["pixeles"] & todos]
        self.assertEqual(grandes, [], "queda una mancha de ojo a la vista")

    def test_la_reconstruccion_deja_pelaje_no_un_agujero(self):
        p = capas.piezas(self.poses[0], 0)
        base = capas.reconstruir(self.poses[0], p["ojo_izq"])
        base.flush()
        datos = base.get_data()
        ancho, paso = base.get_width(), base.get_stride()
        opacos = 0
        for i in p["ojo_izq"]:
            y, x = divmod(i, ancho)
            if datos[y * paso + x * 4 + 3] > 200:
                opacos += 1
        self.assertEqual(opacos, len(p["ojo_izq"]), "quedaron huecos transparentes")

    def test_la_capa_recortada_conserva_el_ojo(self):
        p = capas.piezas(self.poses[0], 0)
        capa = capas.recortar(self.poses[0], p["ojo_izq"])
        self.assertGreater(capas.contar_color(capa, p["ojo_izq"], "ojo"), 100)

    def test_extraer_deja_manifiesto_y_archivos(self):
        m = capas.extraer()
        self.assertEqual(m["version"], capas.VERSION)
        self.assertTrue(m["atlas"])
        self.assertTrue((capas.carpeta() / "base-0.png").exists())
        self.assertTrue((capas.carpeta() / "0-ojo_izq.png").exists())
        self.assertTrue((capas.carpeta() / "0-ojo_der.png").exists())
        self.assertFalse((capas.carpeta() / "3-ojo_izq.png").exists())
        # La pose de reposo saca las seis piezas: dos ojos, dos manos, dos pies
        self.assertEqual(sorted(m["poses"]["0"]),
                         ["mano_der", "mano_izq", "ojo_der", "ojo_izq",
                          "pie_der", "pie_izq"])
        # La de celebrar ya viene con los ojos cerrados y las manos en alto
        self.assertNotIn("ojo_izq", m["poses"]["3"])
        self.assertNotIn("mano_izq", m["poses"]["3"])
        # La dormida es un ovillo: no hay nada que separar
        self.assertEqual(m["poses"]["5"], {})
