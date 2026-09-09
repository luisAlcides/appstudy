"""Chispa: que se dibuja entera, que se elige desde la base y que no es Bit."""
import math
import unittest

import cairo

from appstudy import bit, chispa, db, pet
from tests.apoyo import BaseTemporal
from tests.test_animacion_bit import BitSinVentana


class PieleTest(BaseTemporal):
    def test_por_defecto_sale_bit(self):
        self.assertIs(pet.piel(self.con), bit.Bit)
        self.assertEqual(pet.nombre(self.con), "Bit")

    def test_el_ajuste_elige_la_mascota(self):
        db.set_meta(self.con, "pet_mascota", "chispa")
        self.assertIs(pet.piel(self.con), chispa.Chispa)
        self.assertEqual(pet.nombre(self.con), "Chispa")

    def test_una_mascota_que_ya_no_existe_no_deja_el_escritorio_vacio(self):
        db.set_meta(self.con, "pet_mascota", "dodo")
        self.assertIs(pet.piel(self.con), bit.Bit)

    def test_las_claves_son_unicas_y_estan_todas(self):
        claves = [p.CLAVE for p in pet.PIELES]
        self.assertEqual(sorted(claves), sorted(set(claves)))
        self.assertIn(pet.PIEL_POR_DEFECTO, claves)


class PaletaTest(unittest.TestCase):
    def test_cubre_todos_los_animos(self):
        # Un ánimo sin color se pintaría del de reposo y mentiría sobre el estado.
        self.assertEqual(set(chispa.Chispa.MOODS), set(bit.Bit.MOODS))

    def test_el_pelaje_no_es_el_de_las_patas(self):
        # El zorro tiene calcetines oscuros; si coincidieran, no se le verían.
        self.assertNotEqual(chispa.Chispa.PELAJE, chispa.Chispa.PATA)

    def test_cada_piel_declara_lo_suyo(self):
        for piel in pet.PIELES:
            with self.subTest(piel=piel.NOMBRE):
                self.assertNotEqual(piel.NOMBRE, pet.Creature.NOMBRE)
                self.assertTrue(piel.MOODS)
                self.assertGreater(piel.ANCHO, 0)
                self.assertGreater(piel.ALTO_PET, 0)


class DibujoTest(unittest.TestCase):
    def pintar(self, criatura, escala=1.0):
        w = round(criatura.piel.DISENO[0] * escala)
        h = round(criatura.piel.DISENO[1] * escala)
        superficie = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        criatura.draw(None, cairo.Context(superficie), w, h)
        return superficie

    def test_todos_los_estados_y_accesorios_se_dibujan(self):
        zorro = BitSinVentana(chispa.Chispa)
        for escala in (0.5, 1, 2.5):
            for mood in chispa.Chispa.MOODS:
                for accesorio in pet.ACCESORIOS:
                    with self.subTest(escala=escala, mood=mood,
                                      accesorio=accesorio["key"]):
                        zorro.mood, zorro.accessory = mood, accesorio["key"]
                        zorro.color_actual = pet._hex(chispa.Chispa.MOODS[mood])[:3]
                        superficie = self.pintar(zorro, escala)
                        self.assertTrue(any(superficie.get_data()))
                        self.assertTrue(all(math.isfinite(x) for x in zorro._pose()))

    def test_los_gestos_del_menu_tambien_valen_para_el_zorro(self):
        for nombre, _ in pet.Creature.GESTOS_MENU:
            zorro = BitSinVentana(chispa.Chispa)
            zorro.actuar(nombre)
            for fraccion in (0, .5, .99999):
                zorro.t = zorro.DURACION_GESTO[nombre] * fraccion
                with self.subTest(gesto=nombre, fraccion=fraccion):
                    self.pintar(zorro)
                    self.assertTrue(all(math.isfinite(v) for v in zorro._pose()))

    def test_la_cola_se_guarda_y_se_rehace_al_cambiar_de_animo(self):
        zorro = BitSinVentana(chispa.Chispa)
        zorro.color_actual = pet._hex(chispa.Chispa.MOODS["normal"])[:3]
        self.pintar(zorro)
        primera = zorro._cache_fondo[1]
        self.pintar(zorro)
        self.assertIs(zorro._cache_fondo[1], primera, "el mismo ánimo no la repinta")
        clave = zorro._cache_fondo[0]
        zorro.color_actual = pet._hex(chispa.Chispa.MOODS["triste"])[:3]
        self.pintar(zorro)
        self.assertNotEqual(zorro._cache_fondo[0], clave)

    def test_la_cola_asoma_por_fuera_del_cuerpo(self):
        """Si el cuerpo la tapara entera, la cola sería trabajo tirado."""
        zorro = BitSinVentana(chispa.Chispa)
        zorro.color_actual = pet._hex(chispa.Chispa.MOODS["normal"])[:3]
        superficie = self.pintar(zorro)
        pixeles = memoryview(superficie.get_data()).cast("I")
        w, h = chispa.Chispa.DISENO
        # A la izquierda del cuerpo, a la altura del lomo, solo puede haber cola.
        borde = round(w / 2 + chispa.Chispa.CUERPO_DX - chispa.Chispa.RX) - 6
        fila = round(h - 34 - 40)              # el centro del cuerpo
        pintados = sum(1 for x in range(8, borde)
                       if (pixeles[fila * w + x] >> 24) > 40)
        self.assertGreater(pintados, 10)

    def test_la_barra_de_energia_queda_centrada_aunque_el_cuerpo_se_corra(self):
        # El cuerpo va desplazado para dejarle sitio a la cola; la barra, no.
        self.assertNotEqual(chispa.Chispa.CUERPO_DX, 0)
        zorro = BitSinVentana(chispa.Chispa)
        zorro.energy_mostrada = 1.0
        superficie = self.pintar(zorro)
        pixeles = memoryview(superficie.get_data()).cast("I")
        w, h = chispa.Chispa.DISENO
        fila = h - 14 + 3
        columnas = [x for x in range(w) if (pixeles[fila * w + x] >> 24) > 80]
        centro = (columnas[0] + columnas[-1]) / 2
        self.assertAlmostEqual(centro, w / 2, delta=2)
