"""Extremidades articuladas: quietud accesible y textura sin cortes."""
import unittest

import cairo

from appstudy import animacion_chispa as animacion
from appstudy.chispa import cargar_poses


class ExtremidadesTest(unittest.TestCase):
    def test_descanso_y_movimiento_reducido_no_deforman(self):
        for instante in (0, .1, 1, 30):
            self.assertEqual(animacion.movimientos(5, instante), ())
            for pose in range(6):
                self.assertEqual(animacion.movimientos(pose, instante, 0), ())

    def test_manos_y_pies_se_mueven_sin_arrastrar_la_cabeza(self):
        for pose in range(5):
            antes = animacion.movimientos(pose, .2)
            despues = animacion.movimientos(pose, .7)
            for x, y in animacion.ANCLAJES[pose]:
                self.assertNotEqual(animacion.desplazar(x, y, antes),
                                    animacion.desplazar(x, y, despues))
            self.assertEqual(animacion.desplazar(.60, .10, antes), (.60, .10))

    def test_la_malla_no_invierte_triangulos(self):
        # Un triángulo invertido dobla la textura sobre sí misma.
        for pose in range(5):
            for tiempo in (0, .11, .28, .43, .71, 1.2):
                gestos = animacion.movimientos(pose, tiempo)
                for y in range(24):
                    for x in range(24):
                        puntos = [animacion.desplazar(a/24, b/24, gestos)
                                  for a,b in ((x,y),(x+1,y),(x+1,y+1),(x,y+1))]
                        for a,b,c in ((puntos[0],puntos[1],puntos[2]),
                                      (puntos[0],puntos[2],puntos[3])):
                            area = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                            self.assertGreater(area, 0)

    def test_el_render_mueve_las_extremidades_y_conserva_la_cara(self):
        sprite = cargar_poses()[0]
        resultados = []
        for tiempo in (.2, .7):
            s = cairo.ImageSurface(cairo.FORMAT_ARGB32,512,512)
            animacion.pintar(cairo.Context(s),sprite,animacion.movimientos(0,tiempo))
            resultados.append(bytes(s.get_data()))
        self.assertNotEqual(*resultados)
        # La cara del atlas permanece idéntica aunque se muevan las patas.
        for fila in range(100,250):
            inicio = fila * 2048 + 220 * 4
            fin = fila * 2048 + 390 * 4
            self.assertEqual(resultados[0][inicio:fin],resultados[1][inicio:fin])

    def test_sin_gestos_el_render_es_identico_al_atlas(self):
        sprite = cargar_poses()[0]
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32,512,512)
        animacion.pintar(cairo.Context(s),sprite,())
        self.assertEqual(bytes(s.get_data()),bytes(sprite.get_data()))
