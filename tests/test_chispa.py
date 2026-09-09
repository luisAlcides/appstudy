"""Chispa: que se dibuja entera, que se elige desde la base y que no es Bit."""
import math
import unittest
from types import MethodType
from unittest.mock import Mock, patch

import cairo
from gi.repository import Gdk, Gtk

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

    @patch("appstudy.chispa.cargar_poses", return_value=None)
    def test_la_cola_se_guarda_y_se_rehace_al_cambiar_de_animo(self, _poses):
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


class IlustracionTest(unittest.TestCase):
    def test_atlas_disponible_transparente_y_en_cache(self):
        poses = chispa.cargar_poses()
        self.assertIsNotNone(poses, "La aplicación debe incluir el atlas de Chispa")
        self.assertEqual(len(poses), 6)
        self.assertIs(poses, chispa.cargar_poses())
        for pose in poses:
            pixeles = memoryview(pose.get_data()).cast("I")
            self.assertEqual(pixeles[0] >> 24, 0)
            opacos = sum((p >> 24) > 200 for p in pixeles)
            self.assertGreater(opacos, len(pixeles) * .1)
            self.assertLess(opacos, len(pixeles) * .85)

    def test_acciones_cambian_pose_y_descanso_tiene_prioridad(self):
        zorro = BitSinVentana(chispa.Chispa)
        self.assertEqual(zorro._indice_pose(), 0)
        zorro.saludar()
        self.assertEqual(zorro._indice_pose(), 1)
        zorro.t = 10
        zorro.teaching = True
        self.assertEqual(zorro._indice_pose(), 2)
        zorro.pensar()
        self.assertEqual(zorro._indice_pose(), 4)
        zorro.celebrar()
        self.assertEqual(zorro._indice_pose(), 3)
        zorro.mood = "dormido"
        self.assertEqual(zorro._indice_pose(), 5)

    def test_sin_movimiento_sigue_expresando_las_acciones(self):
        zorro = BitSinVentana(chispa.Chispa)
        zorro.reduced_motion = True
        zorro.saludar()
        self.assertEqual(zorro._indice_pose(), 1)
        self.assertEqual(zorro._pose(), (0, 1, 1, 0))

    def test_recurso_ausente_conserva_mascota_vectorial(self):
        zorro = BitSinVentana(chispa.Chispa)
        with patch("appstudy.chispa.cargar_poses", return_value=None):
            superficie = DibujoTest().pintar(zorro)
        self.assertTrue(any(superficie.get_data()))


class RelevoTest(unittest.TestCase):
    """Cambiar de mascota no puede sentirse como reiniciarla."""

    def test_la_nueva_hereda_lo_que_la_vieja_sabia(self):
        vieja = BitSinVentana(bit.Bit)
        vieja.mood, vieja.energy, vieja.accessory = "triste", 0.3, "gafas"
        vieja.genero, vieja.abandono, vieja.enojado = "f", 0.8, True
        nueva = pet.traspasar_estado(vieja, BitSinVentana(chispa.Chispa))
        for atributo in pet.ESTADO_COMPARTIDO:
            with self.subTest(atributo=atributo):
                self.assertEqual(getattr(nueva, atributo), getattr(vieja, atributo))

    def test_el_color_se_recalcula_con_la_paleta_nueva(self):
        vieja = BitSinVentana(bit.Bit)
        vieja.mood = "feliz"
        vieja.color_actual = pet._hex(bit.Bit.MOODS["feliz"])[:3]
        nueva = pet.traspasar_estado(vieja, BitSinVentana(chispa.Chispa))
        self.assertEqual(nueva.color_actual,
                         pet._hex(chispa.Chispa.MOODS["feliz"])[:3])
        self.assertNotEqual(nueva.color_actual, vieja.color_actual)

    def test_el_progreso_no_es_de_ninguna_de_las_dos(self):
        # Accesorios y evolución se guardan aparte: cambiar no cuesta repasos.
        self.assertNotIn("pet_mascota", pet.ESTADO_COMPARTIDO)
        self.assertIn("accessory", pet.ESTADO_COMPARTIDO)


class VentanaFalsa:
    """Lo justo de PetWindow para probar el relevo: el asa, el menú y la base."""

    def __init__(self, con):
        self.con = con
        self.creature = bit.Bit(1.0)
        self.handle = Gtk.WindowHandle()
        self.handle.set_child(self.creature)
        self.menu = Gtk.Popover(has_arrow=False)
        self.menu.set_parent(self.creature)
        self.set_title = Mock()
        self.refresh_stats = Mock()

    def on_click(self, *_):
        pass

    def __getattr__(self, nombre):
        valor = getattr(pet.PetWindow, nombre)
        return valor.fget(self) if isinstance(valor, property) else \
            MethodType(valor, self)


class RelevoEnCalienteTest(BaseTemporal):
    """Elegir mascota en Ajustes tiene que llegar a la ventana sin reiniciarla."""

    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla GTK")

    def test_el_ajuste_cambia_la_criatura_de_la_ventana(self):
        ventana = VentanaFalsa(self.con)
        self.assertFalse(ventana.aplicar_mascota(), "sin cambio no toca nada")
        db.set_meta(self.con, "pet_mascota", "chispa")
        self.assertTrue(ventana.aplicar_mascota())
        self.assertIsInstance(ventana.creature, chispa.Chispa)
        # Y queda colgada donde estaba, con el menú apuntándole a ella
        self.assertIs(ventana.handle.get_child(), ventana.creature)
        self.assertIs(ventana.menu.get_parent(), ventana.creature)
        self.assertFalse(ventana.aplicar_mascota(), "ya está puesta")

    def test_el_relevo_conserva_tamaño_y_estado(self):
        ventana = VentanaFalsa(self.con)
        ventana.creature.set_escala(1.6)
        ventana.creature.mood = "triste"
        ventana.creature.accessory = "gafas"
        db.set_meta(self.con, "pet_mascota", "chispa")
        ventana.aplicar_mascota()
        self.assertAlmostEqual(ventana.creature.escala, 1.6)
        self.assertEqual(ventana.creature.mood, "triste")
        self.assertEqual(ventana.creature.accessory, "gafas")
        self.assertEqual(ventana.creature.get_content_width(),
                         round(chispa.Chispa.ANCHO * 1.6))

    def test_el_menu_ofrece_la_otra(self):
        ventana = VentanaFalsa(self.con)
        self.assertEqual([p.NOMBRE for p in ventana.otras_mascotas()], ["Chispa"])
        db.set_meta(self.con, "pet_mascota", "chispa")
        ventana.aplicar_mascota()
        self.assertEqual([p.NOMBRE for p in ventana.otras_mascotas()], ["Bit"])

    def test_cambiar_desde_el_menu_guarda_y_saluda(self):
        ventana = VentanaFalsa(self.con)
        ventana.cambiar_mascota("chispa")
        self.assertEqual(db.get_meta(self.con, "pet_mascota"), "chispa")
        self.assertIsInstance(ventana.creature, chispa.Chispa)
        self.assertIsNotNone(ventana.creature.phase("saludo"))
