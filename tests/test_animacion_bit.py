"""Geometría y tiempo de Bit sin abrir ventanas ni depender de un compositor."""
import math
import types
import unittest
from unittest.mock import patch

import cairo

from appstudy import pet


class BitSinVentana:
    """Ejecuta los métodos reales de dibujo con estado en memoria, sin GTK UI."""

    def __init__(self):
        self.t = 0.0
        self.mood = "normal"
        self.energy = self.energy_mostrada = 1.0
        self.teaching = self.charlando = self.hover = self.reduced_motion = False
        self.hover_suave = self.abandono = 0.0
        self.accessory = "ninguno"
        self.anims = {}
        self.particulas = []
        self.mirada = [0.0, 0.0]
        self.objetivo = [0.0, 0.0]
        self.puntero = None
        self.hablando_hasta = self.angulo_estrella = 0.0
        self.inercia = self.inercia_vel = self._pose_y = 0.0
        self.color_actual = pet._hex(pet.MOODS["normal"])[:3]
        self.next_idle = 1000
        self._frame_time = None
        self._cache_estrella = None
        self._cache_cuerpo = None

    def __getattr__(self, nombre):
        valor = getattr(pet.Creature, nombre)
        return types.MethodType(valor, self) if callable(valor) else valor

    def queue_draw(self):
        pass


class AnimacionBitTest(unittest.TestCase):
    def test_reloj_de_frames_limita_reposo_y_se_reinicia_al_volver(self):
        bit = BitSinVentana()
        reloj = unittest.mock.Mock()
        for sello in (1_000_000, 1_016_667, 1_033_334):
            reloj.get_frame_time.return_value = sello
            bit._on_frame(None, reloj)
        self.assertEqual(bit.t, 0)
        reloj.get_frame_time.return_value = 1_050_000
        bit._on_frame(None, reloj)
        self.assertAlmostEqual(bit.t, 0.05)
        bit.play("salto", 1)
        reloj.get_frame_time.return_value = 1_066_667
        bit._on_frame(None, reloj)
        self.assertAlmostEqual(bit.t, 0.066667)
        bit._reiniciar_reloj()
        reloj.get_frame_time.return_value = 100_000_000
        bit._on_frame(None, reloj)
        self.assertAlmostEqual(bit.t, 0.066667)

    def test_reloj_del_sistema_no_interrumpe_los_gestos(self):
        bit = BitSinVentana()
        bit.play("salto", 1)
        with patch("appstudy.pet.time.time", return_value=-100000):
            for _ in range(5):
                bit.tick(0.1)
        self.assertAlmostEqual(bit.phase("salto"), 0.5)
        for _ in range(6):
            bit.tick(0.1)
        self.assertIsNone(bit.phase("salto"))

    def test_muelle_es_independiente_de_la_cadencia(self):
        resultados = []
        for fps in (20, 60, 144):
            posicion, velocidad = 0, 0
            for _ in range(fps):
                posicion, velocidad = pet.muelle(posicion, velocidad, 1, 12, 1 / fps)
                self.assertGreaterEqual(posicion, 0)
                self.assertLessEqual(posicion, 1)
            resultados.append(posicion)
        self.assertAlmostEqual(resultados[0], resultados[1], places=10)
        self.assertAlmostEqual(resultados[1], resultados[2], places=10)

    def test_salto_no_tiene_saltos_de_posicion_ni_velocidad(self):
        bit = BitSinVentana()
        bit.play("salto", 1)
        paso = 0.00001
        for frontera in (0.18, 0.80, 1.0):
            poses = []
            for t in (frontera - paso, frontera, frontera + paso):
                bit.t = t
                poses.append(bit._pose())
            for i in range(4):
                izquierda = (poses[1][i] - poses[0][i]) / paso
                derecha = (poses[2][i] - poses[1][i]) / paso
                self.assertAlmostEqual(izquierda, derecha, delta=0.03)

    def test_movimiento_reducido_sin_particulas_ni_deformaciones(self):
        bit = BitSinVentana()
        bit.celebrar()
        bit.reduced_motion = True
        bit.tick(0.1)
        self.assertEqual(bit.particulas, [])
        self.assertEqual(bit._pose(), (0, 1, 1, 0))
        bit.emitir("chispa", 10)
        self.assertEqual(bit.particulas, [])

    def test_todos_los_estados_y_accesorios_se_dibujan(self):
        bit = BitSinVentana()
        for escala in (0.5, 1, 2.5):
            for mood in pet.MOODS:
                for accesorio in pet.ACCESORIOS:
                    with self.subTest(escala=escala, mood=mood, accesorio=accesorio["key"]):
                        bit.mood, bit.accessory = mood, accesorio["key"]
                        bit.color_actual = pet._hex(pet.MOODS[mood])[:3]
                        w, h = round(pet.ANCHO * escala), round(pet.ALTO_PET * escala)
                        superficie = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
                        bit.draw(None, cairo.Context(superficie), w, h)
                        self.assertTrue(any(superficie.get_data()))
                        self.assertTrue(all(math.isfinite(x) for x in bit._pose()))

    def test_energia_cero_no_pinta_relleno(self):
        bit = BitSinVentana()
        bit.energy_mostrada = 0
        superficie = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 20)
        bit._barra(cairo.Context(superficie), 50, 5, "#FF0000")
        # Centro de la zona antes ocupada por el mínimo de siete píxeles.
        # La pista vacía es marrón; el relleno rojo tiene alfa cercano a uno.
        alpha = memoryview(superficie.get_data()).cast("I")[8 * 100 + 14] >> 24
        self.assertLess(alpha, 100)


if __name__ == "__main__":
    unittest.main()
