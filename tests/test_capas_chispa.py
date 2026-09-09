"""El extractor de capas de Chispa.

Lo que se protege aquí es que las piezas se *encuentren*, no se estimen: un
intento anterior situaba un ojo 22 píxeles más abajo de donde está, y el
párpado se pintaba sobre el ojo abierto.
"""
import unittest

import cairo

from appstudy import capas_chispa as capas


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
