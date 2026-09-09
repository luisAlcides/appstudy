"""El rig: componer las capas y cerrar los ojos de verdad.

La comprobación de que un ojo está cerrado no se hace mirando, se hace
contando: cuántos píxeles del hueco del ojo siguen clasificándose como ojo.
"""
import cairo

from appstudy import capas_chispa as capas
from appstudy import rig_chispa
from tests.apoyo import BaseTemporal


class RigVacioTest(BaseTemporal):
    def test_sin_capas_no_hay_rig_y_no_revienta(self):
        self.assertIsNone(rig_chispa.cargar())

    def test_un_manifiesto_de_otra_version_se_rechaza(self):
        carpeta = capas.carpeta()
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "manifiesto.json").write_text(
            '{"version": "vieja", "atlas": "x", "poses": {}}', encoding="utf-8")
        self.assertIsNone(rig_chispa.cargar())

    def test_un_manifiesto_ilegible_se_rechaza(self):
        carpeta = capas.carpeta()
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "manifiesto.json").write_text("{roto", encoding="utf-8")
        self.assertIsNone(rig_chispa.cargar())


class RigTest(BaseTemporal):
    @classmethod
    def setUpClass(cls):
        from appstudy.chispa import cargar_poses
        if cargar_poses() is None:
            raise unittest.SkipTest("Requiere el atlas de Chispa")

    def setUp(self):
        super().setUp()
        capas.extraer()
        self.rig = rig_chispa.cargar()
        self.assertIsNotNone(self.rig, "las capas recién extraídas deben cargar")

    def pintar(self, indice, cierre):
        from appstudy.chispa import cargar_poses
        celda = cargar_poses()[indice]
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                               celda.get_width(), celda.get_height())
        cr = cairo.Context(s)
        self.assertTrue(self.rig.dibujar(cr, indice, cierre))
        s.flush()
        return s

    def hueco_del_ojo(self, indice):
        p = self.rig.piezas(indice)
        celda_w = self.pintar(indice, 0.0).get_width()
        pixeles = set()
        for clave in ("ojo_izq", "ojo_der"):
            x0, y0, x1, y1 = p[clave]["caja"]
            for y in range(int(y0 * celda_w), int(y1 * celda_w)):
                for x in range(int(x0 * celda_w), int(x1 * celda_w)):
                    pixeles.add(y * celda_w + x)
        return pixeles

    def test_con_los_ojos_abiertos_el_ojo_esta_a_la_vista(self):
        hueco = self.hueco_del_ojo(0)
        abierto = capas.contar_color(self.pintar(0, 0.0), hueco, "ojo")
        self.assertGreater(abierto, 500)

    def test_al_cerrarse_desaparece_el_ojo(self):
        hueco = self.hueco_del_ojo(0)
        abierto = capas.contar_color(self.pintar(0, 0.0), hueco, "ojo")
        cerrado = capas.contar_color(self.pintar(0, 1.0), hueco, "ojo")
        self.assertLess(cerrado, abierto * 0.25,
                        "con el párpado abajo no puede seguir viéndose el ojo")

    def test_a_medio_cerrar_se_ve_menos_que_abierto_y_mas_que_cerrado(self):
        hueco = self.hueco_del_ojo(0)
        cuenta = [capas.contar_color(self.pintar(0, c), hueco, "ojo")
                  for c in (0.0, 0.5, 1.0)]
        self.assertGreater(cuenta[0], cuenta[1])
        self.assertGreater(cuenta[1], cuenta[2])

    def test_las_poses_con_los_ojos_ya_cerrados_no_parpadean(self):
        for indice in (3, 5):
            with self.subTest(pose=indice):
                self.assertFalse(self.rig.parpadea(indice))

    def test_las_demas_si_parpadean(self):
        for indice in (0, 1, 2, 4):
            with self.subTest(pose=indice):
                self.assertTrue(self.rig.parpadea(indice))

    def test_si_falta_una_capa_el_rig_lo_dice_en_vez_de_dibujar_a_medias(self):
        (capas.carpeta() / "0-ojo_izq.png").unlink()
        rig = rig_chispa.cargar()
        rig._cache.clear()
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
        self.assertFalse(rig.dibujar(cairo.Context(s), 0, 0.0))


import unittest  # noqa: E402  (lo usa setUpClass para saltar)


class ChispaConCapasTest(BaseTemporal):
    """El enganche: con capas parpadea, y sin ellas se dibuja como siempre."""

    def bicho(self):
        from appstudy.chispa import Chispa
        c = Chispa()
        self.addCleanup(c.unparent)
        return c

    def test_sin_capas_no_hay_rig_y_se_dibuja_igual(self):
        c = self.bicho()
        self.assertIsNone(c._rig())
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 228, 246)
        c.draw(None, cairo.Context(s), 228, 246)      # no debe lanzar

    def test_el_parpadeo_vale_cero_casi_siempre_y_uno_a_veces(self):
        c = self.bicho()
        valores = []
        for n in range(4000):
            c.t = n / 100
            valores.append(c._cierre_parpadeo())
        self.assertEqual(min(valores), 0.0)
        self.assertGreater(max(valores), 0.9, "alguna vez tiene que cerrarse")
        abiertos = sum(1 for v in valores if v == 0.0)
        self.assertGreater(abiertos / len(valores), 0.9,
                           "parpadear no puede ser el estado normal")

    def test_con_movimiento_reducido_no_parpadea(self):
        c = self.bicho()
        c.reduced_motion = True
        for n in range(500):
            c.t = n / 50
            self.assertEqual(c._cierre_parpadeo(), 0.0)

    def test_con_capas_se_dibuja_por_capas(self):
        from appstudy.chispa import cargar_poses
        if cargar_poses() is None:
            self.skipTest("Requiere el atlas de Chispa")
        capas.extraer()
        c = self.bicho()
        self.assertIsNotNone(c._rig())
        self.assertTrue(c._rig().parpadea(0))
