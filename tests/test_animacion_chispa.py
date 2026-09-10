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


class ConversacionTest(unittest.TestCase):
    def test_voz_arranca_suave_y_se_detiene_al_cancelarla(self):
        from appstudy.chispa import Chispa
        from tests.test_animacion_bit import BitSinVentana
        zorro = BitSinVentana(Chispa)
        zorro.hablar(2)
        self.assertEqual(zorro._intensidad_voz(), 0)
        zorro.t = .5
        self.assertEqual(zorro._intensidad_voz(), 1)
        self.assertEqual(zorro._indice_pose(), 0)
        zorro.t = 1.95
        self.assertLess(zorro._intensidad_voz(), .2)
        zorro.hablando_hasta = 0
        self.assertEqual(zorro._intensidad_voz(), 0)

    def test_reducir_movimiento_y_dormir_detienen_la_cara(self):
        from appstudy.chispa import Chispa
        from tests.test_animacion_bit import BitSinVentana
        zorro = BitSinVentana(Chispa)
        zorro.hablar(3)
        zorro.t = 1
        zorro.reduced_motion = True
        self.assertEqual(zorro._intensidad_voz(), 0)
        self.assertEqual(animacion.expresiones(0,1,(1,1),.5,.5,1,True), ())
        zorro.reduced_motion = False
        zorro.mood = "dormido"
        self.assertEqual(zorro._intensidad_voz(), 0)
        self.assertEqual(animacion.expresiones(5,1,(1,1),.5,.5,1), ())

    def test_parpadeo_modifica_ojos_pero_no_hocico(self):
        sprite = cargar_poses()[0]
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32,512,512)
        cr = cairo.Context(s)
        cr.set_source_surface(sprite,0,0); cr.paint()
        antes = bytes(s.get_data())
        animacion.parpados(cr,0,512,512,.5)
        despues = bytes(s.get_data())
        self.assertNotEqual(antes,despues)
        # Por debajo de los ojos, el hocico y el cuerpo no se repintan.
        self.assertEqual(antes[245*2048:],despues[245*2048:])

    def test_hablar_no_mueve_la_nariz(self):
        for tiempo in (.1,.3,.5,.8):
            rasgos = animacion.expresiones(0,tiempo,voz=1)
            self.assertEqual(animacion.desplazar_rasgos(.625,.437,rasgos),(.625,.437))

    def test_voz_y_mirada_no_invierten_la_textura(self):
        for tiempo in (.13,.37,.75):
            rasgos = animacion.expresiones(0,tiempo,(1,-1),voz=1)
            for y in range(12,29):
                for x in range(18,40):
                    puntos = [animacion.desplazar_rasgos(a/48,b/48,rasgos)
                              for a,b in ((x,y),(x+1,y),(x+1,y+1),(x,y+1))]
                    for a,b,c in ((puntos[0],puntos[1],puntos[2]),
                                  (puntos[0],puntos[2],puntos[3])):
                        area = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                        self.assertGreater(area,0)


class HablaSinDeformacionesTest(unittest.TestCase):
    def test_hablar_conserva_nariz_ojos_y_transparencia(self):
        sprite = cargar_poses()[0]
        original = bytes(sprite.get_data())
        cambios = 0
        for tiempo in (.1,.35,.7,1.1):
            s = cairo.ImageSurface(cairo.FORMAT_ARGB32,512,512)
            animacion.pintar(cairo.Context(s),sprite,(),
                            animacion.expresiones(0,tiempo,voz=1))
            resultado = bytes(s.get_data())
            self.assertEqual(original[:237*2048],resultado[:237*2048])
            self.assertEqual(original[273*2048:],resultado[273*2048:])
            antes = memoryview(sprite.get_data()).cast("I")
            despues = memoryview(s.get_data()).cast("I")
            self.assertEqual([v>>24 for v in antes],[v>>24 for v in despues])
            cambios += original != resultado
        self.assertGreater(cambios,0,"la boca debe seguir animándose")

    def test_hablar_y_gestos_no_producen_huecos_transparentes(self):
        sprite = cargar_poses()[0]
        antes = memoryview(sprite.get_data()).cast("I")
        for tiempo in (.1, .2, .35, .5, .7, .85, 1.0):
            gestos = animacion.movimientos(0, tiempo, 1.0, voz=1.0)
            rasgos = animacion.expresiones(0, tiempo, voz=1.0)
            s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 512, 512)
            animacion.pintar(cairo.Context(s), sprite, gestos, rasgos)
            despues = memoryview(s.get_data()).cast("I")
            huecos = sum(1 for o, d in zip(antes, despues)
                         if (o >> 24) > 200 and (d >> 24) == 0)
            self.assertEqual(huecos, 0, f"Huecos transparentes en t={tiempo}")

    def test_el_dibujo_no_usa_las_capas_segmentadas(self):
        from unittest.mock import patch
        from appstudy.chispa import Chispa
        from tests.test_animacion_bit import BitSinVentana
        zorro = BitSinVentana(Chispa)
        zorro.hablar(2)
        zorro.t = .5
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32,228,246)
        with patch.object(Chispa,"_rig",side_effect=AssertionError("capas defectuosas")):
            zorro.draw(None,cairo.Context(s),228,246)
        self.assertTrue(any(s.get_data()))

    def test_la_apertura_se_distingue_al_tamano_de_pantalla(self):
        # La boca debe cambiar varios píxeles a tamaño real, no solo en el
        # atlas ampliado. La malla anterior producía cambios subpíxel.
        fondos = []
        for tiempo in (.1,.35):
            s = cairo.ImageSurface(cairo.FORMAT_ARGB32,184,184)
            cr = cairo.Context(s)
            cr.scale(184/512,184/512)
            animacion.pintar(cr,cargar_poses()[0],(),
                            animacion.expresiones(0,tiempo,voz=1))
            pixeles = memoryview(s.get_data()).cast("I")
            filas = [y for y in range(86,99) for x in range(103,129)
                     if ((pixeles[y*184+x]>>16)&255)<135
                     and ((pixeles[y*184+x]>>8)&255)<90
                     and pixeles[y*184+x]>>24>200]
            self.assertTrue(filas)
            fondos.append(max(filas))
        self.assertGreaterEqual(fondos[1]-fondos[0],2)


class NuevasAnimacionesTest(unittest.TestCase):
    def test_bostezo_modifica_la_boca(self):
        rasgos = animacion.expresiones(0, 0.0, bostezo=0.5)
        self.assertTrue(any(cierre < -0.3 for *_, cierre in rasgos))

    def test_rascarse_mueve_la_pata_hacia_la_oreja(self):
        antes = animacion.movimientos(4, 0.0)
        durante = animacion.movimientos(4, 0.0, rascarse=0.5)
        self.assertNotEqual(antes[0], durante[0])

    def test_estirar_desplaza_brazos(self):
        antes = animacion.movimientos(0, 0.0)
        durante = animacion.movimientos(0, 0.0, estirar=0.5)
        self.assertNotEqual(antes[0], durante[0])

    def test_risa_genera_movimiento(self):
        antes = animacion.movimientos(3, 0.0)
        durante = animacion.movimientos(3, 0.0, risa=0.5)
        self.assertNotEqual(antes, durante)

    def test_caricia_entorna_parpados(self):
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 512, 512)
        cr = cairo.Context(s)
        animacion.parpados(cr, 0, 512, 512, caricia=0.8)
        self.assertTrue(any(s.get_data()))
