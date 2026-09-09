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
        return MethodType(getattr(pet.PetWindow, nombre), self)


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
                hijo = bit.menu.get_child().get_first_child()
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
        caja = bit.menu.get_child()
        volver = caja.get_first_child()
        aviso = volver.get_next_sibling().get_next_sibling()
        self.assertIn("Reducir movimiento", aviso.get_label())
        volver.emit("clicked")
        bit.refrescar_menu.assert_called_once()


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
