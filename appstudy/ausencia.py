"""¿Te levantaste y acabas de volver? Lo que dispara la bitácora del taller.

En el taller te llaman cuando llega un equipo, y la laptop se queda quieta. Al
volver, ese es el momento de contar qué tenía: lo tienes fresco y todavía no
has vuelto a lo tuyo. Aquí se detecta ese regreso.

La inactividad la da el propio GNOME (`org.gnome.Mutter.IdleMonitor`, por
D-Bus): milisegundos desde la última tecla o movimiento de ratón. Sin nada que
instalar, y sirve igual en X11 que en Wayland.

`Vigia` es pura lógica —recibe lecturas y dice cuándo has vuelto—, así que se
prueba sin escritorio. `inactividad_s` es lo único que habla con el sistema.
"""
from __future__ import annotations

import time

from . import db

MINUTOS_DEFECTO = 10
MAX_MINUTOS = 120
ENFRIAMIENTO = 30 * 60      # s; si te llaman cada rato, no preguntar a cada vuelta

_BUS = "org.gnome.Mutter.IdleMonitor"
_RUTA = "/org/gnome/Mutter/IdleMonitor/Core"


def minutos(con) -> int:
    """Ausencia mínima para preguntar al volver. 0 = no preguntar nunca."""
    try:
        valor = int(db.get_meta(con, "bitacora_ausencia_min", MINUTOS_DEFECTO))
    except (TypeError, ValueError):
        valor = MINUTOS_DEFECTO
    return max(0, min(MAX_MINUTOS, valor))


def guardar_minutos(con, valor: int):
    db.set_meta(con, "bitacora_ausencia_min", str(max(0, min(MAX_MINUTOS, int(valor)))))


def inactividad_s() -> float | None:
    """Segundos sin tocar teclado ni ratón, o None si GNOME no lo dice."""
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        r = bus.call_sync(_BUS, _RUTA, _BUS, "GetIdletime", None,
                          GLib.VariantType.new("(t)"), Gio.DBusCallFlags.NONE, 500, None)
        return r.unpack()[0] / 1000.0
    except Exception:           # sin GNOME, sin bus o sin permiso: simplemente no se sabe
        return None


class Vigia:
    """Recibe la inactividad cada pocos segundos y avisa al volver de una ausencia.

    Una vuelta es ver la inactividad *bajar* después de haber pasado del umbral:
    estabas fuera y alguien ha tocado el teclado. `observar` devuelve entonces
    los minutos que estuviste fuera; el resto del tiempo, None.
    """

    def __init__(self, umbral_s: float, enfriamiento_s: float = ENFRIAMIENTO):
        self.umbral_s = umbral_s
        self.enfriamiento_s = enfriamiento_s
        self._previo: float | None = None
        self._ultimo_aviso = float("-inf")

    def observar(self, idle_s: float | None, ahora: float | None = None) -> float | None:
        if idle_s is None:              # una lectura perdida no borra lo que se sabía
            return None
        ahora = time.time() if ahora is None else ahora
        previo, self._previo = self._previo, idle_s
        if (not self.umbral_s or previo is None or idle_s >= previo
                or previo < self.umbral_s):
            return None
        if ahora - self._ultimo_aviso < self.enfriamiento_s:
            return None
        self._ultimo_aviso = ahora
        return previo / 60.0
