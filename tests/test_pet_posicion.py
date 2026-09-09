"""La posición elegida no se sustituye por ajustes del globo ni callbacks viejos."""
import json
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from tests.apoyo import BaseTemporal
from appstudy import db, pet


class MascotaSinVentana:
    def __init__(self, con):
        self.con = con
        self.pos = (900, 600)
        self.actual = self.pos
        self._auto_pos = None
        self._position_ready = True
        self._position_touched = False
        self.abierto = True
        self.escala = 1
        self.movimientos = []
        self.bubble = SimpleNamespace(get_reveal_child=lambda: self.abierto)
        self.clear_bubble = Mock()

    def __getattr__(self, nombre):
        metodo = getattr(pet.PetWindow, nombre)
        return MethodType(metodo, self)

    def read_position(self):
        return self.actual

    def move_to(self, x, y):
        self.movimientos.append((x, y))
        self.actual = (x, y)
        return True

    def get_surface(self):
        return SimpleNamespace(get_scale_factor=lambda: self.escala)

    def get_display(self):
        monitor = SimpleNamespace(get_geometry=lambda: SimpleNamespace(x=0, y=0, width=1000, height=800))
        return SimpleNamespace(get_monitor_at_surface=lambda _: monitor)

    def get_width(self):
        return 400

    def get_height(self):
        return 500


class PosicionBitTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        self.bit = MascotaSinVentana(self.con)
        db.set_meta(self.con, "pet_pos", json.dumps(self.bit.pos))

    def guardada(self):
        return tuple(json.loads(db.get_meta(self.con, "pet_pos")))

    def test_globo_no_reemplaza_posicion_y_al_cerrar_vuelve(self):
        self.bit.fit_on_screen()
        self.assertEqual(self.bit.actual, (592, 292))
        self.bit.save_position()
        self.assertEqual(self.guardada(), (900, 600))
        self.bit.abierto = False
        self.bit.finish_close_bubble()
        self.assertEqual(self.bit.actual, (900, 600))

    def test_arrastrar_con_globo_abierto_conserva_nuevo_sitio(self):
        self.bit.fit_on_screen()
        self.bit.actual = (100, 120)
        self.bit.abierto = False
        self.bit.finish_close_bubble()
        self.assertEqual(self.guardada(), (100, 120))
        self.assertEqual(self.bit.actual, (100, 120))
        self.assertIsNone(self.bit._auto_pos)

    def test_cerrar_antes_del_ajuste_no_mueve(self):
        self.bit.abierto = False
        self.bit.fit_on_screen()
        self.assertEqual(self.bit.movimientos, [])

    def test_reabrir_antes_de_callback_no_borra_globo_nuevo(self):
        self.bit.finish_close_bubble()
        self.bit.clear_bubble.assert_not_called()

    def test_arrastre_antes_de_callback_no_se_desplaza(self):
        self.bit.actual = (750, 400)
        self.bit.fit_on_screen((900, 600))
        self.assertEqual(self.bit.movimientos, [])
        self.assertEqual(self.guardada(), (750, 400))

    def test_escalado_usa_pixeles_consistentes(self):
        self.bit.escala = 2
        self.bit.actual = self.bit.pos = (1800, 1200)
        self.bit.fit_on_screen()
        self.assertEqual(self.bit.actual, (1184, 584))

    def test_arrastre_antes_de_restaurar_tiene_prioridad(self):
        self.bit.actual = (300, 200)
        self.bit.position_interaction()
        self.bit.restore_position()
        self.assertEqual(self.bit.movimientos, [])
        self.assertEqual(self.guardada(), (300, 200))

    def test_no_guarda_posicion_inicial_del_gestor(self):
        self.bit._position_ready = False
        self.bit.actual = (0, 0)
        self.bit.save_position()
        self.assertEqual(self.guardada(), (900, 600))

    def test_restaurar_usa_la_posicion_guardada(self):
        self.bit.actual = (0, 0)
        self.bit.restore_position()
        self.assertEqual(self.bit.actual, (900, 600))

    def test_ajuste_fallido_no_se_guarda_como_temporal(self):
        self.bit.move_to = Mock(return_value=False)
        self.bit.fit_on_screen()
        self.assertIsNone(self.bit._auto_pos)
        self.assertEqual(self.guardada(), (900, 600))
