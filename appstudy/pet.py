"""Bit, la mascota de escritorio: vive encima de todo y te recuerda estudiar.

Corre en su propio proceso (`appstudy --pet`) y, en GNOME/Wayland, forzado al
backend X11: es la única forma de pedirle al gestor de ventanas que la deje
siempre encima (`_NET_WM_STATE_ABOVE`), algo que Wayland no expone a las
aplicaciones normales. Lee la misma base de datos que el resto de AppStudy, así
que sabe qué tienes pendiente y puede enseñarte una tarjeta sin abrir nada.
"""
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import citas, cloze, db, estadisticas, ia, logros, reto  # noqa: E402
from . import historial, recordatorios, scheduler, sonido, util, voz  # noqa: E402
from .bit import Bit  # noqa: E402
from .criatura import (ESCALA_MAX, ESCALA_MIN, ESCALA_PASO, FRAME_ACTIVO,  # noqa: E402,F401
                       FRAME_REPOSO, Creature, _claro, _hex, _oscuro, acercar,
                       muelle, out_back, out_cubic, pulso, suave)

PET_APP_ID = "io.github.appstudy.AppStudy.Pet"

# Las mascotas disponibles, en el orden en que se ofrecen en Ajustes.
PIELES = (Bit,)
PIEL_POR_DEFECTO = "bit"

# La paleta y las medidas de Bit siguen accesibles por comodidad: son las que
# usan los tests y lo que se dibuja si nadie ha elegido otra cosa.
MOODS = Bit.MOODS
DISENO, ANCHO, ALTO_PET = Bit.DISENO, Bit.ANCHO, Bit.ALTO_PET
CHAT, TERRACOTA, TINTA = Bit.CHAT, Bit.COLOR_BASE, Bit.TINTA

# Cada cuánto revisa el estado y cada cuánto insiste, en segundos
CHECK_EVERY = 15
DEFAULT_EVERY_MIN = 45
SNOOZE_MIN = 60

# Horas sin repasar a partir de las que cambia de ánimo. Entre la primera y la
# última se va viniendo abajo poco a poco (el «abandono» de la criatura).
HORAS_ABURRIDO = 4
HORAS_HAMBRE = 24
HORAS_TRISTE = 72
# Y cada cuánto, como mucho, te lo echa en cara
HORAS_REPROCHE = 3


def debe_enfadarse(horas, pendientes, dormida=False):
    return not dormida and horas >= 24 and pendientes > 0


def enfado_por_estudio(con, pendientes, dormida=False, ahora=None):
    """Repasar y avanzar/terminar una lectura desactivan el enfado."""
    ahora = time.time() if ahora is None else ahora
    ultima = con.execute("""SELECT MAX(ts) FROM (
        SELECT MAX(ts) AS ts FROM log
        UNION ALL SELECT MAX(ts) FROM reading WHERE leido=1 OR avance>0
        UNION ALL SELECT MAX(abierto) FROM books WHERE minutos>0
    )""").fetchone()[0]
    horas = max(0, (ahora - ultima) / 3600) if ultima else 48
    return debe_enfadarse(horas, pendientes, dormida)


# Evoluciona por trabajo real, no por tiempo abierto. Los accesorios son Cairo
# puro: unas pocas curvas más al dibujar, sin imágenes ni memoria adicional.
EVOLUCIONES = (
    {"min": 0, "nombre": "Compañero"},
    {"min": 25, "nombre": "Curioso"},
    {"min": 100, "nombre": "Aplicado"},
    {"min": 500, "nombre": "Sabio"},
    {"min": 1500, "nombre": "Maestro"},
)
ACCESORIOS = (
    {"key": "ninguno", "nombre": "Sin accesorio", "min": 0},
    {"key": "panuelo", "nombre": "Pañuelo", "min": 25},
    {"key": "gafas", "nombre": "Gafas", "min": 100},
    {"key": "corona", "nombre": "Corona", "min": 500},
)


# Cuántos repasos en el día cuentan como «has estudiado» cuando no hay objetivo
# diario puesto. Con objetivo, manda el objetivo.
MINIMO_FELIZ = 10


def animo(t: dict, horas: float, energia: float, dormida: bool = False) -> str:
    """El ánimo de Bit a partir de lo que dice la base.

    El orden importa y es lo que evita que se ponga contenta de más: primero
    pesa **cuánto llevas sin estudiar**, y solo si has repasado hace poco se
    mira si has hecho lo tuyo. Antes bastaba una tarjeta suelta para ponerla
    verde, y se quedaba verde el resto del día aunque no volvieras a aparecer.
    """
    if dormida:
        return "dormido"
    if horas >= HORAS_TRISTE:
        return "triste"
    if horas >= HORAS_HAMBRE:
        return "hambre"
    if horas >= HORAS_ABURRIDO:
        return "aburrido"

    meta = t.get("objetivo") or MINIMO_FELIZ
    if t.get("pendientes", 0) == 0 and t.get("hoy", 0) >= meta:
        return "feliz"
    if energia < 0.3:
        return "hambre"
    return "normal"


def evolucion(repasos: int) -> dict:
    """Etapa actual, siguiente meta y avance 0..1 dentro de la etapa."""
    n = max(0, int(repasos))
    indice = max(i for i, etapa in enumerate(EVOLUCIONES) if n >= etapa["min"])
    actual = EVOLUCIONES[indice]
    siguiente = EVOLUCIONES[indice + 1] if indice + 1 < len(EVOLUCIONES) else None
    if siguiente:
        avance = (n - actual["min"]) / (siguiente["min"] - actual["min"])
    else:
        avance = 1.0
    return {"nombre": actual["nombre"], "min": actual["min"],
            "siguiente": siguiente, "avance": max(0.0, min(1.0, avance)),
            "repasos": n}


def accesorios_disponibles(repasos: int) -> list[dict]:
    n = max(0, int(repasos))
    return [a for a in ACCESORIOS if n >= a["min"]]


def accesorio_valido(clave: str, repasos: int) -> str:
    disponibles = {a["key"] for a in accesorios_disponibles(repasos)}
    return clave if clave in disponibles else "ninguno"


def total_repasos(con) -> int:
    return int(con.execute("SELECT COUNT(*) FROM log").fetchone()[0])


def piel(con):
    """La clase de la mascota elegida en Ajustes; Bit si no hay nada guardado."""
    clave = str(db.get_meta(con, "pet_mascota", PIEL_POR_DEFECTO))
    return {p.CLAVE: p for p in PIELES}.get(clave, Bit)


def nombre(con) -> str:
    """Cómo se llama la mascota que está puesta."""
    return piel(con).NOMBRE


def sin_estudiar(horas: float) -> str:
    """«hace 3 h», «hace 2 días»: para el tooltip y para lo que te dice."""
    if horas < 1:
        return "repasaste hace nada"
    if horas < 24:
        return f"sin repasar desde hace {int(horas)} h"
    dias = int(horas // 24)
    return f"sin repasar desde hace {dias} día{'s' if dias > 1 else ''}"


def reproche(horas: float) -> str:
    """Lo que te suelta cuando llevas días sin aparecer."""
    dias = int(horas // 24)
    if dias < 2:
        return ("Ayer no repasaste nada. Con <b>una tarjeta</b> me conformo, "
                "que si no se te olvida.")
    if dias < 4:
        return (f"Llevas <b>{dias} días</b> sin repasar y se te está borrando lo "
                "que ya sabías. ¿Lo arreglamos ahora?")
    if dias < 8:
        return (f"<b>{dias} días</b>. Ya casi ni me acuerdo de cómo estudiábamos. "
                "Empecemos por una fácil.")
    return (f"<b>{dias} días</b> sin estudiar. Yo aquí sigo, por si te apetece "
            "volver: una tarjeta y lo dejamos.")


class PetWindow(Gtk.ApplicationWindow):
    """Ventana sin bordes, siempre encima, con la criatura y su globo de diálogo."""

    def __init__(self, app, con):
        super().__init__(application=app, title=f"AppStudy · {nombre(con)}")
        self.con = con
        self.xid = None
        self.pos = None
        self._auto_pos = None       # ajuste del globo; nunca es la posición elegida
        self._position_ready = False
        self._position_touched = False
        self._mapped_once = False
        self.card = None            # tarjeta que está enseñando ahora
        self.shown_at = 0.0
        self.last_nag = time.time()
        self.ultimo_reproche = 0
        self.ultimo_aviso_leech = 0.0    # para no repetir la queja cada rato
        self.ultimo_diario = 0.0         # el resumen de la semana, una vez al día
        self.ia_texto = ""            # lo que el modelo lleva escrito
        self.ia_cuerpo = None
        self.contexto_ia = ""         # la tarjeta desde la que preguntaste
        self.sonido = sonido.config(self.con)     # se relee al refrescar el estado
        self.voz_cfg = voz.config(self.con)
        self.btn_voz = None
        self.texto_hablable = ""
        self.chat = None              # {"historial": [...], "contexto": str} en modo chatbot
        self.conversacion = None      # EscuchaContinua cuando la charla es hablada
        self.oido = None              # EscuchaPalabraClave esperando el "hola bit"
        self.examen = None            # ExamenOral o SesionConexiones en curso
        self.ultimo_modo = None       # con qué se repite la ronda al terminar
        self.ultimos_datos = []       # «sabías que» ya soltados, para no repetir
        self.dato_actual = None
        self.recuerdo = None          # recuerdo libre en curso
        self.escucha_recuerdo = None
        self.stats = {}
        self.ultimas_citas = []     # para no repetir la misma frase seguida

        # Retos: el que está en marcha, su cuenta atrás y la fuente que explica
        # la tarjeta (se calcula una vez y se guarda, que mirar la base cuesta).
        self.reto = None
        self.reto_timer = None
        self.reto_total = 1.0
        self.reto_fin = 0.0
        self.barra_tiempo = None
        self.reloj = None
        self.ultimo_formato = None
        self.cap_cache = (None, None)

        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("as-pet")

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                       css_classes=["as-pet-layout"])
        self.set_child(root)

        self.creature = piel(con)(self.escala_guardada())
        self.card_scale = self.card_escala_guardada()
        self.card_css_provider = Gtk.CssProvider()
        disp = Gdk.Display.get_default()
        if disp:
            Gtk.StyleContext.add_provider_for_display(
                disp, self.card_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.aplicar_escala_tarjeta()

        self.handle = handle = Gtk.WindowHandle(css_classes=["as-pet-handle"])
        handle.set_child(self.creature)
        posicion = Gtk.GestureClick(button=1)
        posicion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        posicion.connect("pressed", self.position_interaction)
        handle.add_controller(posicion)
        # Pegada a la izquierda: así la criatura no se desplaza cuando el globo
        # ensancha la ventana.
        handle.set_halign(Gtk.Align.START)
        root.append(handle)

        clic = Gtk.GestureClick(button=0)
        clic.connect("pressed", self.on_click)
        self.creature.add_controller(clic)

        self.bubble = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                                   transition_duration=240,
                                   css_classes=["as-pet-revealer"])
        self.bubble_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                  css_classes=["as-bubble"])
        self.bubble.set_child(self.bubble_box)
        root.append(self.bubble)

        clic_bubble = Gtk.GestureClick(button=0)
        clic_bubble.connect("pressed", self.on_bubble_click)
        self.bubble_box.add_controller(clic_bubble)

        self.registrar_acciones()
        self.menu = Gtk.Popover(has_arrow=False)
        # add_css_class, no css_classes=[...]: el constructor sustituye la lista
        # entera y se lleva por delante la clase "background" que GtkPopover se
        # pone sola, que es la que pinta el fondo. Sin ella la tarjeta sale
        # transparente y se lee el escritorio a través.
        self.menu.add_css_class("as-menu")
        self.menu.set_parent(self.creature)

        self.connect("map", self.on_map)
        GLib.timeout_add_seconds(CHECK_EVERY, self.on_check)
        GLib.timeout_add_seconds(3, self.save_position)
        app.connect("shutdown", lambda *_: self.save_position())
        self.refresh_stats()
        # El oído tarda un segundo en cargar su modelo: se hace después de que la
        # ventana esté puesta para no retrasar la aparición de Bit.
        GLib.timeout_add_seconds(2, lambda: (self.arrancar_palabra_clave(), False)[1])

    @property
    def nombre(self) -> str:
        """Cómo se llama la mascota que está puesta ahora mismo."""
        return self.creature.NOMBRE

    def aplicar_mascota(self) -> bool:
        """Cambia de mascota en caliente si el ajuste dice otra cosa.

        No hace falta reiniciar nada: la criatura es un hijo del asa, así que
        basta con sustituirla llevándose su estado —ánimo, energía, accesorio,
        escala— para que el relevo no se note más que en el dibujo.
        """
        clase = piel(self.con)
        if isinstance(self.creature, clase):
            return False
        vieja = self.creature
        nueva = clase(vieja.escala)
        for atributo in ("mood", "energy", "energy_mostrada", "teaching",
                         "charlando", "accessory", "genero", "abandono",
                         "enojado", "reduced_motion"):
            setattr(nueva, atributo, getattr(vieja, atributo))
        # El color se recalcula con la paleta nueva: el de la vieja no existe aquí.
        nueva.color_actual = _hex(nueva.MOODS.get(nueva.mood, nueva.COLOR_BASE))[:3]

        self.creature = nueva
        self.handle.set_child(nueva)
        clic = Gtk.GestureClick(button=0)
        clic.connect("pressed", self.on_click)
        nueva.add_controller(clic)
        self.menu.unparent()
        self.menu.set_parent(nueva)
        self.set_title(f"AppStudy · {nueva.NOMBRE}")
        return True

    def cambiar_mascota(self, clave: str):
        """Desde el menú de la mascota: elegir con quién se estudia."""
        db.set_meta(self.con, "pet_mascota", clave)
        if self.aplicar_mascota():
            self.refresh_stats()
            self.creature.saludar()

    # ------------------------------------------------------- siempre por encima

    def on_map(self, *_):
        surface = self.get_surface()
        try:
            # Cargar la introspección de X11 es lo que revela get_xid() en la superficie
            gi.require_version("GdkX11", "4.0")
            from gi.repository import GdkX11  # noqa: F401
            self.xid = surface.get_xid()
        except (ValueError, ImportError, AttributeError):
            self.xid = None
        if self.xid is None:
            print("Aviso: sin backend X11 no puedo quedarme encima de todo.",
                  file=sys.stderr)
            return
        self.keep_above()
        if self._mapped_once:
            return
        self._mapped_once = True
        GLib.timeout_add(150, self.restore_position)
        # Algunos gestores olvidan el estado al cambiar de espacio de trabajo o
        # al salir de pantalla completa, así que se vuelve a pedir a menudo.
        GLib.timeout_add_seconds(10, self.vigilar)

    def vigilar(self):
        """Que no se pierda: siempre visible, siempre encima, en todos los escritorios."""
        if not self.get_visible():
            self.present()
        self.keep_above()
        return True

    def wmctrl(self, *args) -> bool:
        if self.xid is None:
            return False
        try:
            r = subprocess.run(["wmctrl", "-i", "-r", hex(self.xid), *args],
                               capture_output=True, text=True, timeout=3)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def keep_above(self):
        # De a una: wmctrl solo aplica dos propiedades por llamada
        for prop in ("above", "sticky", "skip_taskbar", "skip_pager"):
            self.wmctrl("-b", f"add,{prop}")

    # ------------------------------------------------------------- posición

    def read_position(self):
        """Posición real de la ventana.

        Se pregunta con `xwininfo` y no con `wmctrl -lG`: cuando el escritorio
        usa escalado, la lista de wmctrl devuelve las coordenadas multiplicadas
        por el factor, mientras que xwininfo (y el propio `wmctrl -e`) hablan en
        píxeles reales.
        """
        if self.xid is None:
            return None
        try:
            out = subprocess.run(["xwininfo", "-id", hex(self.xid)],
                                 capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        coords = {}
        for linea in out.splitlines():
            if "Absolute upper-left X:" in linea:
                coords["x"] = int(linea.rsplit(":", 1)[1])
            elif "Absolute upper-left Y:" in linea:
                coords["y"] = int(linea.rsplit(":", 1)[1])
        return (coords["x"], coords["y"]) if len(coords) == 2 else None

    def move_to(self, x, y):
        return self.wmctrl("-e", f"0,{x},{y},-1,-1")

    def position_interaction(self, *_):
        # Si ya empezó a arrastrar, la restauración de arranque no debe
        # devolverla al sitio anterior cuando llegue su callback pendiente.
        self._position_touched = True

    def restore_position(self):
        self._position_ready = True
        if self._position_touched:
            self.save_position()
            return False
        guardada = db.get_meta(self.con, "pet_pos")
        if guardada:
            try:
                x, y = json.loads(guardada)
                if self.move_to(int(x), int(y)):
                    self.pos = (int(x), int(y))
                return False
            except (ValueError, TypeError):
                pass
        monitor = self.get_display().get_monitors().get_item(0)
        area = monitor.get_geometry() if monitor else None
        escala = self.get_surface().get_scale_factor()
        x = (area.x + area.width - self.get_width() - 40) * escala if area else 900
        y = (area.y + 60) * escala if area else 80
        if self.move_to(x, y):
            self.pos = (x, y)
            db.set_meta(self.con, "pet_pos", json.dumps(list(self.pos)))
        return False

    def save_position(self):
        if not self._position_ready:
            return True
        actual = self.read_position()
        if self._auto_pos is not None and actual in (self._auto_pos, self.pos):
            return True
        if actual and actual != self.pos:
            self.pos = actual
            self._auto_pos = None
            db.set_meta(self.con, "pet_pos", json.dumps(list(actual)))
        return True

    def finish_close_bubble(self):
        """Deshacer solo el ajuste del globo, respetando un arrastre posterior."""
        if self.bubble.get_reveal_child():
            return False
        self.clear_bubble()
        if self._auto_pos is not None:
            actual = self.read_position()
            if actual == self._auto_pos and self.pos is not None:
                if self.move_to(*self.pos):
                    self._auto_pos = None
            elif actual is not None:
                self.save_position()
        return False

    # ------------------------------------------------------------------ estado

    def sonar(self, nombre):
        sonido.reproducir(self.sonido, nombre)

    def refresh_stats(self):
        """Lee la base y traduce el progreso a ánimo y energía de la mascota.

        Lo que más manda es **cuánto llevas sin estudiar**: a las cuatro horas se
        aburre, al día tiene hambre de repasos, y a los tres días está triste,
        con ojeras y el asterisco casi parado. Vuelve a la normalidad en cuanto
        califiques una tarjeta.
        """
        self.sonido = sonido.config(self.con)
        self.voz_cfg = voz.config(self.con)
        t = db.totals(self.con)
        fila = self.con.execute("SELECT MAX(ts) AS ts FROM log").fetchone()
        ultimo = fila["ts"] or 0
        horas = (time.time() - ultimo) / 3600 if ultimo else 48.0

        # De 0 a 1 entre las 4 h y los 3 días: es lo que le hunde el cuerpo
        abandono = max(0.0, min(1.0, (horas - HORAS_ABURRIDO) /
                                (HORAS_TRISTE - HORAS_ABURRIDO)))
        # La energía baja con las horas sin repasar y con lo que se acumula
        energia = 1.0 - min(horas / 48.0, 1.0) * 0.75 - min(t["pendientes"] / 40.0, 1.0) * 0.35
        energia = max(0.05, min(1.0, energia + min(t["racha"], 7) * 0.02))

        mood = animo(t, horas, energia, self.dormida())

        self.stats = {**t, "energia": energia, "horas": horas, "abandono": abandono}
        if abs(self.escala_guardada() - self.creature.escala) > 0.01:
            self.creature.set_escala(self.escala_guardada())   # cambiado desde Ajustes
        nueva_card_escala = self.card_escala_guardada()
        if abs(nueva_card_escala - getattr(self, "card_scale", 1.15)) > 0.01:
            self.card_scale = nueva_card_escala
            self.aplicar_escala_tarjeta()
            self.refrescar_globo_activo()
        self.creature.mood = mood
        # Leer también cuenta: no reclamar repasos a quien acaba de leer.
        self.creature.enojado = enfado_por_estudio(
            self.con, t["pendientes"] + t["nuevas"], mood == "dormido")
        self.creature.energy = energia
        self.creature.abandono = 0.0 if mood == "dormido" else abandono
        self.creature.reduced_motion = (str(
            db.get_meta(self.con, "reduced_motion", "0")).lower() in ("1", "true")
            or not self.get_settings().get_property("gtk-enable-animations"))
        self.bubble.set_transition_duration(0 if self.creature.reduced_motion else 240)
        repasos = total_repasos(self.con)
        self.creature.accessory = accesorio_valido(
            str(db.get_meta(self.con, "pet_accessory", "ninguno")), repasos)
        self.creature.genero = self.voz_cfg.get("genero", "")
        self.creature.teaching = self.bubble.get_reveal_child()
        self.set_tooltip_text(
            f"{self.nombre} · {t['pendientes']} pendientes · {t['hoy']} hoy · "
            f"racha {t['racha']} d · {sin_estudiar(horas)}")

    def card_escala_guardada(self) -> float:
        try:
            return float(db.get_meta(self.con, "card_scale", 1.15))
        except (TypeError, ValueError):
            return 1.15

    def char_width(self, base: int = 32) -> int:
        return max(24, int(base * max(0.8, getattr(self, "card_scale", 1.15))))

    def fijar_tamano_tarjeta(self, valor: float):
        nueva = round(max(0.70, min(2.50, valor)), 2)
        db.set_meta(self.con, "card_scale", nueva)
        self.card_scale = nueva
        self.aplicar_escala_tarjeta()
        self.sonar("clic")
        self.refrescar_globo_activo()

    def cambiar_tamano_tarjeta(self, paso: float):
        nueva = round(self.card_scale + paso, 2)
        self.fijar_tamano_tarjeta(nueva)

    def refrescar_globo_activo(self):
        # Redibuja el globo si está abierto para aplicar el nuevo tamaño
        if not self.bubble.get_reveal_child():
            return
        if self.card and self.reto:
            self.render_reto()
        elif self.card:
            self.render_card()
        elif hasattr(self, "chat") and self.chat is not None:
            self.abrir_chat()

    def aplicar_escala_tarjeta(self):
        scale = getattr(self, "card_scale", 1.15)
        min_w = int(280 * scale)
        pad_h = int(14 * scale)
        pad_v = int(12 * scale)
        font_front = f"{1.06 * scale:.2f}rem"
        font_text = f"{0.96 * scale:.2f}rem"
        font_title = f"{0.80 * scale:.2f}rem"
        font_cita = f"{0.85 * scale:.2f}rem"
        font_btn = f"{0.90 * scale:.2f}rem"
        btn_pad_v = int(5 * scale)
        btn_pad_h = int(12 * scale)
        css_data = f"""
        /* Sin max-width: GTK4 no tiene esa propiedad (avisaba en cada tarjeta).
           El ancho lo limitan los max_width_chars de cada etiqueta. */
        window.as-pet box.as-bubble {{
            min-width: {min_w}px;
            padding: {pad_v}px {pad_h}px;
        }}
        window.as-pet .as-bubble-title {{
            font-size: {font_title};
        }}
        window.as-pet .as-bubble-front {{
            font-size: {font_front};
            line-height: 1.38;
        }}
        window.as-pet .as-bubble-text {{
            font-size: {font_text};
            line-height: 1.48;
        }}
        window.as-pet .as-bubble-cita {{
            font-size: {font_cita};
        }}
        window.as-pet .as-reto-afirma {{
            font-size: {font_text};
            padding: {int(8 * scale)}px {int(10 * scale)}px;
        }}
        window.as-pet .as-bubble button.pill, window.as-pet .as-bubble button.as-reto-opcion {{
            font-size: {font_btn};
            padding: {btn_pad_v}px {btn_pad_h}px;
        }}
        """
        self.card_css_provider.load_from_data(css_data.encode())

    def escala_guardada(self) -> float:
        try:
            return float(db.get_meta(self.con, "pet_scale", 1.0))
        except (TypeError, ValueError):
            return 1.0

    def alternar_sonido(self):
        sonido.guardar(self.con, activo=not self.sonido["activo"])
        self.sonido = sonido.config(self.con)
        self.sonar("clic")
        self.refrescar_menu()          # cambia la etiqueta de silencio

    def cambiar_tamano(self, paso):
        nueva = round(self.creature.escala + paso, 2)
        nueva = max(ESCALA_MIN, min(ESCALA_MAX, nueva))
        db.set_meta(self.con, "pet_scale", nueva)
        self.creature.set_escala(nueva)
        self.creature.play("salto", 0.5)

    def dormida(self) -> bool:
        hasta = float(db.get_meta(self.con, "pet_snooze_until", 0) or 0)
        return time.time() < hasta

    def intervalo_min(self) -> int:
        try:
            return max(5, int(db.get_meta(self.con, "pet_every", DEFAULT_EVERY_MIN)))
        except (TypeError, ValueError):
            return DEFAULT_EVERY_MIN

    # ------------------------------------------------------------------ bucles

    def on_check(self):
        self.refresh_stats()
        if getattr(self, "_ventana_historial", None) is not None:
            return True
        if self.dormida() or self.bubble.get_reveal_child():
            return True
        if not recordatorios.permitido(recordatorios.config(self.con)):
            return True
        if time.time() - self.last_nag < self.intervalo_min() * 60:
            return True
        t = self.stats
        self.sonar("aviso")
        self.creature.saludar()
        if (t["horas"] >= HORAS_HAMBRE
                and time.time() - self.ultimo_reproche > HORAS_REPROCHE * 3600):
            # Llevas días sin aparecer: antes que una tarjeta, te lo dice
            self.ultimo_reproche = time.time()
            self.sonar("aviso")
            if self.creature.enojado:
                self.creature.actuar("enojado")
            else:
                self.creature.desanimar()
            self.say(reproche(t["horas"]), titulo=f"{self.nombre} te echa de menos",
                     boton=("Va, enséñame algo", self.teach))
            return True
        if (t.get("sanguijuelas") and time.time() - self.ultimo_aviso_leech > 6 * 3600
                and random.random() < 0.35):
            # Las que se te atragantan no se arreglan estudiándolas más veces:
            # hay que reescribirlas, así que te lo recuerda de vez en cuando.
            self.ultimo_aviso_leech = time.time()
            cuantas = t["sanguijuelas"]
            cuales = ("una tarjeta que se te atraganta" if cuantas == 1
                      else f"{cuantas} tarjetas que se te atragantan")
            self.say(f"Hay {cuales}. Reescribirlas cuesta menos que seguir "
                     "fallándolas una y otra vez.",
                     titulo="Se te atragantan",
                     boton=("Verlas", self.abrir_sanguijuelas))
            return True
        if (time.time() - self.ultimo_diario > 24 * 3600 and random.random() < 0.25):
            # Una vez al día como mucho, te cuenta cómo va la semana: cierra el
            # ciclo de «he estudiado» y «ha servido para algo».
            self.ultimo_diario = time.time()
            self.diario()
            return True
        if t["pendientes"] == 0 and t["nuevas"] == 0:
            # Nada que repasar: entonces te deja algo para el rato, un dato de
            # cultura general o una frase de libro
            self.sabias_que() if random.random() < 0.6 else self.quote()
        elif random.random() < 0.30:
            # Aprender cosas sueltas también cuenta, y de estas te queda algo
            # solo si las guardas: por eso el dato trae su botón.
            self.sabias_que() if random.random() < 0.5 else self.quote()
        elif t["pendientes"] or t["nuevas"] or t["energia"] < 0.6:
            # A veces te explica algo y a veces te reta: así no se vuelve rutina
            if random.random() < 0.5:
                self.quiz()
            else:
                self.teach()
        elif t["hoy"] == 0:
            self.say("¿Estrenamos el día con un repaso?", boton=("Vamos", self.study))
        else:
            self.last_nag = time.time()
        return True

    def abrir_sanguijuelas(self, *_):
        """Abre la ventana principal en la lista de tarjetas atragantadas."""
        self.close_bubble()
        self.spawn("--leeches")

    # ------------------------------------------------------------------ globo

    def clear_bubble(self):
        if hasattr(self, "detener_voz"):
            self.detener_voz()
        while (hijo := self.bubble_box.get_first_child()) is not None:
            self.bubble_box.remove(hijo)

    def liberar_ia(self):
        """Pone la IA en reposo descargando el modelo de la memoria (keep_alive=0)."""
        cfg = ia.config(self.con)
        if cfg.get("activa"):
            ia.hilo(lambda: ia.descargar(cfg))

    def close_bubble(self, *_):
        if getattr(self, "conversacion", None) is not None:
            self.parar_conversacion()
        if getattr(self, "examen", None) is not None:
            self.parar_examen(cerrar_globo=False)
        if getattr(self, "recuerdo", None) is not None:
            self.parar_recuerdo(cerrar_globo=False)
        if hasattr(self, "detener_voz"):
            self.detener_voz()
        if self.chat is not None or self.ia_cuerpo is not None:
            self.liberar_ia()
        self.parar_cuenta()
        self.chat = None                     # se acaba la charla
        self.creature.charlando = False
        self.creature.hablando_hasta = 0     # por si cerraste a media respuesta
        self.ia_cuerpo = None
        self.card = None
        self.reto = None
        self.bubble.set_reveal_child(False)
        self.creature.teaching = False
        self.creature.play("ladear", 0.9)
        self.last_nag = time.time()
        GLib.timeout_add(260, self.finish_close_bubble)

    def open_bubble(self):
        self.save_position()
        origen = self.read_position()
        self.sonar("globo")
        self.bubble.set_reveal_child(True)
        self.creature.teaching = True
        self.creature.hablar(1.3)
        self.last_nag = time.time()
        self.keep_above()
        GLib.timeout_add(900, self.fit_on_screen, origen)

    def fit_on_screen(self, origen=None):
        """Si el globo se sale de la pantalla, acerca la ventana al borde."""
        if not self.bubble.get_reveal_child() or not self._position_ready:
            return False
        pos = self.read_position()
        if not pos:
            return False
        if origen is not None and pos != origen:
            # Lo arrastró mientras se abría el globo: no contradecir ese gesto
            # con el ajuste que quedó encolado antes de que lo moviera.
            self.save_position()
            return False
        monitor = self.get_display().get_monitor_at_surface(self.get_surface())
        if monitor is None:
            return False
        area = monitor.get_geometry()
        # GDK da tamaños lógicos; xwininfo y wmctrl usan píxeles X11.
        escala = self.get_surface().get_scale_factor()
        x = min(pos[0], (area.x + area.width - self.get_width() - 8) * escala)
        y = min(pos[1], (area.y + area.height - self.get_height() - 8) * escala)
        x, y = max((area.x + 8) * escala, x), max((area.y + 8) * escala, y)
        if (x, y) != pos:
            self.save_position()
            if self.move_to(x, y):
                self._auto_pos = (x, y)
        return False

    def bubble_header(self, titulo, color=None, mazo=None, nivel=None):
        """La cabecera de la tarjeta: de qué mazo es, qué toca hacer, y cerrar.

        Devuelve una columna: la fila con el chip del mazo y el título, y debajo
        una línea del color del mazo que separa la cabecera del contenido.
        """
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fila = Gtk.Box(spacing=8)

        if mazo:
            chip = Gtk.Label(label=mazo, css_classes=["as-chip-mazo"],
                             valign=Gtk.Align.CENTER, ellipsize=3, max_width_chars=18)
            if color:
                self.pintar(chip, f"label {{ background:{util.shade(color, 0.20)};"
                                  f" color:{util.shade(color, 0.98)}; }}")
            fila.append(chip)

        etiqueta = Gtk.Label(label=titulo, xalign=0, hexpand=True, wrap=True,
                             valign=Gtk.Align.CENTER, css_classes=["as-bubble-title"])
        fila.append(etiqueta)

        if getattr(self, "voz_cfg", {}).get("activo", True):
            self.btn_voz = Gtk.Button(icon_name="audio-volume-high-symbolic",
                                      tooltip_text="Escuchar (leer en voz alta)",
                                      css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
            self.btn_voz.connect("clicked", lambda *_: self.alternar_voz_globo())
            fila.append(self.btn_voz)

        self.btn_mic = Gtk.Button(icon_name="audio-input-microphone-symbolic",
                                  tooltip_text="Responder por voz (habla al micrófono)",
                                  css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
        self.btn_mic.connect("clicked", lambda *_: self.alternar_microfono())
        fila.append(self.btn_mic)

        self.btn_cursos = Gtk.Button(icon_name="media-playback-start-symbolic",
                                      tooltip_text="Cursos Online (Platzi & Udemy)",
                                      css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
        self.btn_cursos.connect("clicked", lambda *_: self.mostrar_menu_cursos())
        fila.append(self.btn_cursos)

        recientes = Gtk.Button(icon_name="document-open-recent-symbolic",
                                tooltip_text="Tarjetas recientes",
                                css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
        recientes.connect("clicked", self.abrir_historial)
        fila.append(recientes)

        cerrar = Gtk.Button(icon_name="window-close-symbolic",
                            css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
        cerrar.connect("clicked", self.close_bubble)
        fila.append(cerrar)
        caja.append(fila)

        if nivel:
            etiqueta.set_tooltip_text(nivel)

        linea = Gtk.Box(css_classes=["as-bubble-linea"])   # el filo del color del mazo
        if color:
            self.pintar(linea, f"box {{ background:{util.shade(color, 0.55)}; }}")
        caja.append(linea)
        return caja

    def alternar_voz_globo(self):
        if voz.esta_hablando():
            self.detener_voz()
            return
        texto = getattr(self, "texto_hablable", "") or self.obtener_texto_globo()
        if not texto:
            return
        self.voz_cfg = voz.config(self.con)
        if not self.voz_cfg.get("activo", True):
            return
        self.cara_de_la_voz(texto, getattr(self, "card", None))
        duracion = voz.hablar(texto, self.voz_cfg, on_done=self.on_voz_terminada,
                              card=getattr(self, "card", None))
        if duracion > 0:
            self.creature.hablar(duracion)
            if hasattr(self, "btn_voz") and self.btn_voz:
                self.btn_voz.set_icon_name("media-playback-stop-symbolic")
                self.btn_voz.set_tooltip_text("Detener voz")

    def alternar_microfono(self):
        import threading
        from . import ia, voz, voz_rec
        if not hasattr(self, "grabador_mic") or not self.grabador_mic:
            self.grabador_mic = voz_rec.GrabadorMicrofono()

        if self.grabador_mic.esta_grabando():
            ruta = self.grabador_mic.detener()
            if hasattr(self, "btn_mic") and self.btn_mic:
                self.btn_mic.set_icon_name("audio-input-microphone-symbolic")
                self.btn_mic.set_tooltip_text("Responder por voz (habla al micrófono)")
                self.btn_mic.remove_css_class("destructive-action")

            if ruta and getattr(self, "card", None):
                idioma = "en" if voz.es_tarjeta_ingles(self.card) else "es"
                cfg_ia = ia.config(self.con)
                esperada = self.card.get("back", "")

                def _tarea():
                    dicho = voz_rec.transcribir_audio(ruta, idioma=idioma)
                    return voz_rec.juzgar_respuesta(dicho, esperada, card=self.card, cfg_ia=cfg_ia)

                def _fin(juicio):
                    if juicio["acierto"]:
                        self.creature.celebrar()
                        self.sonar("acierto")
                    else:
                        self.creature.desanimar()
                        self.sonar("fallo")
                    self.cara_de_la_voz(juicio["feedback"], self.card)
                    duracion = voz.hablar(juicio["feedback"], self.voz_cfg, card=self.card,
                                          on_done=self.on_voz_terminada)
                    if duracion > 0:
                        self.creature.hablar(duracion)

                threading.Thread(target=lambda: GLib.idle_add(_fin, _tarea()), daemon=True).start()
            elif ruta:
                def _tarea_gen():
                    return voz_rec.transcribir_audio(ruta, idioma="es")

                def _fin_gen(dicho):
                    if not dicho:
                        return
                    dicho_l = dicho.lower()
                    es_c = any(k in dicho_l for k in ("platzi", "udemy", "curso", "clase", "reproductor", "video"))
                    es_a = any(k in dicho_l for k in ("platzi", "udemy", "siguiente", "proximo", "próximo", "ultimo", "último", "abre", "abrir", "pon", "poner", "ver", "reproduce", "reproducir", "mostrar", "muéstrame"))
                    if es_c and es_a:
                        plat = "platzi" if "platzi" in dicho_l else ("udemy" if "udemy" in dicho_l else None)
                        self.abrir_reproductor_cursos(plat)
                    elif self.chat is not None:
                        self.enviar_chat(dicho)
                    else:
                        self.abrir_chat()
                        self.enviar_chat(dicho)

                threading.Thread(target=lambda: GLib.idle_add(_fin_gen, _tarea_gen()), daemon=True).start()
        else:
            if hasattr(self, "detener_voz"):
                self.detener_voz()
            ruta = self.grabador_mic.iniciar()
            if hasattr(self, "btn_mic") and self.btn_mic:
                self.btn_mic.set_icon_name("media-record-symbolic")
                self.btn_mic.add_css_class("destructive-action")
                self.btn_mic.set_tooltip_text("Grabando tu respuesta… pulsa para terminar y evaluar")
            if hasattr(self, "creature") and self.creature:
                self.creature.pensar()

    def detener_voz(self):
        from . import voz
        voz.detener()
        if hasattr(self, "creature") and self.creature:
            self.creature.hablando_hasta = 0
        if hasattr(self, "btn_voz") and self.btn_voz:
            self.btn_voz.set_icon_name("audio-volume-high-symbolic")
            self.btn_voz.set_tooltip_text("Escuchar (leer en voz alta)")

    def cara_de_la_voz(self, texto="", card=None):
        """Pone la cara de la voz con la que va a hablar ahora mismo.

        La voz se elige por frase —una tarjeta de inglés la lee la voz inglesa—,
        así que la cara va con ella y no con el idioma configurado.
        """
        if not getattr(self, "creature", None):
            return
        idioma = voz.detectar_idioma(card=card, texto=texto)
        self.creature.genero = voz.genero_voz(idioma)

    def cara_en_reposo(self):
        """Al callarse, vuelve a la cara de su voz de siempre."""
        if getattr(self, "creature", None):
            self.creature.genero = self.voz_cfg.get("genero", "")

    def on_voz_terminada(self):
        self.cara_en_reposo()
        if hasattr(self, "creature") and self.creature:
            self.creature.hablando_hasta = 0
        if hasattr(self, "btn_voz") and self.btn_voz:
            self.btn_voz.set_icon_name("audio-volume-high-symbolic")
            self.btn_voz.set_tooltip_text("Escuchar (leer en voz alta)")

    def obtener_texto_globo(self) -> str:
        partes = []
        def recorrer(widget):
            if isinstance(widget, Gtk.Label):
                lbl = widget.get_label()
                if lbl and not widget.has_css_class("as-chip-mazo") and not widget.has_css_class("as-bubble-title"):
                    partes.append(lbl)
            hijo = widget.get_first_child() if hasattr(widget, "get_first_child") else None
            while hijo:
                recorrer(hijo)
                hijo = hijo.get_next_sibling()
        if hasattr(self, "bubble_box"):
            recorrer(self.bubble_box)
        return " ".join(partes)

    def voz_auto_si_toca(self):
        if hasattr(self, "voz_cfg") and self.voz_cfg.get("activo", True) and self.voz_cfg.get("auto", False):
            GLib.timeout_add(260, self._auto_hablar_timer)

    def _auto_hablar_timer(self):
        if hasattr(self, "bubble") and self.bubble.get_reveal_child():
            if not voz.esta_hablando():
                self.alternar_voz_globo()
        return False

    @staticmethod
    def pintar(widget, css):
        proveedor = Gtk.CssProvider()
        proveedor.load_from_data(css.encode())
        widget.get_style_context().add_provider(
            proveedor, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def say(self, texto, titulo=None, boton=None):
        """Un mensaje corto, con un botón opcional."""
        titulo = titulo or f"{self.nombre} dice"
        self.card = None
        self.texto_hablable = texto
        self.clear_bubble()
        self.bubble_box.append(self.bubble_header(titulo))
        self.bubble_box.append(Gtk.Label(label=util.to_markup(texto), use_markup=True,
                                         wrap=True, xalign=0, max_width_chars=self.char_width(30),
                                         css_classes=["as-bubble-text"]))
        if boton:
            etiqueta, cb = boton
            b = Gtk.Button(label=etiqueta, css_classes=["suggested-action", "pill"])
            b.connect("clicked", lambda *_: cb())
            self.bubble_box.append(b)
        self.open_bubble()
        self.voz_auto_si_toca()

    def quote(self):
        """Una frase de un libro, con su autor y su obra."""
        frase, autor, obra = citas.aleatoria(self.ultimas_citas)
        self.ultimas_citas = (self.ultimas_citas + [frase])[-12:]
        self.card = None
        self.texto_hablable = f"«{frase}». {autor}, {obra}."
        self.clear_bubble()
        self.bubble_box.append(self.bubble_header("📖 De un libro"))
        self.bubble_box.append(Gtk.Label(
            label=f"<i>«{GLib.markup_escape_text(frase)}»</i>", use_markup=True,
            wrap=True, xalign=0, max_width_chars=self.char_width(32), css_classes=["as-bubble-front"]))
        self.bubble_box.append(Gtk.Label(
            label=f"— {GLib.markup_escape_text(autor)}, "
                  f"<i>{GLib.markup_escape_text(obra)}</i>",
            use_markup=True, wrap=True, xalign=1, max_width_chars=self.char_width(34),
            css_classes=["as-bubble-cita"]))
        fila = Gtk.Box(spacing=6, homogeneous=True)
        otra = Gtk.Button(label="Otra frase", css_classes=["pill"])
        otra.connect("clicked", lambda *_: self.quote())
        fila.append(otra)
        estudiar = Gtk.Button(label="Enséñame algo",
                              css_classes=["suggested-action", "pill"])
        estudiar.connect("clicked", lambda *_: self.teach())
        fila.append(estudiar)
        self.bubble_box.append(fila)
        self.creature.pensar()
        self.open_bubble()
        self.voz_auto_si_toca()

    def sabias_que(self, categoria: str | None = None):
        """Un dato de cultura general, con la opción de quedárselo."""
        from . import sabias
        dato, cat, porque = sabias.aleatorio(self.ultimos_datos, categoria)
        self.ultimos_datos = (self.ultimos_datos + [dato])[-20:]
        self.card = None
        self.reto = None
        self.dato_actual = (dato, cat, porque)
        self.texto_hablable = f"¿Sabías que… {dato} {porque}"

        self.clear_bubble()
        self.bubble_box.append(self.bubble_header(f"💡 ¿Sabías que… · {cat}"))
        self.bubble_box.append(Gtk.Label(
            label=GLib.markup_escape_text(dato), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(32), css_classes=["as-bubble-front"]))
        self.bubble_box.append(Gtk.Label(
            label=f"<i>{GLib.markup_escape_text(porque)}</i>", use_markup=True, wrap=True,
            xalign=0, max_width_chars=self.char_width(34), css_classes=["as-bubble-text"]))

        fila = Gtk.Box(spacing=6, homogeneous=True)
        otro = Gtk.Button(label="Otro dato", css_classes=["pill"])
        otro.connect("clicked", lambda *_: self.sabias_que())
        fila.append(otro)
        guardar = Gtk.Button(label="📌 Guárdamela", css_classes=["pill", "suggested-action"])
        guardar.connect("clicked", lambda *_: self.guardar_dato())
        fila.append(guardar)
        self.bubble_box.append(fila)

        if ia.config(self.con)["activa"]:
            mas = Gtk.Button(label="Cuéntame más", css_classes=["flat", "as-bubble-link"])
            mas.connect("clicked", lambda *_: self.ampliar_dato())
            self.bubble_box.append(mas)

        # Por categorías, para cuando quieras insistir en algo concreto
        temas = Gtk.Box(spacing=4)
        temas.append(Gtk.Label(label="Tema:", css_classes=["as-bubble-cita"]))
        combo = Gtk.DropDown.new_from_strings(["Cualquiera", *sabias.categorias()])
        combo.set_selected(0 if not categoria
                           else list(sabias.categorias()).index(categoria) + 1)
        combo.connect("notify::selected", self.on_tema_dato)
        temas.append(combo)
        self.bubble_box.append(temas)

        self.creature.pensar()
        self.open_bubble()
        self.voz_auto_si_toca()

    def on_tema_dato(self, combo, _p):
        from . import sabias
        indice = combo.get_selected()
        self.sabias_que(None if indice == 0 else list(sabias.categorias())[indice - 1])

    def guardar_dato(self):
        """Mete el dato en el mazo de cultura general, para repasarlo luego.

        Si la IA está activa se le pide antes que redacte la pregunta: un dato
        guardado tal cual da una tarjeta que se lee y no se responde, y lo que
        fija el recuerdo es tener que producirlo.
        """
        from . import sabias
        if not getattr(self, "dato_actual", None):
            return
        dato, cat, porque = self.dato_actual
        cfg = ia.config(self.con)

        def _guardar(pregunta=""):
            guardada = sabias.guardar_como_tarjeta(self.con, dato, cat, porque, pregunta)
            total = sabias.cuantas_guardadas(self.con)
            self.sonar("listo" if guardada else "clic")
            self.say("Ya la tenías guardada." if not guardada else
                     f"Guardada en Cultura general. Ya llevas {total}.",
                     titulo="💡 Al mazo",
                     boton=("Otro dato", lambda: self.sabias_que()))
            self.refresh_stats()

        if cfg["activa"]:
            ia.hilo(lambda: ia.pregunta_de_dato(cfg, dato), _guardar, lambda e: _guardar())
        else:
            _guardar()

    def ampliar_dato(self):
        """Le pide a la IA local que cuente algo más sobre el dato."""
        if not getattr(self, "dato_actual", None):
            return
        dato, cat, _ = self.dato_actual
        cfg = ia.config(self.con)
        self.creature.pensar()

        def _fin(texto):
            self.texto_hablable = texto
            self.say(texto, titulo=f"💡 Más sobre esto · {cat}",
                     boton=("Otro dato", lambda: self.sabias_que()))
            self.voz_auto_si_toca()

        ia.hilo(lambda: ia.contar_mas_de(cfg, dato, cat), _fin,
                lambda e: _fin(f"No he podido ampliarlo: {e}"))

    def teach(self):
        """Saca una tarjeta y te la explica: pregunta y respuesta, las dos."""
        current_id = self.card["id"] if self.card else None
        if not hasattr(self, "recent_card_ids"):
            self.recent_card_ids = []
        if current_id and current_id not in self.recent_card_ids:
            self.recent_card_ids.append(current_id)
            if len(self.recent_card_ids) > 30:
                self.recent_card_ids.pop(0)

        anterior = self.card["deck_key"] if self.card else None
        self.card = scheduler.next_card(self.con, exclude_ids=self.recent_card_ids,
                                        exclude_id=current_id, evitar_deck=anterior)
        if not self.card and current_id:
            # Si se excluyeron todas, limpiamos historial reciente y reintentamos
            self.recent_card_ids = [current_id]
            self.card = scheduler.next_card(self.con, exclude_id=current_id)

        if not self.card:
            self.say("No me quedan tarjetas que enseñarte. Añade alguna 😊",
                     boton=("Abrir AppStudy", self.open_main))
            return
        self.reto = None
        self.shown_at = time.time()
        historial.registrar(self.con, self.card["id"])
        self.render_card()

    def render_card(self):
        """Enseñar es enseñar: la respuesta está a la vista desde el principio."""
        c = self.card
        f = cloze.completo(c["front"]) if cloze.tiene_huecos(c["front"]) else c["front"]
        b = c["back"] or c.get("hint", "")
        self.texto_hablable = f"{f}. {b}" if b else f
        self.clear_bubble()
        titulo = {"quiz": "Fíjate en esto", "lesson": "¿Sabías esto?"}.get(
            c["kind"], "Repasemos esto")
        self.bubble_box.append(self.bubble_header(
            titulo, c["deck_color"], mazo=f"{c['deck_icon']} {c['deck_name']}",
            nivel=db.level_name(c["deck_levels"], c["level"])))

        texto_front = (cloze.resaltado(c["front"]) if cloze.tiene_huecos(c["front"])
                       else c["front"])
        self.bubble_box.append(Gtk.Label(
            label=util.to_markup(texto_front), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(30), css_classes=["as-bubble-front"]))

        if c["back"]:
            self.bubble_box.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
            self.bubble_box.append(Gtk.Label(
                label=util.to_markup(c["back"]), use_markup=True, wrap=True, xalign=0,
                max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))
        elif c["hint"]:
            self.bubble_box.append(Gtk.Label(
                label=util.to_markup(c["hint"]), use_markup=True, wrap=True, xalign=0,
                max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))

        fila = Gtk.Box(spacing=6, homogeneous=True)
        for rating, etiqueta, clase in (
                (scheduler.AGAIN, "No lo sabía", "as-rate-again"),
                (scheduler.GOOD, "Lo sabía", "as-rate-good")):
            b = Gtk.Button(label=etiqueta, css_classes=["pill", clase])
            b.connect("clicked", lambda _b, r=rating: self.rate(r))
            fila.append(b)
        self.bubble_box.append(fila)

        if ia.config(self.con)["activa"]:
            fila_ia = Gtk.Box(spacing=10, homogeneous=True)
            fila_ia.append(self.boton_explicar())
            fila_ia.append(self.boton_chat())
            fila_ia.append(self.boton_conversar())
            self.bubble_box.append(fila_ia)

        otra = Gtk.Box(spacing=10, homogeneous=True)
        for etiqueta, cb in (("Otra tarjeta", self.teach), ("⚡ Ponme a prueba", self.quiz)):
            b = Gtk.Button(label=etiqueta, css_classes=["flat", "as-bubble-link"])
            b.connect("clicked", lambda _b, f=cb: f())
            otra.append(b)
        self.bubble_box.append(otra)

        self.bubble_box.append(self.pie_leer())
        self.open_bubble()
        self.voz_auto_si_toca()

    def celebrar_logro(self) -> bool:
        """Si acabas de pasar una marca, la celebra. Solo la primera vez.

        Va después de calificar, que es cuando cambian la racha y los intervalos
        y por tanto cuando se cruzan casi todos los logros.
        """
        nuevos = logros.revisar(self.con)
        if not nuevos:
            return False
        le = nuevos[0]                      # de dos a la vez, se enseña uno
        self.creature.celebrar()
        self.sonar("celebra")
        self.say(logros.frase_de(le, le.get("dato")),
                 titulo=f"{le['icono']} {le['titulo']}",
                 boton=("Seguir", self.teach))
        return True

    def diario(self):
        """El resumen de la semana, contado en un par de frases."""
        self.card = None
        texto = estadisticas.contar_semana(self.con)
        resumen = estadisticas.resumen_semanal(self.con)
        if resumen["total"]:
            self.creature.celebrar() if resumen["activos"] >= 5 else self.creature.pensar()
        else:
            self.creature.pensar()
        self.say(texto, titulo="📔 Cómo va la semana",
                 boton=("Enséñame algo", self.teach))

    def celebrar_vuelta(self, horas_antes: float) -> bool:
        """Si vuelves después de días fuera, lo celebra a lo grande."""
        if horas_antes < HORAS_HAMBRE:
            return False
        self.creature.play("salto", 0.62)
        self.creature.emitir("corazon", 5)
        self.sonar("celebra")
        return True

    def rate(self, rating):
        if not self.card:
            return
        card = self.card
        ausencia = self.stats.get("horas", 0.0)     # antes de apuntar el repaso
        ms = int((time.time() - self.shown_at) * 1000)
        st = scheduler.apply_review(self.con, card["id"], rating, ms)
        self.refresh_stats()
        if rating >= scheduler.GOOD:
            self.creature.celebrar()
            self.sonar("acierto")
        else:
            self.creature.desanimar()
            self.sonar("fallo")
        cuando = scheduler.due_label(st["due"])
        if self.celebrar_logro():
            return
        if self.celebrar_vuelta(ausencia):
            dias = int(ausencia // 24)
            texto = (f"¡Has vuelto! Llevabas {dias} día{'s' if dias > 1 else ''} "
                     f"fuera. Te lo vuelvo a preguntar en <b>{cuando}</b>.")
            titulo = "🎉"
        else:
            texto = f"Anotado. Te lo vuelvo a preguntar en <b>{cuando}</b>."
            titulo = "👌"
        self.say(texto, titulo=titulo, boton=("⚡ Ponme a prueba", self.quiz))
        # say() deja el globo limpio: se devuelve la tarjeta para el enlace del pie
        self.card = card
        self.bubble_box.append(self.pie_leer())

    # ------------------------------------------------------------------- retos

    def quiz(self):
        """Te pone a prueba, y cada vez de una manera distinta."""
        current_id = self.card["id"] if self.card else None
        if not hasattr(self, "recent_card_ids"):
            self.recent_card_ids = []
        if current_id and current_id not in self.recent_card_ids:
            self.recent_card_ids.append(current_id)
            if len(self.recent_card_ids) > 30:
                self.recent_card_ids.pop(0)

        anterior = self.card["deck_key"] if self.card else None
        self.card = scheduler.next_card(self.con, exclude_ids=self.recent_card_ids,
                                        exclude_id=current_id, evitar_deck=anterior)
        if not self.card and current_id:
            self.recent_card_ids = [current_id]
            self.card = scheduler.next_card(self.con, exclude_id=current_id)

        if not self.card:
            self.say("No me quedan tarjetas con las que retarte. Añade alguna 😊",
                     boton=("Abrir AppStudy", self.open_main))
            return
        historial.registrar(self.con, self.card["id"])
        if not util.plain(self.card["back"]):
            # Una lección no se puede preguntar, así que se lee
            self.reto = None
            self.shown_at = time.time()
            self.render_card()
            return
        self.reto = reto.preparar(self.con, self.card, evitar=self.ultimo_formato)
        self.ultimo_formato = self.reto["formato"]
        self.shown_at = time.time()
        self.render_reto()

    def render_reto(self):
        r, c = self.reto, self.card
        ops = ". ".join(r.get("opciones", [])) if r.get("opciones") else ""
        self.texto_hablable = f"{r.get('pregunta', '')}. {ops}".strip()
        self.clear_bubble()
        self.bubble_box.append(self.bubble_header(
            f"{r['icono']} {r['titulo']}", c["deck_color"],
            mazo=f"{c['deck_icon']} {c['deck_name']}",
            nivel=db.level_name(c["deck_levels"], c["level"])))
        self.bubble_box.append(self.cuenta_atras())
        self.bubble_box.append(self.enunciado())
        self.bubble_box.append({
            "opciones": self.reto_opciones,
            "invertido": self.reto_opciones,
            "vf": self.reto_vf,
            "hueco": lambda: self.reto_escribir("La palabra que falta…"),
            "escribir": self.reto_escribir,
            "relampago": self.reto_relampago,
        }[r["formato"]]())
        self.bubble_box.append(self.pie_leer())
        self.creature.pensar()
        self.arrancar_cuenta(r["segundos"])
        self.open_bubble()
        self.voz_auto_si_toca()

    def enunciado(self):
        """Lo que hay que leer antes de responder, según el formato del reto."""
        r = self.reto
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        if r["formato"] == "invertido":
            # Aquí se enseña la respuesta y hay que reconocer la pregunta
            caja.append(Gtk.Label(label=r["pregunta"], wrap=True, xalign=0,
                                  max_width_chars=self.char_width(32), css_classes=["as-reto-afirma"]))
            caja.append(Gtk.Label(label="¿De qué tarjeta es?", xalign=0, wrap=True,
                                  max_width_chars=self.char_width(30), css_classes=["as-bubble-front"]))
            return caja
        caja.append(Gtk.Label(
            label=util.to_markup(r["pregunta"]), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(30), css_classes=["as-bubble-front"]))
        if r["formato"] == "hueco":
            caja.append(Gtk.Label(label=r["frase"], wrap=True, xalign=0,
                                  max_width_chars=self.char_width(32), css_classes=["as-reto-afirma"]))
        return caja

    # --- los seis formatos

    def reto_opciones(self):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for i, texto in enumerate(self.reto["opciones"]):
            b = Gtk.Button(css_classes=["pill", "as-reto-opcion"])
            b.set_child(Gtk.Label(label=texto, wrap=True, xalign=0, max_width_chars=self.char_width(28)))
            b.connect("clicked", lambda _b, i=i: self.resolver(
                i == self.reto["correcta"], elegida=self.reto["opciones"][i]))
            caja.append(b)
        return caja

    def reto_vf(self):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        caja.append(Gtk.Label(label=self.reto["afirmacion"], wrap=True, xalign=0,
                              max_width_chars=self.char_width(30), css_classes=["as-reto-afirma"]))
        fila = Gtk.Box(spacing=6, homogeneous=True)
        for etiqueta, valor, clase in (("Verdadero", True, "as-rate-good"),
                                       ("Falso", False, "as-rate-again")):
            b = Gtk.Button(label=etiqueta, css_classes=["pill", clase])
            b.connect("clicked", lambda _b, v=valor: self.resolver(
                v == self.reto["verdadera"], elegida=("Verdadero" if v else "Falso")))
            fila.append(b)
        caja.append(fila)
        return caja

    def reto_escribir(self, pista="Escríbelo aquí…"):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        entrada = Gtk.Entry(placeholder_text=pista, css_classes=["as-reto-entrada"])
        entrada.connect("activate", lambda *_: self.comprobar_escrito(entrada))
        caja.append(entrada)
        fila = Gtk.Box(spacing=6, homogeneous=True)
        rendirse = Gtk.Button(label="No caigo", css_classes=["pill"])
        rendirse.connect("clicked", lambda *_: self.resolver(False))
        fila.append(rendirse)
        comprobar = Gtk.Button(label="Comprobar", css_classes=["pill", "as-rate-good"])
        comprobar.connect("clicked", lambda *_: self.comprobar_escrito(entrada))
        fila.append(comprobar)
        caja.append(fila)
        GLib.timeout_add(350, lambda: (entrada.grab_focus(), False)[1])
        return caja

    def comprobar_escrito(self, entrada):
        if self.reto is None:
            return
        texto = entrada.get_text().strip()
        if not texto:
            return
        # En el reto del hueco basta con acertar la palabra que falta
        objetivo = self.reto.get("palabra") or self.reto["respuesta"]
        self.resolver(reto.acierta_escrito(texto, objetivo), elegida=texto)

    def reto_relampago(self):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        caja.append(Gtk.Label(
            label="Piénsalo antes de que se acabe el tiempo.", wrap=True, xalign=0,
            max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))
        b = Gtk.Button(label="Ya lo tengo", css_classes=["pill", "as-rate-good"])
        b.connect("clicked", lambda *_: self.revelar_relampago())
        caja.append(b)
        return caja

    def revelar_relampago(self, agotado=False):
        """Enseña la respuesta y te deja decir si la tenías."""
        self.parar_cuenta()
        c = self.card
        self.clear_bubble()
        self.bubble_box.append(self.bubble_header(
            "⏱ Se acabó el tiempo" if agotado else "⚡ A ver si coincidimos",
            c["deck_color"], mazo=f"{c['deck_icon']} {c['deck_name']}"))
        texto_front = (cloze.resaltado(c["front"]) if cloze.tiene_huecos(c["front"])
                       else c["front"])
        self.bubble_box.append(Gtk.Label(
            label=util.to_markup(texto_front), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(30), css_classes=["as-bubble-front"]))
        self.bubble_box.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
        self.bubble_box.append(Gtk.Label(
            label=util.to_markup(c["back"]), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))
        fila = Gtk.Box(spacing=6, homogeneous=True)
        for etiqueta, ok, clase in (("No la tenía", False, "as-rate-again"),
                                    ("La tenía", True, "as-rate-good")):
            b = Gtk.Button(label=etiqueta, css_classes=["pill", clase])
            b.connect("clicked", lambda _b, v=ok: self.resolver(v, sin_respuesta=True))
            fila.append(b)
        self.bubble_box.append(fila)
        self.bubble_box.append(self.pie_leer())

    # --- la cuenta atrás

    def cuenta_atras(self):
        """La barra de tiempo del reto, que se vacía y avisa al final."""
        fila = Gtk.Box(spacing=8)
        self.barra_tiempo = Gtk.ProgressBar(hexpand=True, fraction=1.0,
                                            valign=Gtk.Align.CENTER,
                                            css_classes=["as-reto-tiempo"])
        fila.append(self.barra_tiempo)
        self.reloj = Gtk.Label(label="", css_classes=["as-reto-reloj"])
        fila.append(self.reloj)
        return fila

    def arrancar_cuenta(self, segundos):
        self.parar_cuenta()
        self.reto_total = float(segundos)
        self.reto_fin = time.time() + segundos
        self.reto_timer = GLib.timeout_add(100, self.tick_reto)

    def parar_cuenta(self):
        if self.reto_timer is not None:
            GLib.source_remove(self.reto_timer)
            self.reto_timer = None

    def tick_reto(self):
        if self.barra_tiempo is None or self.reto is None:
            self.reto_timer = None
            return False
        restante = self.reto_fin - time.time()
        self.barra_tiempo.set_fraction(max(0.0, restante / self.reto_total))
        self.reloj.set_label(f"{max(0, math.ceil(restante))} s")
        if restante <= self.reto_total * 0.34:
            self.barra_tiempo.add_css_class("urgente")
        if restante > 0:
            return True
        self.reto_timer = None
        if self.reto["formato"] == "relampago":
            self.revelar_relampago(agotado=True)
        else:
            self.resolver(False, agotado=True)
        return False

    # --- el resultado

    def resolver(self, acierto, elegida=None, agotado=False, sin_respuesta=False):
        """Cierra el reto: lo apunta en el planificador y te enseña la respuesta."""
        if self.card is None:
            return
        self.parar_cuenta()
        ausencia = self.stats.get("horas", 0.0)      # antes de apuntar el repaso
        segundos = time.time() - self.shown_at
        # Rápido y bien vale por «fácil»: así deja de preguntarlo antes
        rapido = acierto and not sin_respuesta and segundos <= self.reto["segundos"] * 0.4
        rating = (scheduler.EASY if rapido
                  else scheduler.GOOD if acierto else scheduler.AGAIN)
        card = self.card
        st = scheduler.apply_review(self.con, card["id"], rating, int(segundos * 1000))
        self.refresh_stats()
        if acierto:
            self.creature.celebrar()
            self.sonar("acierto")
        else:
            self.creature.desanimar()
            self.sonar("fallo")

        self.clear_bubble()
        if agotado:
            titulo, clase = "⏱ Se acabó el tiempo", "as-reto-mal"
        elif acierto:
            titulo, clase = ("⚡ ¡Rápido y bien!" if rapido else "✅ ¡Correcto!"), "as-reto-ok"
        else:
            titulo, clase = "❌ Casi", "as-reto-mal"
        self.bubble_box.append(self.bubble_header(titulo))
        texto_front = (cloze.resaltado(card["front"]) if cloze.tiene_huecos(card["front"])
                       else card["front"])
        self.bubble_box.append(Gtk.Label(
            label=util.to_markup(texto_front), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(30), css_classes=["as-bubble-front"]))
        if not acierto and elegida:
            self.bubble_box.append(Gtk.Label(
                label=f"Dijiste <s>{GLib.markup_escape_text(elegida)}</s>",
                use_markup=True, wrap=True, xalign=0, max_width_chars=self.char_width(32),
                css_classes=["as-bubble-cita", clase]))
        self.bubble_box.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
        # La respuesta se enseña siempre, se acierte o no: para eso está aquí
        self.bubble_box.append(Gtk.Label(
            label=util.to_markup(card["back"]), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))
        self.bubble_box.append(Gtk.Label(
            label=f"{segundos:.1f} s · vuelve en {scheduler.due_label(st['due'])}",
            xalign=0, css_classes=["as-bubble-cita"]))
        if self.celebrar_vuelta(ausencia):
            dias = int(ausencia // 24)
            self.bubble_box.append(Gtk.Label(
                label=f"🎉 Y rompes {dias} día{'s' if dias > 1 else ''} sin estudiar",
                xalign=0, wrap=True, max_width_chars=self.char_width(32),
                css_classes=["as-bubble-cita", "as-reto-ok"]))

        fila = Gtk.Box(spacing=6, homogeneous=True)
        otro = Gtk.Button(label="Otro reto", css_classes=["pill"])
        otro.connect("clicked", lambda *_: self.quiz())
        fila.append(otro)
        ensenar = Gtk.Button(label="Enséñame", css_classes=["pill", "suggested-action"])
        ensenar.connect("clicked", lambda *_: self.teach())
        fila.append(ensenar)
        self.bubble_box.append(fila)
        if ia.config(self.con)["activa"]:
            fila_ia = Gtk.Box(spacing=10, homogeneous=True)
            fila_ia.append(self.boton_explicar())
            fila_ia.append(self.boton_chat())
            fila_ia.append(self.boton_conversar())
            self.bubble_box.append(fila_ia)

        self.card = card       # el pie necesita saber de qué tarjeta se habla
        self.reto = None
        self.bubble_box.append(self.pie_leer())
        self.open_bubble()

    # -------------------------------------------------------------------- IA

    def boton_explicar(self):
        b = Gtk.Button(label="🧠 Explícamelo mejor", css_classes=["flat", "as-bubble-link"])
        b.connect("clicked", lambda *_: self.explicar())
        return b

    def explicar(self):
        """Le pide al modelo local otra explicación de la tarjeta que estás viendo."""
        card = self.card
        if not card:
            return
        cuerpo = self.globo_ia(f"{card['deck_icon']} Otra manera de verlo",
                              util.plain(card["front"]))
        self.creature.pensar()
        cfg = ia.config(self.con)          # SQLite no se puede tocar desde otro hilo
        ia.hilo(lambda: ia.explicar(cfg, card, trozo=self.escribir_ia),
                lambda texto: self.fin_ia(cuerpo, texto, card),
                lambda e: self.fin_ia(cuerpo, f"<i>{GLib.markup_escape_text(str(e))}</i>", card))

    def boton_chat(self):
        b = Gtk.Button(label="💬 Modo chatbot", css_classes=["flat", "as-bubble-link"])
        b.connect("clicked", lambda *_: self.abrir_chat())
        return b

    def boton_conversar(self):
        b = Gtk.Button(label="🎙️ Hablar con Bit", css_classes=["flat", "as-bubble-link"])
        b.connect("clicked", lambda *_: self.alternar_conversacion())
        return b

    # ------------------------------------------------- conversación hablada

    # Lo que dices para cerrar la charla sin tocar nada. Se compara con el turno
    # entero, no por palabras sueltas, para que "adiós" dentro de una frase
    # ("¿cómo se dice adiós en inglés?") no te corte la conversación.
    DESPEDIDAS = {
        "adios", "adios bit", "hasta luego", "hasta luego bit", "chao", "chau",
        "nos vemos", "ya esta", "ya está", "eso es todo", "gracias bit",
        "listo gracias", "para", "para ya", "deja de escuchar", "salir del chat",
    }

    @staticmethod
    def _normalizar(texto: str) -> str:
        limpio = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                         if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9 ]+", "", limpio).strip()

    @classmethod
    def es_despedida(cls, texto: str) -> bool:
        return cls._normalizar(texto) in {cls._normalizar(d) for d in cls.DESPEDIDAS}

    def salir_del_todo(self):
        """Cierra Bit soltando antes el micrófono y la IA."""
        self.parar_palabra_clave()
        self.parar_conversacion()
        if getattr(self, "examen", None) is not None:
            self.parar_examen(cerrar_globo=False)
        if getattr(self, "recuerdo", None) is not None:
            self.parar_recuerdo(cerrar_globo=False)
        self.get_application().quit()

    def arrancar_palabra_clave(self):
        """Deja el oído puesto esperando un «hola bit», si toca."""
        from . import voz_rec
        if self.oido is not None or self.conversacion is not None:
            return False
        self.voz_cfg = voz.config(self.con)
        if not self.voz_cfg.get("clave", True) or not ia.config(self.con)["activa"]:
            return False
        if not voz_rec.EscuchaPalabraClave.disponible("es"):
            return False
        oido = voz_rec.EscuchaPalabraClave(
            idioma="es", al_activar=lambda: GLib.idle_add(self.despertar_por_voz))
        self.oido = oido if oido.iniciar() else None
        return False

    def parar_palabra_clave(self):
        oido, self.oido = self.oido, None
        if oido is not None:
            oido.detener()

    def despertar_por_voz(self):
        """Has dicho «hola bit»: suelta el micrófono del oído y ponte a charlar."""
        self.parar_palabra_clave()
        if self.conversacion is not None:
            return False
        self.creature.play("salto", 0.5)
        self.sonar("listo")
        self.alternar_conversacion()
        return False

    # ------------------------------------------------------- examen oral

    def empezar_recuerdo_libre(self):
        """Cierra el libro y suelta todo lo que recuerdes; luego se contrasta."""
        from . import recuerdo
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y contrastamos lo que recuerdes.",
                     titulo="🧠 Sin IA", boton=("Abrir AppStudy", self.open_main))
            return
        temas = recuerdo.temas_disponibles(self.con)
        if not temas:
            self.say("Necesito un mazo con algo de material para esto.",
                     titulo="🧠 Nada que recordar")
            return
        self.elegir_tema_recuerdo(temas)

    def elegir_tema_recuerdo(self, temas: list):
        """De qué tema vas a intentar acordarte."""
        self.clear_bubble()
        self.card = None
        self.reto = None
        self.bubble_box.append(self.bubble_header("🧠 Recuerdo libre"))
        self.bubble_box.append(Gtk.Label(
            label="Elige un tema, cierra los ojos y cuéntame todo lo que te venga. "
                  "Luego te digo qué te dejaste.",
            wrap=True, xalign=0, max_width_chars=self.char_width(32),
            css_classes=["as-bubble-text"]))
        for tema in temas[:5]:
            b = Gtk.Button(label=f"{tema['name']} · {tema['cuantas']} tarjetas",
                           css_classes=["pill"])
            b.connect("clicked", lambda _b, t=tema: self.arrancar_recuerdo(t))
            self.bubble_box.append(b)
        cerrar = Gtk.Button(label="Ahora no", css_classes=["flat", "as-bubble-link"])
        cerrar.connect("clicked", self.close_bubble)
        self.bubble_box.append(cerrar)
        self.open_bubble()

    def arrancar_recuerdo(self, tema: dict):
        from . import recuerdo, voz_rec
        self.parar_conversacion()
        self.parar_palabra_clave()
        self.recuerdo = {"tema": tema,
                         "material": recuerdo.material_de(self.con, deck_key=tema["key"]),
                         "dicho": []}
        self.render_recuerdo()
        self.escucha_recuerdo = voz_rec.EscuchaContinua(
            idioma="es",
            al_estado=lambda e: GLib.idle_add(self.estado_recuerdo, e),
            al_oir=lambda t: GLib.idle_add(self.trozo_recordado, t))
        if not self.escucha_recuerdo.iniciar():
            self.escucha_recuerdo = None      # se podrá escribir, que también vale

    def estado_recuerdo(self, estado: str):
        if getattr(self, "lbl_recuerdo", None) is not None and self.recuerdo:
            self.lbl_recuerdo.set_label(
                {"escuchando": "🎙️ Te escucho… sigue, sin prisa",
                 "procesando": "✍️ Anotando…"}.get(estado, ""))
        return False

    def trozo_recordado(self, texto: str):
        """Cada tanda de lo que vas diciendo se va apuntando."""
        if not getattr(self, "recuerdo", None) or not texto:
            return False
        self.recuerdo["dicho"].append(texto)
        self.render_recuerdo()
        if getattr(self, "escucha_recuerdo", None) is not None:
            self.escucha_recuerdo.reanudar()
        return False

    def render_recuerdo(self, informe: dict | None = None):
        if not getattr(self, "recuerdo", None):
            return
        self.clear_bubble()
        tema = self.recuerdo["tema"]
        self.bubble_box.append(self.bubble_header(f"🧠 {tema['name']}"))
        self.lbl_recuerdo = Gtk.Label(label="🎙️ Te escucho… sigue, sin prisa", xalign=0,
                                      css_classes=["as-bubble-cita"])
        self.bubble_box.append(self.lbl_recuerdo)

        dicho = " ".join(self.recuerdo["dicho"])
        if dicho:
            scroll = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=140,
                                        hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(Gtk.Label(label=dicho, wrap=True, xalign=0,
                                       max_width_chars=self.char_width(32),
                                       css_classes=["as-bubble-text"]))
            self.bubble_box.append(scroll)

        entrada = Gtk.Entry(placeholder_text="…o escríbelo aquí",
                            css_classes=["as-reto-entrada"])
        entrada.connect("activate", lambda w: (self.trozo_recordado(w.get_text().strip()),
                                               w.set_text("")))
        self.bubble_box.append(entrada)

        if informe:
            self.bubble_box.append(Gtk.Label(
                label=f"<b>Recordaste el {informe['nota']}%</b> · {informe['veredicto']}",
                use_markup=True, wrap=True, xalign=0, css_classes=["as-bubble-front"]))
            if informe["falto"]:
                self.bubble_box.append(Gtk.Label(label="Se te quedó fuera:", xalign=0,
                                                 css_classes=["as-bubble-title"]))
                for punto in informe["falto"][:6]:
                    self.bubble_box.append(Gtk.Label(
                        label=f"· {punto}", wrap=True, xalign=0,
                        max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))

        fila = Gtk.Box(spacing=6, homogeneous=True)
        cerrar = Gtk.Button(label="Dejarlo", css_classes=["pill"])
        cerrar.connect("clicked", lambda *_: self.parar_recuerdo())
        fila.append(cerrar)
        listo = Gtk.Button(label="Ya está, contrasta", css_classes=["pill", "suggested-action"])
        listo.connect("clicked", lambda *_: self.contrastar_recuerdo())
        fila.append(listo)
        self.bubble_box.append(fila)
        self.open_bubble()

    def contrastar_recuerdo(self):
        """Compara lo que soltaste con el material y dice qué te dejaste."""
        from . import recuerdo
        if not getattr(self, "recuerdo", None):
            return
        if getattr(self, "escucha_recuerdo", None) is not None:
            self.escucha_recuerdo.pausar()
        self.creature.pensar()
        material = self.recuerdo["material"]
        dicho = " ".join(self.recuerdo["dicho"])
        cfg = ia.config(self.con)

        def _fin(informe):
            if not getattr(self, "recuerdo", None):
                return
            recuerdo.guardar(self.con, self.recuerdo["tema"]["key"], informe)
            self.render_recuerdo(informe)
            faltaron = len(informe.get("falto", []))
            resumen = f"Recordaste el {informe['nota']} por ciento. {informe['veredicto']}"
            if faltaron:
                resumen += f" Se te quedaron fuera {faltaron} cosas."
            self.voz_cfg = voz.config(self.con)
            duracion = voz.hablar(resumen, self.voz_cfg, on_done=self.on_voz_terminada)
            if duracion > 0:
                self.creature.hablar(duracion)

        ia.hilo(lambda: recuerdo.evaluar(cfg, material, dicho), _fin,
                lambda e: _fin({"nota": 0, "falto": [], "cubierto": [],
                                "veredicto": str(e), "sin_ia": True}))

    def parar_recuerdo(self, cerrar_globo: bool = True):
        escucha, self.escucha_recuerdo = getattr(self, "escucha_recuerdo", None), None
        if escucha is not None:
            escucha.detener()
        self.recuerdo = None
        if cerrar_globo:
            self.close_bubble()
        GLib.timeout_add_seconds(2, lambda: (self.arrancar_palabra_clave(), False)[1])

    def empezar_examen_oral(self):
        """Bit te pregunta hablando y califica lo que respondes."""
        from . import examen_oral, voz_rec
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y te tomo el examen.", titulo="🧠 Sin IA",
                     boton=("Abrir AppStudy", self.open_main))
            return
        tarjetas = examen_oral.tarjetas_para_examen(self.con)
        if not tarjetas:
            self.say("Primero estudia algo: no te puedo examinar de lo que no has abierto.",
                     titulo="🎓 Nada que preguntar")
            return

        self.parar_conversacion()
        self.parar_palabra_clave()
        self.ultimo_modo = self.empezar_examen_oral
        self.examen = examen_oral.ExamenOral(self.con, ia.config(self.con), tarjetas)
        self.escucha_examen = voz_rec.EscuchaContinua(
            idioma="es",
            al_estado=lambda e: GLib.idle_add(self.estado_examen, e),
            al_oir=lambda t: GLib.idle_add(self.respuesta_de_examen, t))
        if not self.escucha_examen.iniciar():
            self.examen = None
            self.say("No pude abrir el micrófono para escucharte.", titulo="🎙️ Sin micrófono")
            return
        self.escucha_examen.pausar()      # primero pregunta ella
        self.creature.charlando = True
        self.render_examen("Preparando la primera pregunta…")
        self.lanzar_pregunta_examen()

    def lanzar_pregunta_examen(self):
        """Pide la pregunta al modelo en otro hilo y la dice en voz alta."""
        if self.examen is None:
            return
        self.creature.pensar()

        def _fin(pregunta):
            if self.examen is None:
                return
            self.render_examen(pregunta)
            self.hablar_examen(pregunta, luego_escuchar=True)

        ia.hilo(self.examen.siguiente_pregunta, _fin, lambda e: _fin(str(e)))

    def hablar_examen(self, texto: str, luego_escuchar: bool):
        self.voz_cfg = voz.config(self.con)
        self.cara_de_la_voz(texto)
        fin = self.escuchar_respuesta_examen if luego_escuchar else self.on_voz_terminada
        duracion = voz.hablar(texto, self.voz_cfg, on_done=fin)
        if duracion > 0:
            self.creature.hablar(duracion)
        elif luego_escuchar:
            self.escuchar_respuesta_examen()

    def escuchar_respuesta_examen(self):
        self.on_voz_terminada()
        if getattr(self, "escucha_examen", None) is not None:
            self.escucha_examen.reanudar()
        return False

    def estado_examen(self, estado: str):
        if self.examen is None:
            return False
        etiquetas = {"escuchando": "🎙️ Te escucho… responde con tus palabras",
                     "procesando": "🤔 Corrigiendo…",
                     "hablando": "🔊 Bit está hablando…"}
        if getattr(self, "lbl_examen", None) is not None:
            self.lbl_examen.set_label(etiquetas.get(estado, ""))
        return False

    def respuesta_de_examen(self, dicho: str):
        """Llega tu respuesta hablada: se califica y se pasa a la siguiente."""
        if self.examen is None:
            return False
        if getattr(self, "escucha_examen", None) is not None:
            self.escucha_examen.pausar()
        self.estado_examen("procesando")

        def _fin(resultado):
            if self.examen is None:
                return
            self.render_examen(self.examen.pregunta_actual, resultado=resultado)
            if resultado.get("nota", 0) >= 60:
                self.creature.celebrar()
            else:
                self.creature.desanimar()
            comentario = resultado.get("veredicto") or "Vamos con la siguiente."
            if resultado.get("falto"):
                comentario += f" Te faltó: {resultado['falto']}."
            if self.examen.terminado():
                self.cerrar_examen(comentario)
            else:
                self.hablar_examen(comentario, luego_escuchar=False)
                GLib.timeout_add(600, lambda: (self.lanzar_pregunta_examen(), False)[1])

        ia.hilo(lambda: self.examen.responder(dicho), _fin,
                lambda e: _fin({"nota": 0, "veredicto": str(e), "falto": ""}))
        return False

    def cerrar_examen(self, comentario: str):
        """Se acabó: acta, nota y a repasar lo flojo."""
        guardar = getattr(self.examen, "guardar", None)
        acta = guardar() if guardar else self.examen.acta()
        self.render_acta(acta)
        self.parar_examen(cerrar_globo=False)
        self.hablar_examen(
            f"{comentario} Nota final, {acta['nota']} sobre 100. {acta['juicio']}",
            luego_escuchar=False)

    def empezar_conexiones(self):
        """Preguntas de relación: qué tiene que ver una cosa con la otra."""
        from . import conexiones, voz_rec
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y te pregunto por las conexiones.",
                     titulo="🧠 Sin IA", boton=("Abrir AppStudy", self.open_main))
            return
        parejas = conexiones.pares(self.con)
        if not parejas:
            self.say("Estudia un poco más de un mismo tema y te pregunto cómo encaja.",
                     titulo="🔗 Aún no hay de qué")
            return

        self.parar_conversacion()
        self.parar_palabra_clave()
        self.ultimo_modo = self.empezar_conexiones
        self.examen = conexiones.SesionConexiones(self.con, ia.config(self.con), parejas)
        self.escucha_examen = voz_rec.EscuchaContinua(
            idioma="es",
            al_estado=lambda e: GLib.idle_add(self.estado_examen, e),
            al_oir=lambda t: GLib.idle_add(self.respuesta_de_examen, t))
        if not self.escucha_examen.iniciar():
            self.examen = None
            self.say("No pude abrir el micrófono para escucharte.", titulo="🎙️ Sin micrófono")
            return
        self.escucha_examen.pausar()
        self.creature.charlando = True
        self.render_examen("Buscando dos cosas que tengan que ver…")
        self.lanzar_pregunta_examen()

    def parar_examen(self, cerrar_globo: bool = True):
        escucha, self.escucha_examen = getattr(self, "escucha_examen", None), None
        if escucha is not None:
            escucha.detener()
        self.examen = None
        self.creature.charlando = False
        if cerrar_globo:
            self.close_bubble()
        GLib.timeout_add_seconds(2, lambda: (self.arrancar_palabra_clave(), False)[1])

    def render_examen(self, pregunta: str, resultado: dict | None = None):
        """El globo del examen: dónde vas, la pregunta y la nota de la anterior."""
        if self.examen is None:
            return
        self.clear_bubble()
        self.bubble_box.add_css_class("as-bubble-chat")
        self.card = None
        self.reto = None
        icono = "🔗" if self.examen.marcador().startswith("Conexión") else "🎓"
        self.bubble_box.append(self.bubble_header(f"{icono} {self.examen.marcador()}", CHAT))
        self.lbl_examen = Gtk.Label(label="🔊 Bit está hablando…", xalign=0,
                                    css_classes=["as-bubble-cita"])
        self.bubble_box.append(self.lbl_examen)
        self.bubble_box.append(Gtk.Label(
            label=pregunta, wrap=True, xalign=0, max_width_chars=self.char_width(32),
            css_classes=["as-bubble-front"]))
        if resultado:
            texto = f"<b>{resultado['nota']}/100</b> · {resultado.get('veredicto', '')}"
            if resultado.get("falto"):
                texto += f"\n<i>Te faltó: {resultado['falto']}</i>"
            self.bubble_box.append(Gtk.Label(label=texto, use_markup=True, wrap=True,
                                             xalign=0, css_classes=["as-bubble-text"]))
        salir = Gtk.Button(label="Dejar el examen", css_classes=["pill"])
        salir.connect("clicked", lambda *_: self.parar_examen())
        self.bubble_box.append(salir)
        self.open_bubble()

    def render_acta(self, acta: dict):
        self.clear_bubble()
        self.bubble_box.add_css_class("as-bubble-chat")
        self.bubble_box.append(self.bubble_header("🎓 Examen terminado", CHAT))
        cabeza = f"<b>{acta['nota']}/100</b>"
        if "aprobadas" in acta:
            cabeza += f" · {acta['aprobadas']} de {acta['total']} bien"
        self.bubble_box.append(Gtk.Label(
            label=f"{cabeza}\n{acta['juicio']}",
            use_markup=True, wrap=True, xalign=0, css_classes=["as-bubble-front"]))
        if acta["flojas"]:
            self.bubble_box.append(Gtk.Label(label="Lo que hay que repasar:", xalign=0,
                                             css_classes=["as-bubble-title"]))
            for floja in acta["flojas"][:3]:
                # El examen trae la tarjeta; las conexiones, las dos que unía
                titulo = floja.get("front") or " ↔ ".join(floja.get("entre", ()))
                self.bubble_box.append(Gtk.Label(
                    label=f"· {titulo} ({floja['nota']}/100)", wrap=True, xalign=0,
                    max_width_chars=self.char_width(32), css_classes=["as-bubble-text"]))
        fila = Gtk.Box(spacing=6, homogeneous=True)
        cerrar = Gtk.Button(label="Cerrar", css_classes=["pill"])
        cerrar.connect("clicked", self.close_bubble)
        fila.append(cerrar)
        repetir = self.ultimo_modo or self.empezar_examen_oral
        otra = Gtk.Button(label="Otra ronda", css_classes=["pill", "suggested-action"])
        otra.connect("clicked", lambda *_: repetir())
        fila.append(otra)
        self.bubble_box.append(fila)
        self.open_bubble()

    def explicarselo_a_bit(self):
        """Tú explicas y Bit hace de alumna que no se entera y repregunta.

        Explicar en voz alta destapa los huecos que releer no destapa: releyendo
        reconoces lo que ya viste, explicando tienes que producirlo tú.
        """
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y te escucho la explicación.",
                     titulo="🧠 Sin IA", boton=("Abrir AppStudy", self.open_main))
            return
        tema = ""
        if self.card:
            tema = util.plain(self.card["front"])
        elif getattr(self, "stats", None):
            carta = scheduler.next_card(self.con)
            tema = util.plain(carta["front"]) if carta else ""

        self.abrir_chat()
        if self.chat is None:
            return
        self.chat["papel"] = "alumna"
        self.chat["contexto"] = f"El estudiante te va a explicar: {tema}" if tema else ""
        entrada = (f"Voy a explicarte «{tema}». Pregúntame lo que no entiendas."
                   if tema else "Voy a explicarte un tema. Pregúntame lo que no entiendas.")
        self.render_chat()
        self.alternar_conversacion()      # manos libres: es una explicación hablada
        if self.conversacion is not None:
            self.enviar_chat(entrada)

    def alternar_conversacion(self):
        """Enciende o apaga la charla hablada: hablas y Bit contesta, sin botones."""
        from . import voz_rec
        if self.conversacion is not None:
            self.parar_conversacion(despedirse=True)
            return
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y charlamos.", titulo="🧠 Sin IA",
                     boton=("Abrir AppStudy", self.open_main))
            return
        if not voz_rec.tiene_reconocimiento_voz("es"):
            self.say("Me falta el reconocimiento de voz. Instálame vosk y te escucho.",
                     titulo="🎙️ Sin oído")
            return
        if self.chat is None:
            self.abrir_chat()
            if self.chat is None:     # la IA no estaba lista
                return
        self.chat["hablado"] = True

        escucha = voz_rec.EscuchaContinua(
            idioma="es",
            al_estado=lambda e: GLib.idle_add(self.estado_conversacion, e),
            al_oir=lambda t: GLib.idle_add(self.oido_en_conversacion, t))
        if not escucha.iniciar():
            self.say("No pude abrir el micrófono para escucharte.", titulo="🎙️ Sin micrófono")
            return
        self.parar_palabra_clave()   # el micrófono es de la charla mientras dure
        self.conversacion = escucha
        self.render_chat()

    def parar_conversacion(self, despedirse: bool = False):
        escucha, self.conversacion = self.conversacion, None
        if escucha is not None:
            escucha.detener()
        if self.chat is not None:
            self.chat["hablado"] = False
            self.render_chat()
        if despedirse and self.chat is not None:
            self.creature.play("salto", 0.4)
        # Se vuelve a dejar el oído puesto, pero un momento después: si arranca
        # pegado al final de la charla, coge la cola de lo último que se dijo.
        GLib.timeout_add_seconds(2, lambda: (self.arrancar_palabra_clave(), False)[1])

    def estado_conversacion(self, estado: str):
        """Refleja en el globo si te está oyendo, pensando o hablando."""
        etiquetas = {"escuchando": "🎙️ Te escucho…",
                     "procesando": "🤔 Déjame pensar…",
                     "hablando": "🔊 Bit está hablando…"}
        if getattr(self, "lbl_conversacion", None) is not None:
            self.lbl_conversacion.set_label(etiquetas.get(estado, ""))
        if estado == "escuchando" and self.creature:
            self.creature.play("mirar", 0.6)
        return False

    def oido_en_conversacion(self, texto: str):
        """Llega un turno tuyo transcrito del micrófono."""
        if self.conversacion is None or not texto:
            return False
        if self.es_despedida(texto):
            self.parar_conversacion()
            self.chat["historial"].append({"role": "user", "content": texto})
            self.render_chat()
            self.hablar_en_conversacion("Vale, aquí sigo cuando quieras.", seguir=False)
            return False
        if not self.enviar_chat(texto) and self.conversacion is not None:
            # Fue una orden ("abre Platzi", "crea una tarjeta"): no hay respuesta
            # del modelo que esperar, así que se vuelve a escuchar ya.
            self.conversacion.reanudar()
        return False

    def hablar_en_conversacion(self, texto: str, seguir: bool = True):
        """Bit dice su turno y, al terminar, vuelve a escucharte."""
        self.voz_cfg = voz.config(self.con)
        self.estado_conversacion("hablando")
        fin = self.fin_turno_hablado if seguir else (lambda: self.on_voz_terminada())
        self.cara_de_la_voz(texto)
        duracion = voz.hablar(texto, self.voz_cfg, on_done=fin)
        if duracion > 0:
            self.creature.hablar(duracion)
        elif seguir:
            self.fin_turno_hablado()

    def fin_turno_hablado(self):
        self.on_voz_terminada()
        if self.conversacion is not None:
            self.conversacion.reanudar()
        return False

    def abrir_chat(self):
        """Empieza una conversación nueva, con la tarjeta actual como contexto."""
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y charlamos.", titulo="🧠 Sin IA",
                     boton=("Abrir AppStudy", self.open_main))
            return
        contexto = ""
        if self.card:
            contexto = (f"{util.plain(self.card['front'])} → "
                        f"{util.plain(self.card['back'])}")
        self.chat = {"historial": [], "contexto": contexto}
        self.creature.charlando = True
        self.creature.play("salto", 0.5)
        self.sonar("listo")
        self.render_chat()

    def salir_chat(self, *_):
        """Se acabó la charla: Bit vuelve a su color y a lo suyo, y libera la IA."""
        self.parar_conversacion()
        self.chat = None
        self.creature.charlando = False
        self.bubble_box.remove_css_class("as-bubble-chat")
        self.liberar_ia()
        self.close_bubble()

    def render_chat(self, escribiendo=None):
        """El globo del chat: lo hablado, una caja de texto y la salida.

        `escribiendo` es la etiqueta donde el modelo va escribiendo su respuesta;
        se pasa cuando se está en mitad de un turno.
        """
        self.clear_bubble()
        self.bubble_box.add_css_class("as-bubble-chat")
        self.card = None
        self.reto = None

        hablando = self.conversacion is not None
        if self.chat.get("papel") == "alumna":
            titulo = "👩‍🎓 Explícaselo a Bit"
        else:
            titulo = "🎙️ Hablando con Bit" if hablando else "💬 Chat con Bit"
        cabecera = self.bubble_header(titulo, CHAT)
        self.bubble_box.append(cabecera)
        self.lbl_conversacion = None
        if hablando:
            self.lbl_conversacion = Gtk.Label(label="🎙️ Te escucho…", xalign=0,
                                              css_classes=["as-bubble-cita"])
            self.bubble_box.append(self.lbl_conversacion)
        if self.chat["contexto"]:
            self.bubble_box.append(Gtk.Label(
                label=self.chat["contexto"][:110], wrap=True, xalign=0,
                max_width_chars=self.char_width(34), css_classes=["as-bubble-cita"]))

        charla = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for turno in self.chat["historial"][-8:]:
            mio = turno["role"] == "user"
            charla.append(Gtk.Label(
                label=util.to_markup(turno["content"]), use_markup=True, wrap=True,
                xalign=1 if mio else 0, max_width_chars=self.char_width(32),
                css_classes=["as-chat-tu" if mio else "as-chat-bit"]))
        if escribiendo is not None:
            charla.append(escribiendo)
        scroll = Gtk.ScrolledWindow(propagate_natural_height=True,
                                    max_content_height=230,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(charla)
        self.bubble_box.append(scroll)
        GLib.timeout_add(60, lambda: (self._chat_al_final(scroll), False)[1])

        entrada = Gtk.Entry(
            placeholder_text="Háblame o escríbeme…" if hablando else "Escríbeme…",
            css_classes=["as-reto-entrada"])
        self.bubble_box.append(entrada)

        micro = Gtk.Button(
            label="⏹️ Dejar de hablar" if hablando else "🎙️ Hablar con Bit",
            css_classes=["pill", "destructive-action" if hablando else "as-chat-enviar"])
        micro.connect("clicked", lambda *_: self.alternar_conversacion())
        self.bubble_box.append(micro)

        fila = Gtk.Box(spacing=6, homogeneous=True)
        salir = Gtk.Button(label="Salir del chat", css_classes=["pill"])
        salir.connect("clicked", self.salir_chat)
        fila.append(salir)
        enviar = Gtk.Button(label="Enviar", css_classes=["pill", "as-chat-enviar"])
        fila.append(enviar)
        self.bubble_box.append(fila)
        for w, senal in ((entrada, "activate"), (enviar, "clicked")):
            w.connect(senal, lambda *_: self.enviar_chat(entrada.get_text().strip()))
        if escribiendo is None:
            GLib.timeout_add(320, lambda: (entrada.grab_focus(), False)[1])
        else:
            entrada.set_sensitive(False)
            enviar.set_sensitive(False)
        self.open_bubble()

    @staticmethod
    def _chat_al_final(scroll):
        ajuste = scroll.get_vadjustment()
        ajuste.set_value(max(0, ajuste.get_upper() - ajuste.get_page_size()))

    def enviar_chat(self, texto):
        """Manda un turno. Devuelve False si lo resolvió una orden, sin modelo."""
        if not texto or self.chat is None:
            return False

        texto_l = texto.lower()
        if any(k in texto_l for k in ("crea una tarjeta", "crear una tarjeta", "haz una tarjeta", "nueva tarjeta")):
            self.crear_tarjeta_con_ia(texto)
            return False

        es_c = any(k in texto_l for k in ("platzi", "udemy", "curso", "clase", "reproductor", "video"))
        es_a = any(k in texto_l for k in ("platzi", "udemy", "siguiente", "proximo", "próximo", "ultimo", "último", "abre", "abrir", "pon", "poner", "ver", "reproduce", "reproducir", "mostrar", "muéstrame"))
        if es_c and es_a:
            plat = "platzi" if "platzi" in texto_l else ("udemy" if "udemy" in texto_l else None)
            self.abrir_reproductor_cursos(plat)
            return False

        self.chat["historial"].append({"role": "user", "content": texto})
        cuerpo = Gtk.Label(label="…", wrap=True, xalign=0, max_width_chars=self.char_width(32),
                           css_classes=["as-chat-bit"])
        self.ia_texto = ""
        self.ia_cuerpo = cuerpo
        self.render_chat(escribiendo=cuerpo)
        self.creature.hablar(60)
        self.creature.pensar()

        cfg = ia.config(self.con)
        historial = list(self.chat["historial"][:-1])
        contexto = self.chat["contexto"]
        hablado = bool(self.chat.get("hablado"))
        papel = self.chat.get("papel", "profesora")
        ia.hilo(lambda: ia.conversar(cfg, historial, texto, contexto,
                                     trozo=self.escribir_ia, hablado=hablado, papel=papel),
                self.fin_chat,
                lambda e: self.fin_chat(f"<i>{GLib.markup_escape_text(str(e))}</i>"))
        return True

    def fin_chat(self, respuesta):
        self.creature.hablando_hasta = 0
        if self.chat is None:
            return                       # saliste del chat mientras pensaba
        self.texto_hablable = respuesta or ""
        self.chat["historial"].append({"role": "assistant",
                                       "content": respuesta or "(sin respuesta)"})
        self.sonar("listo")
        self.render_chat()
        if self.conversacion is not None:
            self.hablar_en_conversacion(ia.acortar_para_hablar(respuesta or ""))
        else:
            self.voz_auto_si_toca()

    def preguntar(self):
        """Un globo con una caja de texto: pregúntale lo que quieras."""
        if not ia.config(self.con)["activa"]:
            self.say("Actívame la IA en Ajustes y te respondo lo que quieras.",
                     titulo="🧠 Sin IA", boton=("Abrir AppStudy", self.open_main))
            return
        # Si venías de una tarjeta, se guarda para dársela como contexto
        self.contexto_ia = (f"{util.plain(self.card['front'])} → "
                            f"{util.plain(self.card['back'])}") if self.card else ""
        self.card = None
        self.reto = None
        self.clear_bubble()
        self.bubble_box.append(self.bubble_header("🧠 Pregúntame algo"))
        entrada = Gtk.Entry(placeholder_text="¿Qué quieres saber?",
                            css_classes=["as-reto-entrada"])
        self.bubble_box.append(entrada)
        fila = Gtk.Box(spacing=6, homogeneous=True)
        cerrar = Gtk.Button(label="Ahora no", css_classes=["pill"])
        cerrar.connect("clicked", self.close_bubble)
        fila.append(cerrar)
        mandar = Gtk.Button(label="Preguntar", css_classes=["pill", "as-rate-good"])
        fila.append(mandar)
        self.bubble_box.append(fila)
        for w, señal in ((entrada, "activate"), (mandar, "clicked")):
            w.connect(señal, lambda *_: self.lanzar_pregunta(entrada.get_text().strip()))
        GLib.timeout_add(350, lambda: (entrada.grab_focus(), False)[1])
        self.open_bubble()

    def lanzar_pregunta(self, pregunta):
        if not pregunta:
            return
        # Si no venías de una tarjeta, se buscan las tuyas que hablen del tema
        contexto = self.contexto_ia or ia.buscar_contexto(self.con, pregunta)
        cuerpo = self.globo_ia("🧠 A ver…", pregunta)
        self.creature.pensar()
        cfg = ia.config(self.con)
        ia.hilo(lambda: ia.preguntar(cfg, pregunta, contexto, trozo=self.escribir_ia),
                lambda texto: self.fin_ia(cuerpo, texto, None),
                lambda e: self.fin_ia(cuerpo, f"<i>{GLib.markup_escape_text(str(e))}</i>", None))

    def globo_ia(self, titulo, pregunta):
        """Prepara el globo donde el modelo va escribiendo su respuesta."""
        self.clear_bubble()
        self.bubble_box.append(self.bubble_header(titulo))
        self.bubble_box.append(Gtk.Label(
            label=util.to_markup(pregunta), use_markup=True, wrap=True, xalign=0,
            max_width_chars=self.char_width(30), css_classes=["as-bubble-front"]))
        self.bubble_box.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
        cuerpo = Gtk.Label(label="…", wrap=True, xalign=0, max_width_chars=self.char_width(32),
                           css_classes=["as-bubble-text"])
        self.bubble_box.append(cuerpo)
        self.ia_texto = ""
        self.ia_cuerpo = cuerpo
        self.creature.hablar(60)          # la boca se mueve mientras escribe
        self.open_bubble()
        return cuerpo

    def escribir_ia(self, pedazo):
        """Llega desde el hilo del modelo: se pinta en el de la interfaz."""
        def pintar():
            self.ia_texto += pedazo
            if self.ia_cuerpo is not None:
                self.ia_cuerpo.set_text(self.ia_texto)     # crudo mientras escribe
            return False
        GLib.idle_add(pintar)

    def fin_ia(self, cuerpo, texto, card):
        """Respuesta completa: se pasa a markup y se dejan los botones."""
        self.creature.hablando_hasta = 0
        if cuerpo is not self.ia_cuerpo:
            return                        # el globo ya se cerró o cambió
        self.texto_hablable = texto or ""
        cuerpo.set_markup(util.to_markup(texto or "(sin respuesta)"))
        self.sonar("listo")
        fila = Gtk.Box(spacing=6, homogeneous=True)
        otra = Gtk.Button(label="Otra pregunta", css_classes=["pill"])
        otra.connect("clicked", lambda *_: self.preguntar())
        fila.append(otra)
        seguir = Gtk.Button(label="Enséñame", css_classes=["pill", "suggested-action"])
        seguir.connect("clicked", lambda *_: self.teach())
        fila.append(seguir)
        self.bubble_box.append(fila)
        self.card = card                  # para el pie, si venía de una tarjeta
        if card:
            self.bubble_box.append(self.pie_leer())
        self.creature.play("salto", 0.5)
        self.voz_auto_si_toca()

    # --------------------------------------------------------- leer sobre esto

    def fuente_de(self, card):
        """Capítulo o libro de origen, calculado una sola vez por tarjeta."""
        if not card:
            return None
        if self.cap_cache[0] != card["id"]:
            fuente = db.source_for_card(self.con, card["id"])
            if not fuente:
                cap = db.chapter_for_card(self.con, card)
                fuente = ({"kind": "chapter", "title": cap["title"], "chapter": cap}
                          if cap else None)
            self.cap_cache = (card["id"], fuente)
        return self.cap_cache[1]

    def pie_leer(self):
        """El pie del globo: abre la lectura justo donde se explica esto."""
        fuente = self.fuente_de(self.card)
        b = Gtk.Button(css_classes=["flat", "as-bubble-link"])
        if fuente is None:
            b.set_label("Sesión completa →")
            b.connect("clicked", lambda *_: self.study())
            return b
        titulo = util.plain(db.source_label(fuente))
        b.set_label(f"Volver a la fuente → {titulo[:26]}{'…' if len(titulo) > 26 else ''}")
        b.set_tooltip_text(f"Abre «{titulo}», de donde salió esta tarjeta")
        b.connect("clicked", lambda *_: self.leer_sobre_esto())
        return b

    def leer_sobre_esto(self):
        card = self.card
        self.close_bubble()          # cierra el globo, pero la tarjeta ya está a salvo
        if card:
            self.spawn("--read-card", str(card["id"]))
        else:
            self.spawn("--popup")

    # ---------------------------------------------------------------- acciones

    def on_click(self, gesture, n_press, x, y):
        if self.clic_del_menu(gesture):
            return
        boton = gesture.get_current_button()
        if boton == 3:
            self.abrir_menu_en(self.creature, x, y)
            return
        if boton == 1 and n_press == 1:
            self.sonar("clic")
            self.creature.play("salto", 0.6)
            if self.bubble.get_reveal_child():
                self.close_bubble()
            else:
                self.wake()
                self.teach()

    def on_bubble_click(self, gesture, n_press, x, y):
        if self.clic_del_menu(gesture):
            return
        boton = gesture.get_current_button()
        if boton == 3:
            self.abrir_menu_en(self.bubble_box, x, y)
            return

    # ------------------------------------------------ la tarjeta de acciones

    def clic_del_menu(self, gesture):
        # El popover cuelga de la criatura o del globo. Sus clics no deben
        # activar también «enseñar»/«cerrar globo» en ese antecesor.
        evento = gesture.get_current_event()
        return evento is not None and evento.get_surface() != self.get_surface()

    def boton_menu_gestos(self):
        boton = Gtk.Button(label="Gestos de Bit →", css_classes=["flat", "as-menu-fila"])
        # No usar _fila_accion: cierra el popover antes de ejecutar la acción.
        boton.connect("clicked", lambda *_: self.mostrar_menu_gestos())
        return boton

    def mostrar_menu_gestos(self):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       css_classes=["as-menu-caja"])
        volver = Gtk.Button(label="← Volver", css_classes=["flat"])
        volver.connect("clicked", lambda *_: self.refrescar_menu())
        caja.append(volver)
        caja.append(Gtk.Label(label="Elige un gesto", xalign=0,
                              css_classes=["as-bubble-title"]))
        if self.creature.reduced_motion:
            caja.append(Gtk.Label(label="Reducir movimiento está activo: solo verás las expresiones faciales. "
                                        "Puedes cambiarlo en Ajustes → Apariencia y progreso.",
                                  wrap=True, max_width_chars=32, xalign=0))
        for nombre, etiqueta in Creature.GESTOS_MENU:
            caja.append(self._fila_accion(etiqueta,
                        lambda n=nombre: self.creature.actuar(n)))
        self.menu.set_child(caja)

    def _boton_accion(self, etiqueta, cb, clases=("pill",), tooltip=None):
        b = Gtk.Button(label=etiqueta, css_classes=list(clases), hexpand=True)
        b.connect("clicked", lambda *_: (self.menu.popdown(), cb()))
        if tooltip:
            b.set_tooltip_text(tooltip)
        return b

    def _fila_accion(self, etiqueta, cb, sufijo=None):
        """Una línea de la lista: texto a la izquierda y, si acaso, un dato a la derecha."""
        b = Gtk.Button(css_classes=["flat", "as-menu-fila"])
        caja = Gtk.Box(spacing=8)
        caja.append(Gtk.Label(label=etiqueta, xalign=0, hexpand=True))
        if sufijo:
            caja.append(Gtk.Label(label=sufijo, css_classes=["as-menu-dato"]))
        b.set_child(caja)
        b.connect("clicked", lambda *_: (self.menu.popdown(), cb()))
        return b

    def _grupo_tamano(self, titulo, menos, mas):
        fila = Gtk.Box(spacing=6, css_classes=["as-menu-tamano"])
        fila.append(Gtk.Label(label=titulo, xalign=0, hexpand=True,
                              css_classes=["as-menu-dato"]))
        for etiqueta, cb in (("−", menos), ("+", mas)):
            b = Gtk.Button(label=etiqueta, css_classes=["circular", "flat"])
            b.connect("clicked", lambda _b, f=cb: f())     # sin cerrar: se ajusta a ojo
            fila.append(b)
        return fila

    def refrescar_menu(self):
        """Rehace el contenido: el estado y las etiquetas cambian entre aperturas."""
        t = self.stats or {}
        # `total` de stats son tarjetas, no repasos: la etapa se cuenta del log
        etapa = evolucion(total_repasos(self.con))["nombre"]
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       css_classes=["as-menu-caja"])

        caja.append(Gtk.Label(label=f"{self.nombre} · {etapa}", xalign=0,
                              css_classes=["as-bubble-title"]))
        pendientes = t.get("pendientes", 0)
        resumen = (f"{pendientes} pendientes · {t.get('hoy', 0)} hoy"
                   if pendientes else f"al día · {t.get('hoy', 0)} hoy")
        racha = t.get("racha", 0)
        if racha:
            resumen += f" · racha de {racha} d"
        if t.get("nuevas_tope"):
            resumen += f"\n{t.get('nuevas_hoy', 0)} nuevas hoy · quedan {t.get('nuevas_restantes', 0)} de cupo"
        caja.append(Gtk.Label(label=resumen, xalign=0, css_classes=["as-menu-estado"]))
        caja.append(self.boton_menu_gestos())

        # Lo que se usa a diario, en botones grandes y a dos columnas
        rejilla = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True,
                           margin_top=4)
        principales = [
            ("🧠 Enséñame", lambda: (self.wake(), self.teach())),
            ("⚡ Ponme a prueba", lambda: (self.wake(), self.quiz())),
            ("🎙️ Hablar", lambda: (self.wake(), self.alternar_conversacion())),
            ("💬 Chat", lambda: (self.wake(), self.abrir_chat())),
            ("🎓 Examen oral", lambda: (self.wake(), self.empezar_examen_oral())),
            ("🗒️ Recuerdo libre", lambda: (self.wake(), self.empezar_recuerdo_libre())),
            ("👩‍🎓 Te lo explico", lambda: (self.wake(), self.explicarselo_a_bit())),
            ("🔗 Conexiones", lambda: (self.wake(), self.empezar_conexiones())),
        ]
        for i, (etiqueta, cb) in enumerate(principales):
            clases = ["pill", "suggested-action"] if i == 0 else ["pill"]
            rejilla.attach(self._boton_accion(etiqueta, cb, clases), i % 2, i // 2, 1, 1)
        caja.append(rejilla)

        caja.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
        for etiqueta, cb, sufijo in (
                ("❓ Pregúntame algo", lambda: (self.wake(), self.preguntar()), None),
                ("💡 ¿Sabías que…?", lambda: (self.wake(), self.sabias_que()), None),
                ("📖 Una frase de libro", lambda: (self.wake(), self.quote()), None),
                ("📊 Cómo va la semana", lambda: (self.wake(), self.diario()), None),
                ("⏱️ Sesión de estudio", self.study, None),
                ("🕐 Tarjetas recientes", self.abrir_historial, None),
                ("🎬 Platzi", lambda: self.abrir_reproductor_cursos("platzi"), None),
                ("🎬 Udemy", lambda: self.abrir_reproductor_cursos("udemy"), None)):
            caja.append(self._fila_accion(etiqueta, cb, sufijo))

        caja.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
        caja.append(self._grupo_tamano(f"Tamaño de {self.nombre}",
                                       lambda: self.cambiar_tamano(-ESCALA_PASO),
                                       lambda: self.cambiar_tamano(ESCALA_PASO)))
        caja.append(self._grupo_tamano("Tamaño de la tarjeta",
                                       lambda: self.cambiar_tamano_tarjeta(-0.25),
                                       lambda: self.cambiar_tamano_tarjeta(0.25)))

        caja.append(Gtk.Separator(css_classes=["as-bubble-sep"]))
        for etiqueta, cb in (
                ("🔇 Silencio" if self.sonido["activo"] else "🔊 Con sonido",
                 self.alternar_sonido),
                (f"😴 Duérmete {SNOOZE_MIN} min", self.snooze),
                ("☀️ Despertar", self.wake),
                ("🪟 Abrir AppStudy", self.open_main),
                ("❔ Cómo se usa", self.abrir_ayuda)):
            caja.append(self._fila_accion(etiqueta, cb))

        salir = self._fila_accion("🚪 Salir", self.salir_del_todo)
        salir.add_css_class("as-menu-salir")
        caja.append(salir)

        self.menu.set_child(caja)

    def abrir_menu_en(self, widget, x, y):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        if self.menu.get_parent() != widget:
            if self.menu.get_parent() is not None:
                self.menu.unparent()
            self.menu.set_parent(widget)
        self.menu.set_pointing_to(rect)
        self.refrescar_menu()          # el estado y las etiquetas, al día
        self.menu.popup()

    def abrir_historial(self, *_):
        # Salir del reto detiene su cuenta atrás: consultar no puede causar un fallo.
        self.close_bubble()
        historial.abrir(self, self.con)

    def crear_tarjeta_con_ia(self, texto_usuario: str):
        from . import ia
        self.wake()
        cfg_ia = ia.config(self.con)
        if not cfg_ia.get("activa"):
            self.say("Actívame la IA en Ajustes para redactar tarjetas automáticamente.", titulo="🧠 Sin IA")
            return

        ultimo = db.get_last_course(self.con)
        contexto = f"Curso: {ultimo['course_title']} (Clase: {ultimo['last_video_title']})" if ultimo else "General"

        self.say("✨ Redactando tu tarjeta con IA local...", titulo="💡 Nueva tarjeta")
        self.creature.pensar()

        def _tarea():
            prompt = (
                f"El estudiante te pide crear una tarjeta de estudio: «{texto_usuario}».\n"
                f"Contexto del curso que está viendo: {contexto}.\n\n"
                "Genera una tarjeta flashcard concisa en formato JSON estricto:\n"
                "{\n  \"front\": \"Pregunta o concepto clave\",\n  \"back\": \"Respuesta o explicación concisa\",\n  \"tags\": \"etiquetas\"\n}"
            )
            try:
                resp = ia.completar(cfg_ia, prompt, timeout=12)
                m = re.search(r"\{.*\}", resp, re.DOTALL)
                if m:
                    return json.loads(m.group(0))
            except Exception:
                pass
            return None

        def _fin(res):
            if res and res.get("front") and res.get("back"):
                mazos = self.con.execute("SELECT id, name FROM decks ORDER BY pos").fetchall()
                deck_id = mazos[0]["id"] if mazos else 1
                deck_key = mazos[0]["name"].lower() if mazos else "general"
                tags = res.get("tags") or "ia,cursos"
                db.add_card(self.con, deck_id, deck_key, "card", res["front"], res["back"], tags=tags)
                self.con.commit()
                self.creature.celebrar()
                self.sonar("acierto")
                msg = f"¡Tarjeta creada con éxito!\n<b>{res['front']}</b> → {res['back']}"
                self.say(msg, titulo="✅ Tarjeta guardada")
                if getattr(self, "voz_cfg", {}).get("activo", True):
                    voz.hablar(f"Tarjeta creada y guardada: {res['front']}", self.voz_cfg)
            else:
                self.creature.desanimar()
                self.say("No pude redactar la tarjeta automáticamente. Intenta especificar un poco más el concepto.", titulo="⚠️ Aviso")

        import threading
        threading.Thread(target=lambda: GLib.idle_add(_fin, _tarea()), daemon=True).start()

    def abrir_reproductor_cursos(self, plataforma=None, **kwargs):
        from . import reproductor
        self.wake()
        p = (plataforma or "").lower().strip()
        nombre_plat = "Udemy" if p == "udemy" else ("Platzi" if p == "platzi" else "Cursos")
        texto_voz = f"Abriendo {nombre_plat} en el reproductor..."

        self.say(f"🎬 <b>{texto_voz}</b>", titulo="🎬 Cursos Online")
        if getattr(self, "voz_cfg", {}).get("activo", True):
            self.cara_de_la_voz(texto_voz)
            dur = voz.hablar(texto_voz, self.voz_cfg, on_done=self.on_voz_terminada)
            if dur > 0:
                self.creature.hablar(dur)

        reproductor.abrir_reproductor(self.con, plataforma=p if p else None)

    def mostrar_menu_cursos(self):
        self.clear_bubble()
        self.card = None
        self.reto = None

        cabecera = self.bubble_header("🎬 Cursos Online", "#2ec27e")
        self.bubble_box.append(cabecera)

        p_platzi = db.get_last_course(self.con, "platzi")
        p_udemy = db.get_last_course(self.con, "udemy")

        # Tarjeta Platzi
        box_platzi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card"])
        box_platzi.set_margin_top(4)
        box_platzi.set_margin_bottom(4)
        box_platzi.set_margin_start(4)
        box_platzi.set_margin_end(4)
        lbl_p_tit = Gtk.Label(label="🟢 Platzi", css_classes=["heading"], xalign=0)
        box_platzi.append(lbl_p_tit)
        if p_platzi and p_platzi.get("course_title"):
            info_p = f"<b>{p_platzi.get('course_title')}</b>"
        else:
            info_p = "Accede a tus cursos y clases de Platzi."
        box_platzi.append(Gtk.Label(label=info_p, use_markup=True, wrap=True, xalign=0, css_classes=["caption"]))

        btn_platzi = Gtk.Button(label="🟢 Abrir Platzi", css_classes=["pill", "suggested-action"])
        btn_platzi.connect("clicked", lambda *_: self.abrir_reproductor_cursos("platzi"))
        box_platzi.append(btn_platzi)
        self.bubble_box.append(box_platzi)

        # Tarjeta Udemy
        box_udemy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card"])
        box_udemy.set_margin_top(4)
        box_udemy.set_margin_bottom(4)
        box_udemy.set_margin_start(4)
        box_udemy.set_margin_end(4)
        lbl_u_tit = Gtk.Label(label="🟣 Udemy", css_classes=["heading"], xalign=0)
        box_udemy.append(lbl_u_tit)
        if p_udemy and p_udemy.get("course_title"):
            info_u = f"<b>{p_udemy.get('course_title')}</b>"
        else:
            info_u = "Accede a tu biblioteca de cursos de Udemy."
        box_udemy.append(Gtk.Label(label=info_u, use_markup=True, wrap=True, xalign=0, css_classes=["caption"]))

        btn_udemy = Gtk.Button(label="🟣 Abrir Udemy", css_classes=["pill", "suggested-action"])
        btn_udemy.connect("clicked", lambda *_: self.abrir_reproductor_cursos("udemy"))
        box_udemy.append(btn_udemy)
        self.bubble_box.append(box_udemy)

        self.open_bubble()

    def registrar_acciones(self):
        """Las acciones de ventana, por si se llaman desde fuera (GAction).

        La tarjeta de acciones ya no usa un modelo de menú: se construye a mano
        en `refrescar_menu`, así que aquí solo queda el registro.
        """
        for nombre, cb in (("teach", lambda *_: (self.wake(), self.teach())),
                           ("historial", self.abrir_historial),
                           ("quiz", lambda *_: (self.wake(), self.quiz())),
                           ("ask", lambda *_: (self.wake(), self.preguntar())),
                           ("chat", lambda *_: (self.wake(), self.abrir_chat())),
                           ("quote", lambda *_: (self.wake(), self.quote())),
                           ("diario", lambda *_: (self.wake(), self.diario())),
                           ("study", lambda *_: self.study()),
                           ("open", lambda *_: self.open_main()),
                           ("ayuda", lambda *_: self.abrir_ayuda()),
                           ("platzi_open", lambda *_: self.abrir_reproductor_cursos("platzi")),
                           ("udemy_open", lambda *_: self.abrir_reproductor_cursos("udemy")),
                           ("platzi_next", lambda *_: self.abrir_reproductor_cursos("platzi")),
                           ("platzi_last", lambda *_: self.abrir_reproductor_cursos("platzi")),
                           ("udemy_next", lambda *_: self.abrir_reproductor_cursos("udemy")),
                           ("udemy_last", lambda *_: self.abrir_reproductor_cursos("udemy")),
                           ("cursos_player", lambda *_: self.abrir_reproductor_cursos(None)),
                           ("mute", lambda *_: self.alternar_sonido()),
                           ("card_bigger", lambda *_: self.cambiar_tamano_tarjeta(0.15)),
                           ("card_smaller", lambda *_: self.cambiar_tamano_tarjeta(-0.15)),
                           ("card_size_100", lambda *_: self.fijar_tamano_tarjeta(1.0)),
                           ("card_size_125", lambda *_: self.fijar_tamano_tarjeta(1.25)),
                           ("card_size_150", lambda *_: self.fijar_tamano_tarjeta(1.50)),
                           ("bigger", lambda *_: self.cambiar_tamano(ESCALA_PASO)),
                           ("smaller", lambda *_: self.cambiar_tamano(-ESCALA_PASO)),
                           ("snooze", lambda *_: self.snooze()),
                           ("wake", lambda *_: self.wake()),
                           ("quit", lambda *_: self.salir_del_todo())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            self.add_action(a)

    def snooze(self):
        self.sonar("dormir")
        db.set_meta(self.con, "pet_snooze_until", time.time() + SNOOZE_MIN * 60)
        self.liberar_ia()
        self.close_bubble()
        self.refresh_stats()

    def wake(self):
        db.set_meta(self.con, "pet_snooze_until", 0)
        self.refresh_stats()

    def spawn(self, *args):
        """Lanza la aplicación principal; sin GDK_BACKEND para que use Wayland."""
        env = {k: v for k, v in os.environ.items() if k != "GDK_BACKEND"}
        try:
            subprocess.Popen([launcher(), *args], env=env,
                             start_new_session=True)
        except OSError as e:
            print(f"No pude lanzar AppStudy: {e}", file=sys.stderr)

    def study(self):
        self.close_bubble()
        self.spawn("--popup")

    def open_main(self):
        self.close_bubble()
        self.spawn()

    def abrir_ayuda(self):
        """La guía de uso vive en la ventana principal, que es otro proceso."""
        self.close_bubble()
        self.spawn("--ayuda")


# ------------------------------------------------------------------- autostart

AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) \
    / "autostart" / "appstudy-pet.desktop"


def launcher() -> str:
    """Ruta absoluta del lanzador de AppStudy."""
    env = os.environ.get("APPSTUDY_COMMAND")
    if env:
        return env.split()[0]
    script = Path(sys.argv[0]).resolve()
    if script.is_file() and script.name == "appstudy":
        return str(script)
    # Arrancado de otra forma (python -m, un intérprete…): el lanzador que
    # vive junto al paquete.
    return str(Path(__file__).resolve().parent.parent / "bin" / "appstudy")


def autostart_enabled() -> bool:
    return AUTOSTART.exists()


def set_autostart(enabled: bool, nombre_mascota: str = "La mascota") -> str:
    if not enabled:
        AUTOSTART.unlink(missing_ok=True)
        return f"{nombre_mascota} ya no aparecerá al iniciar sesión."
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name=AppStudy · {nombre_mascota}\n"
        "Comment=La mascota de estudio, siempre en el escritorio\n"
        f"Exec={launcher()} --pet\n"
        "Icon=io.github.appstudy.AppStudy\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=8\n")
    return f"{nombre_mascota} saldrá solo al iniciar sesión."


# ----------------------------------------------------------------------- arranque

def run_pet(argv) -> int:
    import shutil
    if shutil.which("wmctrl") is None:
        print("Falta wmctrl: sin él la mascota no puede quedarse encima de todo.\n"
              "  sudo apt install wmctrl x11-utils", file=sys.stderr)

    # El backend X11 (vía XWayland) es lo que permite el «siempre encima» bajo
    # GNOME/Wayland, y se elige en bin/appstudy: para cuando llegamos aquí GTK
    # ya está importado y la pantalla abierta.
    app = Adw.Application(application_id=PET_APP_ID,
                          flags=Gio.ApplicationFlags.FLAGS_NONE)
    abiertas = []          # la ventana de Bit, para poder apagarla al salir

    def activate(a):
        if a.get_active_window():
            a.get_active_window().present()
            return
        con = db.connect()
        # Que se sepa desde fuera (la extensión del top bar) que anda suelta
        db.set_meta(con, "pet_pid", os.getpid())
        a.connect("shutdown", lambda *_: (db.set_meta(con, "pet_pid", 0), ia.descargar(ia.config(con))))
        css = Gtk.CssProvider()
        css.load_from_path(str(Path(__file__).parent / "style.css"))
        display = Gdk.Display.get_default()
        if display:
            # Por encima de PRIORITY_USER: un tema propio en ~/.config/gtk-4.0/
            # pintaría un fondo opaco y la mascota dejaría de recortarse.
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        ventana = PetWindow(a, con)
        abiertas.append(ventana)
        ventana.present()

    import signal
    try:
        def _apagar(*_):
            # Soltar el micrófono antes de irse: si no, el proceso de grabación
            # sobrevive a Bit y el trasto se queda con el micro cogido.
            for ventana in abiertas:
                try:
                    ventana.parar_palabra_clave()
                    ventana.parar_conversacion()
                except Exception:
                    pass
            app.quit()

        signal.signal(signal.SIGTERM, _apagar)
        signal.signal(signal.SIGINT, _apagar)
    except Exception:
        pass
    app.connect("activate", activate)
    return app.run([argv[0]])
