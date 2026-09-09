"""Recorre el menú real de gestos y activa sus botones GTK."""
from types import MethodType
import unittest
from unittest.mock import Mock

from appstudy import pet
from tests.test_animacion_bit import BitSinVentana
from gi.repository import Gtk, Gdk


class MenuBit:
    def __init__(self):
        self.menu = Gtk.Popover()
        self.creature = BitSinVentana()
        self.refrescar_menu = Mock()

    def __getattr__(self, nombre):
        valor = getattr(pet.PetWindow, nombre)
        # Las propiedades (`nombre`) llegan aquí sin resolver: se piden a mano.
        return valor.fget(self) if isinstance(valor, property) else \
            MethodType(valor, self)


class MenuGestosUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla GTK")

    def test_boton_abre_lista_y_cada_gesto_ejecuta_animacion(self):
        bit = MenuBit()
        for nombre, etiqueta in pet.Creature.GESTOS_MENU:
            with self.subTest(gesto=nombre):
                bit.creature.anims.clear()
                bit.boton_menu_gestos().emit("clicked")
                hijo = bit.menu_caja.get_first_child()
                while hijo is not None:
                    if isinstance(hijo, Gtk.Button) and isinstance(hijo.get_child(), Gtk.Box):
                        if hijo.get_child().get_first_child().get_label() == etiqueta:
                            hijo.emit("clicked")
                            break
                    hijo = hijo.get_next_sibling()
                self.assertIsNotNone(hijo, "El gesto debe ser accesible sin expandir el menú")
                self.assertIsNotNone(bit.creature.phase(nombre))

    def test_volver_y_aviso_movimiento_reducido(self):
        bit = MenuBit()
        bit.creature.reduced_motion = True
        bit.boton_menu_gestos().emit("clicked")
        caja = bit.menu_caja
        volver = caja.get_first_child()
        aviso = volver.get_next_sibling().get_next_sibling()
        self.assertIn("Reducir movimiento", aviso.get_label())
        volver.emit("clicked")
        bit.refrescar_menu.assert_called_once()


class MenuCabeEnPantallaTest(unittest.TestCase):
    """El menú creció hasta rozar los 864 px de una pantalla normal.

    Cuando no cabe, GTK lo recorta sin avisar y las últimas opciones —cambiar de
    mascota, los tamaños, salir— quedan fuera de alcance, sobre todo con la
    mascota apoyada en la parte de abajo. Tiene que desplazarse, no recortarse.
    """

    @classmethod
    def setUpClass(cls):
        Gtk.init()
        if Gdk.Display.get_default() is None:
            raise unittest.SkipTest("Requiere pantalla GTK")

    def alto_menor(self):
        monitores = Gdk.Display.get_default().get_monitors()
        return min(monitores.get_item(i).get_geometry().height
                   for i in range(monitores.get_n_items()))

    def test_un_menu_larguisimo_se_desplaza_en_vez_de_recortarse(self):
        bit = MenuBit()
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for i in range(80):
            caja.append(Gtk.Button(label=f"opción {i}"))
        bit.poner_en_menu(caja)
        tope = bit.alto_util_menu()
        self.assertLessEqual(tope, self.alto_menor())
        _, natural, _, _ = bit.menu.get_child().measure(Gtk.Orientation.VERTICAL, -1)
        self.assertLessEqual(natural, tope)
        # Y la última opción sigue estando ahí, solo que hay que bajar hasta ella
        self.assertIs(bit.menu_caja, caja)
        self.assertEqual(caja.get_last_child().get_label(), "opción 79")

    def test_un_menu_corto_sigue_saliendo_corto(self):
        # Poder desplazarse no puede volver alto a un menú de dos líneas. La
        # barra de desplazamiento le impone unas decenas de píxeles de mínimo,
        # que es lo único que se le consiente.
        bit = MenuBit()
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        caja.append(Gtk.Button(label="una sola opción"))
        bit.poner_en_menu(caja)
        _, natural, _, _ = bit.menu.get_child().measure(Gtk.Orientation.VERTICAL, -1)
        _, natural_caja, _, _ = caja.measure(Gtk.Orientation.VERTICAL, -1)
        self.assertLess(natural, natural_caja + 40)
        self.assertLess(natural, bit.alto_util_menu() / 4)


class PropagacionMenuTest(unittest.TestCase):
    def test_clic_del_popover_no_activa_mascota_ni_globo(self):
        ventana = Mock()
        ventana.clic_del_menu = MethodType(pet.PetWindow.clic_del_menu, ventana)
        gesto = Mock()
        gesto.get_current_event().get_surface.return_value = object()
        ventana.get_surface.return_value = object()
        pet.PetWindow.on_click(ventana, gesto, 1, 0, 0)
        pet.PetWindow.on_bubble_click(ventana, gesto, 1, 0, 0)
        ventana.teach.assert_not_called()
        ventana.close_bubble.assert_not_called()
        ventana.abrir_menu_en.assert_not_called()
