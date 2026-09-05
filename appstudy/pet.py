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
import subprocess
import sys
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import citas, cloze, db, estadisticas, ia, logros, reto  # noqa: E402
from . import historial, recordatorios, scheduler, sonido, util, voz  # noqa: E402

PET_APP_ID = "io.github.appstudy.AppStudy.Pet"
NOMBRE = "Bit"

# Los gestos siguen el reloj de fotogramas de GTK; en reposo limitamos el dibujo.
FRAME_REPOSO = 50

# El estallido de once rayos costaba la mitad del fotograma —dos trazos anchos de
# halo sobre un contorno de once puntas—, así que se pinta una vez en una imagen
# y luego solo se gira. El lienzo tiene que dar para el radio (54) más el halo, y
# se pinta al doble de resolución para que al girarlo no se vean los bordes. El
# paso de la onda es el redondeo de su fase: mueve las puntas menos de dos
# píxeles, así que a saltos de 0,3 rad no se nota y varios fotogramas seguidos
# reaprovechan el mismo dibujo.
ESTRELLA_LADO = 132
ESTRELLA_PASO_ONDA = 0.3

# El mochi se guarda igual. Aquí no hace falta redondear nada: lo único que lo
# cambia es el color del ánimo, así que en reposo se pinta una vez y ya. El
# lienzo tiene que dar para la sombra de contacto, que se sale del cuerpo.
CUERPO_LADO = 120

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

# Bit está dibujado en un lienzo fijo de 152x184 y luego se escala al tamaño
# real del widget: para hacerlo más grande o más pequeño basta con tocar ANCHO y
# ALTO_PET, que las proporciones se mantienen solas.
DISENO = (152, 184)
ANCHO = 168          # el ancho de la mascota al 100 %; el globo manda cuando está abierto
ALTO_PET = 203
ESCALA_MIN, ESCALA_MAX, ESCALA_PASO = 0.5, 2.5, 0.15   # «Más grande» / «Más pequeño»

# Bit está dibujado a la manera de la mascota de Claude: cuerpo crema, tinta
# cálida y el asterisco de rayos girando sobre la cabeza. Es un homenaje hecho a
# mano, no el logotipo de nadie.
CREMA_CLARO = "#FAF8F2"
CREMA = "#F0EDE4"
CREMA_SOMBRA = "#DED7C7"
TERRACOTA = "#D97757"           # el acento de la casa

# Ánimos: el cuerpo siempre es crema, y este es el color del asterisco, los
# cachetes y la barra de energía.
MOODS = {
    "feliz":    "#6E9B7A",
    "normal":   TERRACOTA,
    "aburrido": "#9C8AA8",
    "hambre":   "#D9A441",
    "triste":   "#B24A3E",
    "dormido":  "#9A938C",
}

# En modo chatbot se sale de la paleta cálida a propósito: un azul frío avisa de
# un vistazo de que Bit está conversando y no repasando.
CHAT = "#5B86D6"

TINTA = (0.16, 0.14, 0.12)      # ojos, cejas y boca, en marrón cálido

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


# ------------------------------------------------------------------- animación

def _hex(color, alpha=1.0):
    # Las transiciones de ánimo trabajan con RGB ya interpolado. Aceptarlo aquí
    # permite que todas las piezas sigan usando las mismas ayudas de color.
    if isinstance(color, (tuple, list)):
        return float(color[0]), float(color[1]), float(color[2]), alpha
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return r, g, b, alpha


def _oscuro(color, k=0.62, alpha=1.0):
    r, g, b, _ = _hex(color)
    return r * k, g * k, b * k, alpha


def _claro(color, k=0.45, alpha=1.0):
    r, g, b, _ = _hex(color)
    return r + (1 - r) * k, g + (1 - g) * k, b + (1 - b) * k, alpha


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


def out_cubic(t):
    return 1 - (1 - t) ** 3


def out_back(t, s=2.2):
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def suave(t):
    return t * t * (3 - 2 * t)


def pulso(t):
    """Sube y baja una vez, de 0 a 1 y de vuelta a 0."""
    return math.sin(math.pi * max(0.0, min(1.0, t)))


def acercar(actual, objetivo, rapidez, dt):
    """Interpolación independiente de los FPS, sin saltos al cambiar de estado."""
    k = 1 - math.exp(-rapidez * max(0.0, dt))
    return actual + (objetivo - actual) * k


def muelle(actual, velocidad, objetivo, rapidez, dt):
    """Muelle críticamente amortiguado, estable incluso cuando se pierde un frame."""
    dt = max(0.0, dt)
    distancia = actual - objetivo
    impulso = velocidad + rapidez * distancia
    decae = math.exp(-rapidez * dt)
    return (objetivo + (distancia + impulso * dt) * decae,
            (velocidad - rapidez * impulso * dt) * decae)


class Creature(Gtk.DrawingArea):
    """Bit, dibujado a mano con Cairo.

    Nunca se queda quieto: respira, se balancea, parpadea, sigue al ratón con la
    mirada y cada pocos segundos hace un gesto suelto (saltar, estirarse,
    ladear la cabeza, agitar la antena). Los gestos puntuales se lanzan con
    `play(nombre, segundos)` y viven en `self.anims` hasta que se les acaba el
    tiempo; `phase(nombre)` devuelve por dónde van, de 0 a 1. Aparte vuelan las
    partículas: corazones al acertar, gotas al fallar, chispas y zZz.
    """

    # Lo que hace cuando nadie lo molesta (repetido = más probable). A esta
    # base se le suman gestos propios de cada ánimo en `_gestos_idle`.
    IDLES = ("parpadeo", "parpadeo", "parpadeo", "parpadeo2", "mirar", "mirar",
             "antena", "salto", "estirar", "ladear", "asentir")
    DURACION_GESTO = {
        "antena": 0.9, "salto": 0.68, "estirar": 1.3, "ladear": 1.4,
        "asentir": 0.95, "sorpresa": 0.9, "risa": 1.25, "baile": 1.9,
        "bostezo": 1.8, "suspiro": 1.35, "tiritar": 1.15,
    }
    EXPRESIONES = {"sorpresa", "risa", "baile", "bostezo", "suspiro", "tiritar"}

    def __init__(self, escala=1.0):
        super().__init__()
        self.escala = 1.0
        self.set_escala(escala)
        self.mood = "normal"
        self.energy = 1.0
        self.teaching = False
        self.charlando = False      # modo chatbot: se pinta de azul
        self.hover = False
        self.hover_suave = 0.0
        self.reduced_motion = False
        self.accessory = "ninguno"
        # Cuánto llevas sin estudiar, de 0 (acabas de repasar) a 1 (varios días).
        # Le cambia el ánimo, pero también cómo se mueve: se le nota en el cuerpo.
        self.abandono = 0.0

        self.t = 0.0
        self.anims = {}                 # nombre -> (arranque, duración)
        self.particulas = []
        self.mirada = [0.0, 0.0]        # hacia dónde apuntan las pupilas, -1..1
        self.objetivo = [0.0, 0.0]
        self.puntero = None             # posición del ratón, normalizada
        self.hablando_hasta = 0.0
        self.angulo_estrella = 0.0
        self.color_actual = _hex(MOODS["normal"])[:3]
        self.energy_mostrada = 1.0
        self.next_idle = random.uniform(1.5, 4)
        self.inercia = self.inercia_vel = 0.0
        self._pose_y = 0.0
        self._frame_time = None
        self._cache_estrella = None     # (clave, imagen) del estallido ya pintado
        self._cache_cuerpo = None       # (color, imagen) del mochi ya pintado

        self.set_draw_func(self.draw)
        raton = Gtk.EventControllerMotion()
        raton.connect("motion", self.on_motion)
        raton.connect("enter", self.on_enter)
        raton.connect("leave", self.on_leave)
        self.add_controller(raton)
        # En vez de aparecer de golpe al arrancar, cae suavemente en su sitio.
        self.play("aparecer", 0.85)
        self.connect("map", self._reiniciar_reloj)
        self.add_tick_callback(self._on_frame)

    def _reiniciar_reloj(self, *_):
        self._frame_time = None

    def _on_frame(self, _widget, reloj):
        ahora = reloj.get_frame_time()
        if self._frame_time is None:
            self._frame_time = ahora
            return GLib.SOURCE_CONTINUE
        dt = (ahora - self._frame_time) / 1_000_000
        intervalo = 0.1 if self.reduced_motion else FRAME_REPOSO / 1000
        if (self.reduced_motion or not self.ocupada()) and dt < intervalo:
            return GLib.SOURCE_CONTINUE
        self._frame_time = ahora
        self.tick(dt)
        return GLib.SOURCE_CONTINUE

    def set_escala(self, escala):
        """Tamaño de la mascota respecto al de diseño; la ventana la sigue."""
        self.escala = max(ESCALA_MIN, min(ESCALA_MAX, float(escala)))
        # Las piezas guardadas se pintan con holgura sobre el tamaño en pantalla,
        # que es lo que evita que se vean blandas cuando Bit se agranda.
        detalle = max(2, math.ceil(self.escala * 2))
        if detalle != self._ss:
            self._ss = detalle
            self._cache_estrella = self._cache_cuerpo = None
        self.set_content_width(round(ANCHO * self.escala))
        self.set_content_height(round(ALTO_PET * self.escala))
        self.queue_draw()

    # ------------------------------------------------------------------ gestos

    def play(self, nombre, dur):
        # Una expresión nueva sustituye la anterior: acertar mientras bostezaba,
        # por ejemplo, debe convertir el bostezo en risa inmediatamente.
        if nombre in self.EXPRESIONES:
            for anterior in self.EXPRESIONES - {nombre}:
                self.anims.pop(anterior, None)
        self.anims[nombre] = (self.t, max(0.001, dur))

    def phase(self, nombre):
        """0..1 mientras el gesto corre; None cuando ya terminó."""
        dato = self.anims.get(nombre)
        if dato is None:
            return None
        p = (self.t - dato[0]) / dato[1]
        return None if p >= 1.0 else max(0.0, p)

    def phase_motion(self, nombre):
        """Una animación corporal, o nada si se pidió reducir el movimiento."""
        return None if self.reduced_motion else self.phase(nombre)

    def hablar(self, segundos=1.2):
        self.hablando_hasta = self.t + segundos
        self.play("antena", 0.8)

    def saludar(self):
        self.play("saludo", 1.7)
        self.play("antena", 1.0)
        self.hablar(1.4)

    def celebrar(self):
        self.play("salto", 0.68)
        self.play("risa", 1.25)
        self.play("brillo", 1.5)
        self.emitir("corazon", 4)
        self.emitir("chispa", 9)

    def desanimar(self):
        self.play("negar", 0.8)
        self.play("suspiro", 1.35)
        self.emitir("gota", 2)

    def pensar(self):
        self.play("ladear", 1.2)
        self.emitir("nota", 2)

    def _gestos_idle(self):
        """Gestos disponibles ahora: Bit se comporta según cómo se siente."""
        gestos = list(self.IDLES)
        if self.mood == "feliz":
            gestos += ["risa", "risa", "baile", "baile"]
        elif self.mood == "aburrido":
            gestos += ["bostezo", "bostezo", "suspiro"]
        elif self.mood == "hambre":
            gestos += ["suspiro", "suspiro", "tiritar"]
        elif self.mood == "triste":
            gestos += ["suspiro", "suspiro", "tiritar", "bostezo"]
        else:
            gestos += ["sorpresa", "asentir"]
        return gestos

    def emitir(self, kind, n):
        if self.reduced_motion:
            return
        arriba = kind in ("corazon", "chispa", "nota")
        for _ in range(n):
            self.particulas.append({
                "kind": kind,
                "x": random.uniform(-24, 24),
                "y": random.uniform(-24, 4) if arriba else random.uniform(-34, -24),
                "vx": random.uniform(-26, 26) if arriba else random.uniform(4, 16),
                "vy": random.uniform(-62, -30) if arriba else random.uniform(6, 16),
                "t": 0.0,
                "vida": random.uniform(0.9, 1.7),
                "giro": random.uniform(-2.5, 2.5),
                "tam": random.uniform(0.75, 1.35),
            })

    # ------------------------------------------------------------------ ratón

    def on_motion(self, _c, x, y):
        self.hover = True
        w, h = max(1, self.get_width()), max(1, self.get_height())
        self.puntero = ((x - w / 2) / (w / 2), (y - h / 2) / (h / 2))

    def on_enter(self, _c, x, y):
        self.on_motion(_c, x, y)
        self.play("antena", 0.7)
        # A veces Bit se sorprende al verte llegar; no lo repite si ya está
        # expresando otra cosa importante.
        expresivos = {"risa", "baile", "bostezo", "suspiro", "tiritar"}
        if not expresivos.intersection(self.anims) and random.random() < 0.35:
            self.play("sorpresa", self.DURACION_GESTO["sorpresa"])

    def on_leave(self, _c):
        self.hover = False
        self.puntero = None

    # ------------------------------------------------------------------ tiempo

    def tick(self, dt):
        dt = max(0.0, min(dt, 0.1))      # reloj monotónico, acotado tras una pausa
        self.t += dt
        vel_estrella = (0.0 if self.reduced_motion else
                        0.85 if self.teaching else 0.22 * (1 - 0.75 * self.abandono))
        self.angulo_estrella = (self.angulo_estrella + vel_estrella * dt) % math.tau

        ahora = self.t
        self.anims = {k: v for k, v in self.anims.items() if ahora - v[0] < v[1]}
        objetivo_color = _hex(CHAT if self.charlando else
                              MOODS.get(self.mood, MOODS["normal"]))[:3]
        self.color_actual = tuple(acercar(a, b, 4.2, dt)
                                  for a, b in zip(self.color_actual, objetivo_color))
        self.energy_mostrada = acercar(self.energy_mostrada, self.energy, 3.6, dt)
        self.hover_suave = acercar(self.hover_suave, 1.0 if self.hover else 0.0,
                                   8.0 if self.hover else 5.0, dt)
        if self.reduced_motion:
            self.particulas.clear()
        else:
            self._mover_particulas(dt)
        self._decidir(ahora, dt)
        for i in (0, 1):                # las pupilas alcanzan su objetivo con calma
            self.mirada[i] = acercar(self.mirada[i], self.objetivo[i], 7, dt)

        dy, _, _, rot = self._pose()
        velocidad_y = (dy - self._pose_y) / max(dt, 0.001)
        objetivo = max(-0.24, min(0.24, -velocidad_y * 0.002 + rot * 0.7))
        self.inercia, self.inercia_vel = muelle(
            self.inercia, self.inercia_vel, objetivo, 12, dt)
        self._pose_y = dy

        self.queue_draw()

    def _decidir(self, ahora, dt):
        if self.mood == "dormido":
            if (not self.reduced_motion and random.random() < dt * 0.55
                    and len(self.particulas) < 6):
                self.particulas.append({
                    "kind": "z", "x": 22, "y": -26,
                    "vx": random.uniform(6, 12), "vy": random.uniform(-22, -14),
                    "t": 0.0, "vida": 2.2, "giro": 0.0,
                    "tam": random.uniform(0.8, 1.2)})
            return
        if self.abandono > 0.6 and random.random() < dt * 0.06 and not self.particulas:
            self.emitir("gota", 1)      # un suspiro, de tarde en tarde
        if self.puntero is not None:    # si hay ratón cerca, lo sigue con la mirada
            self.objetivo = [max(-1.0, min(1.0, self.puntero[0])),
                             max(-1.0, min(1.0, self.puntero[1]))]
        if ahora < self.next_idle:
            return
        self.next_idle = ahora + random.uniform(2.2, 5.2)
        gesto = random.choice(self._gestos_idle())
        if gesto == "parpadeo":
            self.play("parpadeo", 0.16)
        elif gesto == "parpadeo2":
            self.play("parpadeo", 0.38)
        elif gesto == "mirar":
            if self.puntero is None:
                self.objetivo = [random.uniform(-1, 1), random.uniform(-0.7, 0.5)]
                self.next_idle = ahora + random.uniform(0.9, 2.0)
        elif gesto == "salto" and self.energy <= 0.35:
            # Con poca energía no salta: bosteza o suspira según su estado.
            cansado = "bostezo" if self.mood == "aburrido" else "suspiro"
            self.play(cansado, self.DURACION_GESTO[cansado])
        else:
            self.play(gesto, self.DURACION_GESTO[gesto])

    def ocupada(self) -> bool:
        """¿Hay algo que merezca dibujar a plena velocidad?

        En reposo se limita la cadencia; los gestos y las transiciones de color
        siguen la frecuencia de la pantalla.
        """
        objetivo_color = _hex(CHAT if self.charlando else
                              MOODS.get(self.mood, MOODS["normal"]))[:3]
        return bool(self.anims or self.particulas or self.hover or self.teaching
                    or self.t < self.hablando_hasta
                    or abs(self.inercia) > 0.01
                    or abs(self.hover_suave - float(self.hover)) > 0.01
                    or abs(self.energy - self.energy_mostrada) > 0.01
                    or any(abs(a - b) > 0.005 for a, b in
                           zip(self.color_actual, objetivo_color))
                    or abs(self.objetivo[0] - self.mirada[0]) > 0.02
                    or abs(self.objetivo[1] - self.mirada[1]) > 0.02)

    def _mover_particulas(self, dt):
        vivas = []
        for p in self.particulas:
            p["t"] += dt
            if p["t"] >= p["vida"]:
                continue
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if p["kind"] in ("corazon", "chispa", "nota"):
                p["vy"] += 34 * dt
            elif p["kind"] == "gota":
                p["vy"] += 45 * dt
            elif p["kind"] == "z":
                # La 'z' flota suavemente hacia arriba
                p["vy"] = max(-26, p["vy"] - 2 * dt)
                p["vx"] += 3 * dt
            vivas.append(p)
        self.particulas = vivas

    # ------------------------------------------------------------------ dibujo

    def _pose(self):
        """Dónde y cómo está el cuerpo ahora mismo: (desplazamiento, escalas, giro).

        Vive fuera de `draw` porque `tick` también la consulta para decidir si
        hace falta repintar.
        """
        dormido = self.mood == "dormido"
        caido = self.abandono                      # 0 al día, 1 tras varios días
        vel = 0.85 if dormido else 1.9 - 0.55 * caido
        amplitud = 0.0 if self.reduced_motion else 1.0
        bob = (math.sin(self.t * vel) * (1.5 if dormido else 2.5) *
               (1 - 0.45 * caido) * amplitud)
        resp = (math.sin(self.t * (1.0 if dormido else 1.7 - 0.4 * caido)) *
                amplitud)
        sx, sy = 1 + resp * 0.028, 1 - resp * 0.028
        dy = bob
        # Dos frecuencias muy sutiles evitan el balanceo perfectamente pendular.
        rot = (math.sin(self.t * 0.8) * 0.012 + math.sin(self.t * 0.37) * 0.006) * amplitud
        # Sin repasos se va viniendo abajo: hunde los hombros y se aplasta un poco
        dy += 4.0 * caido
        sy -= 0.025 * caido
        sx += 0.025 * caido

        p = self.phase_motion("salto")
        if p is not None:
            # Anticipación, vuelo y aterrizaje son tres fases continuas. Antes el
            # primer fotograma ya nacía aplastado y el salto se sentía brusco.
            if p < 0.18:
                k = math.sin(math.pi * p / 0.18) ** 2
                sx += 0.16 * k; sy -= 0.14 * k; dy += 3 * k
            elif p < 0.80:
                k = math.sin(math.pi * (p - 0.18) / 0.62) ** 2
                dy -= 25 * k
                sx -= 0.065 * k; sy += 0.075 * k
            else:
                k = math.sin(math.pi * (p - 0.80) / 0.20) ** 2
                sx += 0.18 * k; sy -= 0.15 * k; dy += 2.5 * k

        p = self.phase_motion("estirar")
        if p is not None:
            k = pulso(p)
            sy += 0.16 * k; sx -= 0.10 * k; dy -= 6 * k

        p = self.phase_motion("ladear")
        if p is not None:
            rot += math.sin(math.pi * p) * 0.20

        p = self.phase_motion("negar")
        if p is not None:
            rot += math.sin(p * math.pi * 5) * 0.11 * (1 - p)

        p = self.phase_motion("asentir")
        if p is not None:
            envolvente = math.sin(math.pi * p)
            dy += math.sin(p * math.pi * 4) * 3.2 * envolvente
            rot += math.sin(p * math.pi * 4) * 0.018 * envolvente

        p = self.phase_motion("sorpresa")
        if p is not None:
            k = pulso(p)
            dy -= 4.5 * k
            sx -= 0.045 * k
            sy += 0.085 * k

        p = self.phase_motion("risa")
        if p is not None:
            envolvente = math.sin(math.pi * p)
            carcajada = abs(math.sin(p * math.pi * 6))
            dy -= carcajada * 3.2 * envolvente
            sx += carcajada * 0.035 * envolvente
            sy -= carcajada * 0.025 * envolvente

        p = self.phase_motion("baile")
        if p is not None:
            envolvente = math.sin(math.pi * p)
            paso = math.sin(p * math.pi * 6)
            dy -= abs(paso) * 5.0 * envolvente
            rot += paso * 0.13 * envolvente
            sx += abs(paso) * 0.035 * envolvente
            sy -= abs(paso) * 0.025 * envolvente

        p = self.phase_motion("bostezo")
        if p is not None:
            k = pulso(p)
            dy += 3.5 * k
            sx += 0.04 * k
            sy -= 0.05 * k
            rot -= 0.035 * k

        p = self.phase_motion("suspiro")
        if p is not None:
            k = pulso(p)
            dy += 3.0 * k
            sx += 0.035 * k
            sy -= 0.045 * k

        p = self.phase_motion("tiritar")
        if p is not None:
            envolvente = math.sin(math.pi * p)
            temblor = math.sin(p * math.pi * 14) * envolvente
            rot += temblor * 0.035
            dy += abs(temblor) * 1.2

        # Se acerca con curiosidad al cursor, pero con inercia para no dar un salto.
        sx += 0.025 * self.hover_suave
        sy += 0.025 * self.hover_suave
        if self.puntero is not None:
            rot += self.puntero[0] * 0.018 * self.hover_suave

        p = self.phase_motion("aparecer")
        if p is not None:
            k = out_back(p, 1.35)
            sx *= max(0.01, 0.62 + 0.38 * k)
            sy *= max(0.01, 0.62 + 0.38 * k)
            dy += 22 * (1 - out_cubic(p))

        return dy, sx, sy, rot

    def draw(self, _area, cr, w, h, *_):
        # Todo lo que sigue habla en unidades de diseño; el escalado es lo último
        # que se toca si algún día se quiere una mascota más grande.
        cr.save()
        k = min(w / DISENO[0], h / DISENO[1])
        cr.translate((w - DISENO[0] * k) / 2, (h - DISENO[1] * k) / 2)
        cr.scale(k, k)
        w, h = DISENO
        color = self.color_actual
        dormido = self.mood == "dormido"
        cx = w / 2
        suelo = h - 34
        base = suelo - 40                 # centro del cuerpo en reposo

        dy, sx, sy, rot = self._pose()

        # sombra en el suelo: se encoge y se aclara cuando salta
        salto = min(1.0, max(0.0, -dy - 3) / 24)
        cr.save()
        cr.translate(cx, suelo + 5)
        cr.scale(1.0, 0.26)
        radio = 38 - salto * 10
        sombra = cairo.RadialGradient(0, 0, 3, 0, 0, radio)
        sombra.add_color_stop_rgba(0, 0.08, 0.055, 0.04, 0.30 - salto * 0.16)
        sombra.add_color_stop_rgba(1, 0.08, 0.055, 0.04, 0)
        cr.arc(0, 0, radio, 0, math.tau)
        cr.set_source(sombra)
        cr.fill()
        cr.restore()

        # Las motas pasan por detrás de Bit: pueden orbitar sin cruzarle la cara.
        self._destellos_ambiente(cr, cx, base + dy, color)
        cr.save()
        cr.translate(cx, base + dy)
        cr.rotate(rot)
        cr.scale(sx, sy)
        self._estrella(cr, color)         # el estallido, detrás de todo
        self._pies(cr)
        self._brazos(cr, color)
        self._cuerpo(cr, color)
        cr.save()
        # La cara acompaña la mirada, con menos recorrido que las pupilas.
        cr.translate(self.mirada[0] * 1.2, self.mirada[1] * 0.8)
        self._cara(cr, color, dormido)
        self._accesorio(cr, color)
        cr.restore()
        cr.restore()

        self._particulas(cr, cx, base + dy)
        self._barra(cr, cx, h - 14, color)
        cr.restore()

    # -- piezas ---------------------------------------------------------------

    RX, RY = 39, 35                       # mejillas amplias, silueta de mochi

    # Cuánto más fino que la pantalla se pintan las piezas guardadas. Lo ajusta
    # `set_escala`; aquí queda el valor de una mascota a tamaño normal.
    _ss = 2

    def _forma(self, cr, rx, ry):
        """La silueta del cuerpo: un mochi, redondo arriba y ancho y plano abajo."""
        k = 0.5523
        cr.move_to(0, -ry)
        cr.curve_to(rx * 0.88 * k * 1.25, -ry, rx * 0.93, -ry * k * 1.08, rx * 0.95, -ry * 0.08)
        cr.curve_to(rx * 0.99, ry * 0.50, rx * 0.66, ry, 0, ry)
        cr.curve_to(-rx * 0.66, ry, -rx * 0.99, ry * 0.50, -rx * 0.95, -ry * 0.08)
        cr.curve_to(-rx * 0.93, -ry * k * 1.08, -rx * 0.88 * k * 1.25, -ry, 0, -ry)
        cr.close_path()

    def _halo(self, cr, dibujar, ancho=1.0):
        """Sombra suave alrededor de una pieza.

        Cairo no tiene desenfoque, así que se imita con trazos concéntricos cada
        vez más tenues. Sin esto la mascota se perdería sobre un fondo claro.
        """
        for grosor, alpha in ((7.0, 0.035), (3.4, 0.055)):
            dibujar()
            cr.set_source_rgba(0.10, 0.07, 0.05, alpha)
            cr.set_line_width(grosor * ancho)
            cr.stroke()

    def _perfil(self, cr, alpha=0.30, grosor=1.9):
        """El contorno cálido que separa a Bit de cualquier escritorio."""
        cr.set_source_rgba(0.29, 0.23, 0.19, alpha)
        cr.set_line_width(grosor)
        cr.stroke()

    def _pintar_estrella(self, cr, color, r, inercia, fase):
        """Dibuja el estallido centrado en el origen, sin girarlo ni latir.

        Es la parte cara del fotograma: once rayos con dos trazos anchos de halo
        encima. Se mantiene aparte para poder guardarla en `_cache_estrella` y
        reaprovecharla mientras la forma no cambie.
        """
        rb, wb = 21, 10.4                 # separación clara entre los once rayos

        def silueta():
            cr.new_sub_path()
            cr.arc(0, 0, rb + 3, 0, math.tau)
            # Una onda mínima recorre los rayos. Rompe la rigidez geométrica sin
            # desdibujar la silueta de once puntas que identifica a Bit.
            for i in range(11):
                cr.save()
                cr.rotate(i * math.tau / 11 + inercia * math.sin(i * 1.73) * 0.45)
                onda = 0.0 if self.reduced_motion else math.sin(fase + i * 1.73)
                ri = r * (1 + 0.045 * math.sin(i * 2.4) +
                          0.028 * onda * (1 - 0.45 * self.abandono))
                wi = wb * (1 - 0.025 * onda)
                # El segundo control va a la altura de la punta: así el rayo
                # acaba romo y redondeado, como en el logo, no en pincho.
                cr.move_to(rb, -wi)
                cr.curve_to(ri * 0.68, -wi * 0.90, ri * 1.04, -wi * 0.56, ri, 0)
                cr.curve_to(ri * 1.04, wi * 0.56, ri * 0.68, wi * 0.90, rb, wi)
                cr.close_path()
                cr.restore()

        # Sombra suave y contorno van DEBAJO del relleno: así el borde queda
        # limpio aunque los rayos se pisen entre sí.
        self._halo(cr, silueta, 1.4)
        silueta()
        self._perfil(cr, 0.34, 3.2)

        silueta()
        g = cairo.RadialGradient(-r * 0.25, -r * 0.30, 4, 0, 0, r)
        g.add_color_stop_rgba(0, *_claro(color, 0.30))
        g.add_color_stop_rgba(0.45, *_hex(color))
        g.add_color_stop_rgba(1, *_oscuro(color, 0.80))
        cr.set_source(g)
        cr.fill()

        # Relieves cortos: cada pétalo tiene volumen sin añadir textura ruidosa.
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for i in range(11):
            cr.save()
            cr.rotate(i * math.tau / 11 + inercia * math.sin(i * 1.73) * 0.45)
            cr.move_to(r * 0.67, -3)
            cr.curve_to(r * 0.74, -4.5, r * 0.83, -3.5, r * 0.88, -1.5)
            cr.set_source_rgba(1, 0.96, 0.87, 0.24)
            cr.set_line_width(2.1)
            cr.stroke()
            cr.restore()

    def _estrella_grabada(self, color, r, inercia, fase):
        """El estallido ya pintado en una imagen, listo para girar y pegar.

        Girar y escalar son cosas que Cairo hace al pegar la imagen, así que no
        entran en la clave: mientras el color, el tamaño y la onda sigan siendo
        los mismos, el fotograma siguiente reutiliza este dibujo tal cual.
        """
        clave = (tuple(round(c, 2) for c in color[:3]), round(r, 1),
                 round(inercia, 2), round(fase, 2), self.reduced_motion,
                 round(self.abandono, 2))
        if self._cache_estrella and self._cache_estrella[0] == clave:
            return self._cache_estrella[1]

        # El lienzo se reaprovecha entre repintados: pedir 280 kB al sistema cada
        # vez que la onda avanza costaba más que volver a trazar los rayos.
        lado = ESTRELLA_LADO * self._ss
        superficie = self._cache_estrella[1] if self._cache_estrella else \
            cairo.ImageSurface(cairo.FORMAT_ARGB32, lado, lado)
        ctx = cairo.Context(superficie)
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.restore()
        ctx.scale(self._ss, self._ss)
        ctx.translate(ESTRELLA_LADO / 2, ESTRELLA_LADO / 2)
        self._pintar_estrella(ctx, color, r, inercia, fase)
        superficie.flush()
        self._cache_estrella = (clave, superficie)
        return superficie

    def _estrella(self, cr, color):
        """El estallido de once rayos: es el cuerpo de Bit y su estado de ánimo.

        Va detrás del mochi, en el color del humor, y gira despacio todo el rato:
        se acelera cuando tiene algo que enseñarte, el gesto «antena» le da un
        tirón, y cuando llevas días sin aparecer casi se para y se encoge. Es el
        guiño a la mascota de Claude, dibujado rayo a rayo.

        El dibujo en sí sale de `_estrella_grabada`, que lo guarda entre
        fotogramas; aquí solo se le da la vuelta y el latido, que son justo lo
        que cambia siempre y lo que Cairo sabe hacer barato al pegar la imagen.
        """
        cx, cy = 0, -19
        r = 54 * (1 - 0.10 * self.abandono)
        inercia = 0.0 if self.reduced_motion else self.inercia
        vuelta = self.angulo_estrella + inercia
        p = self.phase_motion("antena")
        if p is not None:
            vuelta += math.sin(p * math.pi * 4) * 0.35 * (1 - p)
        latido = (1.0 if self.reduced_motion else
                  1 + math.sin(self.t * (5 if self.teaching else 1.6)) *
                  (0.035 if self.teaching else 0.015) + 0.025 * self.hover_suave)

        if self.teaching:                 # un halo cálido cuando está enseñando
            g = cairo.RadialGradient(cx, cy, r * 0.6, cx, cy, r * 1.45)
            g.add_color_stop_rgba(0, *_hex(color, 0.30))
            g.add_color_stop_rgba(1, *_hex(color, 0.0))
            cr.arc(cx, cy, r * 1.45, 0, math.tau)
            cr.set_source(g)
            cr.fill()

        # La onda de los rayos se redondea antes de pedir el dibujo: mueve las
        # puntas menos de dos píxeles, así que avanzar a saltos no se nota y en
        # cambio deja que varios fotogramas seguidos compartan la misma imagen.
        fase = 0.0 if self.reduced_motion else (
            round(self.t * 1.35 / ESTRELLA_PASO_ONDA) * ESTRELLA_PASO_ONDA)
        superficie = self._estrella_grabada(color, r, inercia, fase)

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(vuelta)
        cr.scale(latido / self._ss, latido / self._ss)
        lado = ESTRELLA_LADO * self._ss
        cr.set_source_surface(superficie, -lado / 2, -lado / 2)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        cr.restore()

    def _cuerpo(self, cr, color):
        """El mochi, con su sombra, sus luces y su insignia.

        El dibujo no depende del tiempo —la respiración y el balanceo se los
        aplica `draw` por fuera, al deformar el lienzo—, así que se guarda ya
        pintado y solo se vuelve a trazar cuando cambia el color del ánimo.
        """
        cr.save()
        cr.scale(1 / self._ss, 1 / self._ss)
        lado = CUERPO_LADO * self._ss
        cr.set_source_surface(self._cuerpo_grabado(color), -lado / 2, -lado / 2)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        cr.restore()

        p = self.phase_motion("brillo")  # aro que se expande al celebrar
        if p is not None:
            cr.arc(0, -10, 62 + out_cubic(p) * 26, 0, math.tau)
            cr.set_source_rgba(*_hex(color, (1 - p) * 0.55))
            cr.set_line_width(3.5 * (1 - p))
            cr.stroke()

    def _cuerpo_grabado(self, color):
        """El mochi ya pintado. Solo el color del ánimo invalida la copia."""
        clave = tuple(round(c, 2) for c in color[:3])
        if self._cache_cuerpo and self._cache_cuerpo[0] == clave:
            return self._cache_cuerpo[1]

        lado = CUERPO_LADO * self._ss
        superficie = self._cache_cuerpo[1] if self._cache_cuerpo else \
            cairo.ImageSurface(cairo.FORMAT_ARGB32, lado, lado)
        ctx = cairo.Context(superficie)
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.restore()
        ctx.scale(self._ss, self._ss)
        ctx.translate(CUERPO_LADO / 2, CUERPO_LADO / 2)
        self._pintar_cuerpo(ctx, color)
        superficie.flush()
        self._cache_cuerpo = (clave, superficie)
        return superficie

    def _pintar_cuerpo(self, cr, color):
        rx, ry = self.RX, self.RY

        # sombra de contacto del mochi sobre el estallido
        oc = cairo.RadialGradient(0, 4, rx * 0.7, 0, 4, rx + 13)
        oc.add_color_stop_rgba(0, 0.16, 0.10, 0.07, 0.34)
        oc.add_color_stop_rgba(1, 0.16, 0.10, 0.07, 0.0)
        cr.arc(0, 4, rx + 13, 0, math.tau)
        cr.set_source(oc)
        cr.fill()

        self._halo(cr, lambda: self._forma(cr, rx, ry), 0.8)

        g = cairo.RadialGradient(-12, -16, 4, 0, 6, rx + 24)
        g.add_color_stop_rgba(0, *_hex(CREMA_CLARO))
        g.add_color_stop_rgba(0.55, *_hex(CREMA))
        g.add_color_stop_rgba(1, *_hex(CREMA_SOMBRA))
        self._forma(cr, rx, ry)
        cr.set_source(g)
        cr.fill_preserve()

        cr.save()
        cr.clip()                       # todo lo que sigue, dentro del cuerpo

        # luz cenital
        lz = cairo.LinearGradient(0, -ry, 0, -ry * 0.1)
        lz.add_color_stop_rgba(0, 1, 1, 1, 0.42)
        lz.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.rectangle(-rx, -ry, rx * 2, ry)
        cr.set_source(lz)
        cr.fill()

        # rebote del color del estallido en el borde
        rb = cairo.RadialGradient(0, 2, rx * 0.72, 0, 2, rx + 2)
        rb.add_color_stop_rgba(0, *_hex(color, 0.0))
        rb.add_color_stop_rgba(1, *_hex(color, 0.20))
        cr.rectangle(-rx - 2, -ry - 2, rx * 2 + 4, ry * 2 + 4)
        cr.set_source(rb)
        cr.fill()

        # y una ocupación suave abajo, donde se apoyan los pies
        oc = cairo.RadialGradient(0, ry, 4, 0, ry, 26)
        oc.add_color_stop_rgba(0, 0.30, 0.22, 0.17, 0.16)
        oc.add_color_stop_rgba(1, 0.30, 0.22, 0.17, 0)
        cr.rectangle(-rx, ry - 28, rx * 2, 28)
        cr.set_source(oc)
        cr.fill()
        cr.restore()

        self._forma(cr, rx, ry)
        self._perfil(cr)

        # Pequeña insignia de luz: un detalle propio, legible incluso al 50 %.
        cr.move_to(0, 22)
        cr.curve_to(1, 25, 2, 26, 5, 27)
        cr.curve_to(2, 28, 1, 29, 0, 32)
        cr.curve_to(-1, 29, -2, 28, -5, 27)
        cr.curve_to(-2, 26, -1, 25, 0, 22)
        cr.set_source_rgba(*_hex(color, 0.72))
        cr.fill()

    def _pies(self, cr):
        """Dos pies rechonchos que asoman bajo el mochi y alternan con el balanceo."""
        paso = 0.0 if self.reduced_motion else math.sin(self.t * 1.9) * 1.6
        baile = self.phase_motion("baile")
        baile_env = math.sin(math.pi * baile) if baile is not None else 0.0
        baile_paso = math.sin(baile * math.pi * 6) if baile is not None else 0.0
        for lado, fase in ((-1, paso), (1, -paso)):
            levanta = max(0.0, baile_paso * lado) * 7.0 * baile_env

            def pie(lado=lado, fase=fase, levanta=levanta):
                cr.save()
                cr.translate(lado * (15 + levanta * 0.35),
                             self.RY - 1 + fase * 0.4 - levanta)
                cr.rotate(lado * (0.12 + levanta * 0.025))
                cr.scale(1.0, 0.58)
                cr.arc(0, 0, 11.5, 0, math.tau)
                cr.restore()
            self._halo(cr, pie, 0.7)
            pie()
            cr.set_source_rgba(*_hex(CREMA_SOMBRA))
            cr.fill_preserve()
            self._perfil(cr, 0.30)

    def _brazos(self, cr, color):
        """Dos brazos cortos con manopla; el derecho saluda cuando toca.

        Se dibuja solo el derecho: el izquierdo es el mismo trazo en espejo, así
        el balanceo sale simétrico sin repetir la trigonometría.
        """
        vaiven = 0.0 if self.reduced_motion else math.sin(self.t * 1.9) * 0.10
        saludo = self.phase_motion("saludo")
        baile = self.phase_motion("baile")
        sorpresa = self.phase_motion("sorpresa")
        bostezo = self.phase_motion("bostezo")
        suspiro = self.phase_motion("suspiro")
        for lado in (1, -1):
            ang = 0.62 + vaiven - 0.10 * self.hover_suave
            largo = 15 + 1.2 * self.hover_suave
            if baile is not None:
                envolvente = math.sin(math.pi * baile)
                ang -= (0.75 + lado * math.sin(baile * math.pi * 6) * 0.55) * envolvente
                largo += 3 * envolvente
            if sorpresa is not None:
                k = pulso(sorpresa)
                ang += (-0.72 - ang) * k
                largo += 3 * k
            if suspiro is not None:
                ang += 0.28 * pulso(suspiro)
            if lado == 1 and bostezo is not None:
                k = pulso(bostezo)
                ang += (-2.72 - ang) * k
                largo += 3 * k
            if lado == 1 and saludo is not None:
                k = suave(min(1.0, saludo * 4)) * (1 - max(0.0, (saludo - 0.75) / 0.25))
                # Hacia arriba y hacia fuera: con el brazo detrás del mochi, si
                # sube recto la manopla queda tapada y el saludo no se ve.
                ang = 0.62 - (1.95 + math.sin(saludo * math.pi * 6) * 0.30) * k
                largo = 15 + 7 * k

            cr.save()
            cr.translate(lado * 30, 5)
            cr.scale(lado, 1)               # el izquierdo, en espejo
            cr.rotate(ang)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for grosor, rgba in ((13.5, (0.10, 0.07, 0.05, 0.06)),
                                 (11.6, (0.29, 0.23, 0.19, 0.30)),
                                 (9.4, _hex(CREMA))):
                cr.move_to(0, 0)
                cr.line_to(largo, 0)
                cr.set_source_rgba(*rgba)
                cr.set_line_width(grosor)
                cr.stroke()
            cr.arc(largo + 1.5, 0, 6.6, 0, math.tau)     # la manopla
            cr.set_source_rgba(*_hex(CREMA_CLARO))
            cr.fill_preserve()
            self._perfil(cr, 0.28)
            cr.restore()

    def _cara(self, cr, color, dormido):
        apertura = {"aburrido": 0.55, "hambre": 0.82, "triste": 0.76}.get(self.mood, 1.0)
        if dormido:
            apertura = 0.0
        p = self.phase("parpadeo")
        if p is not None:
            doble = self.anims["parpadeo"][1] > 0.3     # el guiño largo son dos
            apertura *= 1 - abs(math.sin(math.pi * p * (2 if doble else 1)))

        sorpresa = self.phase("sorpresa")
        risa = self.phase("risa")
        bostezo = self.phase("bostezo")
        if sorpresa is not None:
            apertura = max(apertura, 1.0 + 0.25 * pulso(sorpresa))
        if risa is not None:
            apertura *= max(0.08, 1 - 1.15 * pulso(risa))
        if bostezo is not None:
            apertura *= max(0.06, 1 - 1.05 * pulso(bostezo))
        cerrado = apertura < 0.16

        mx, my = self.mirada[0] * 3.0, self.mirada[1] * 2.2
        pupila_sorpresa = pulso(sorpresa) if sorpresa is not None else 0.0
        for dx in (-13.5, 13.5):
            ex, ey = dx, -5
            if cerrado:                 # ojo cerrado: un arco tranquilo
                curva = -5.8 if self.mood == "feliz" or risa is not None else 4.8
                cr.move_to(ex - 7.5, ey)
                cr.curve_to(ex - 2.4, ey + curva, ex + 2.4, ey + curva, ex + 7.5, ey)
                cr.set_source_rgba(*TINTA, 0.92)
                cr.set_line_width(2.8)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.stroke()
                continue

            def ojo():
                cr.save()
                cr.translate(ex, ey)
                cr.scale(1.0, 1.18 * apertura)
                cr.arc(0, 0, 9.2, 0, math.tau)
                cr.restore()

            ojo()                        # blanco del ojo
            cr.set_source_rgba(1, 0.995, 0.985, 1)
            cr.fill_preserve()
            cr.set_source_rgba(0.29, 0.23, 0.19, 0.20)
            cr.set_line_width(1.3)
            cr.stroke()

            cr.save()                    # todo lo de dentro, recortado al ojo
            ojo()
            cr.clip()
            # sombra del párpado
            cr.rectangle(-10 + ex, -12 + ey, 20, 6.5)
            cr.set_source_rgba(0.29, 0.23, 0.19, 0.14)
            cr.fill()
            # iris y pupila
            px, py = ex + mx, ey + my * apertura
            iris_r = 6.0 - 1.0 * pupila_sorpresa
            pupila_r = 4.3 - 0.9 * pupila_sorpresa
            cr.save()
            cr.translate(px, py)
            cr.scale(1.0, max(0.3, min(1.0, apertura * 1.05)))
            cr.arc(0, 0, iris_r, 0, math.tau)
            cr.restore()
            iris = cairo.LinearGradient(px, py - 6, px, py + 6)
            iris.add_color_stop_rgb(0, 0.21, 0.14, 0.12)
            iris.add_color_stop_rgb(1, 0.58, 0.38, 0.22)
            cr.set_source(iris)
            cr.fill()
            cr.save()
            cr.translate(px, py)
            cr.scale(1.0, max(0.3, min(1.0, apertura * 1.05)))
            cr.arc(0, 0.4, pupila_r, 0, math.tau)
            cr.restore()
            cr.set_source_rgba(*TINTA)
            cr.fill()
            # dos brillos: el grande arriba a la izquierda, el chico abajo
            cr.arc(px - 2.3, py - 2.6, 2.5, 0, math.tau)
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.fill()
            cr.arc(px + 2.2, py + 2.4, 1.15, 0, math.tau)
            cr.set_source_rgba(1, 1, 1, 0.6)
            cr.fill()
            cr.restore()

        if self.abandono > 0.45 and not dormido:
            self._ojeras(cr, min(1.0, (self.abandono - 0.45) / 0.55))
        self._cejas(cr, cerrado)
        self._boca(cr, color)
        self._cachetes(cr, color)

    def _ojeras(self, cr, k):
        """Dos sombras bajo los ojos: lo que se le pone cuando no apareces."""
        cr.set_source_rgba(0.42, 0.30, 0.34, 0.24 * k)
        cr.set_line_width(2.6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for dx in (-13.5, 13.5):
            cr.move_to(dx - 7, 6.5)
            cr.curve_to(dx - 2.6, 9.4, dx + 2.6, 9.4, dx + 7, 6.5)
            cr.stroke()

    def _cachetes(self, cr, color):
        fuerte = (self.mood == "feliz" or self.phase("brillo") is not None or
                  self.phase("risa") is not None or self.phase("baile") is not None)
        for dx in (-23, 23):
            g = cairo.RadialGradient(dx, 8, 1, dx, 8, 8)
            g.add_color_stop_rgba(0, *_hex(color, 0.40 if fuerte else 0.22))
            g.add_color_stop_rgba(1, *_hex(color, 0.0))
            cr.save()
            cr.translate(dx, 8)
            cr.scale(1.3, 1.0)
            cr.arc(0, 0, 8, 0, math.tau)
            cr.restore()
            cr.set_source(g)
            cr.fill()

    def _cejas(self, cr, cerrado):
        if self.mood == "dormido":
            return
        # Positivo = extremo interior hacia arriba, que es la cara de pena
        inclinacion = {"triste": 0.46, "hambre": 0.30, "aburrido": 0.14,
                       "feliz": -0.20}.get(self.mood, 0.0)
        inclinacion -= 0.08 * self.hover_suave
        alto = -21 - (2 if self.mood == "feliz" else 0) - 1.8 * self.hover_suave
        sorpresa = self.phase("sorpresa")
        risa = self.phase("risa")
        bostezo = self.phase("bostezo")
        if sorpresa is not None:
            k = pulso(sorpresa)
            alto -= 4.5 * k
            inclinacion -= 0.16 * k
        if risa is not None:
            alto -= 2.0 * pulso(risa)
            inclinacion -= 0.12 * pulso(risa)
        if bostezo is not None:
            alto += 1.5 * pulso(bostezo)
        marcada = self.mood in ("triste", "hambre", "aburrido", "feliz")
        cr.set_source_rgba(*TINTA, 0.72 if marcada else 0.50)
        cr.set_line_width(2.7 if marcada else 2.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for lado in (-1, 1):
            cr.save()
            cr.translate(lado * 13.5, alto)
            cr.rotate(inclinacion * lado)
            cr.move_to(-6, 0)
            cr.curve_to(-2, -2.2, 2, -2.2, 6, 0)
            cr.stroke()
            cr.restore()

    def _boca(self, cr, color):
        my = 13
        cr.set_source_rgba(*TINTA, 0.9)
        cr.set_line_width(2.7)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if self.t < self.hablando_hasta:          # habla: la boca se abre y cierra
            a = 3.0 if self.reduced_motion else 2.4 + abs(math.sin(self.t * 11)) * 4.6
            cr.save()
            cr.translate(0, my + 1)
            cr.scale(1.0, a / 6.8)
            cr.arc(0, 0, 6.8, 0, math.tau)
            cr.restore()
            cr.fill()
            return

        sorpresa = self.phase("sorpresa")
        bostezo = self.phase("bostezo")
        suspiro = self.phase("suspiro")
        risa = self.phase("risa")
        baile = self.phase("baile")

        if sorpresa is not None:
            k = pulso(sorpresa)
            cr.save()
            cr.translate(0, my + 1)
            cr.scale(0.72 + 0.18 * k, 0.86 + 0.45 * k)
            cr.arc(0, 0, 5.2, 0, math.tau)
            cr.restore()
            cr.fill()
            return
        if bostezo is not None:
            k = pulso(bostezo)
            cr.save()
            cr.translate(0, my + 2)
            cr.scale(0.82 + 0.18 * k, 0.68 + 0.72 * k)
            cr.arc(0, 0, 7.2, 0, math.tau)
            cr.restore()
            cr.fill_preserve()
            cr.save()
            cr.clip()
            cr.arc(0, my + 8, 4.7, 0, math.tau)
            cr.set_source_rgba(*_hex(TERRACOTA, 0.82))
            cr.fill()
            cr.restore()
            return
        if suspiro is not None:
            k = pulso(suspiro)
            cr.save()
            cr.translate(0, my + 1)
            cr.scale(1.0, 0.78 + 0.28 * k)
            cr.arc(0, 0, 3.6 + 1.2 * k, 0, math.tau)
            cr.restore()
            cr.fill()
            return
        if self.mood == "feliz" or risa is not None or baile is not None:
            # Sonrisa abierta, con lengua. En una carcajada crece al centro del gesto.
            fuerza = (pulso(risa) if risa is not None else
                      pulso(baile) * 0.55 if baile is not None else 0.35)
            cr.save()
            cr.translate(0, my + 2)
            cr.scale(1.0 + 0.08 * fuerza, 1.0 + 0.14 * fuerza)
            cr.translate(0, -(my + 2))
            cr.move_to(-10, my - 4)
            cr.curve_to(-9.5, my + 9.5, 9.5, my + 9.5, 10, my - 4)
            cr.close_path()
            cr.set_source_rgba(*TINTA, 0.92)
            cr.fill_preserve()
            cr.save()
            cr.clip()
            cr.arc(0, my + 9, 5.4, 0, math.tau)
            cr.set_source_rgba(*_hex(TERRACOTA, 0.95))
            cr.fill()
            cr.restore()
            cr.restore()
        elif self.mood == "triste":
            cr.arc(0, my + 10.5, 8.5, 1.20 * math.pi, 1.80 * math.pi)
            cr.stroke()
        elif self.mood == "hambre":                # boca ondulada
            cr.move_to(-8, my)
            cr.curve_to(-4, my - 3.8, -0.5, my + 3.4, 0, my)
            cr.curve_to(1, my - 3.4, 4.5, my + 3.8, 8, my)
            cr.stroke()
        elif self.mood == "dormido":
            cr.move_to(-5, my)
            cr.line_to(5, my)
            cr.stroke()
        else:
            # Al acercarte, la sonrisa se abre un poco: una respuesta pequeña
            # pero inmediata que acompaña a los ojos y a la inclinación.
            sonrisa = self.hover_suave if self.mood == "normal" else 0.0
            ancho = 7.5 + 2.2 * sonrisa
            cr.save()
            cr.translate(0, my - 3)
            cr.scale(1.0, 1.0 + 0.16 * sonrisa)
            cr.arc(0, 0, ancho, 0.16 * math.pi, 0.84 * math.pi)
            cr.restore()
            cr.stroke()

    # -- adornos --------------------------------------------------------------

    def _accesorio(self, cr, color):
        """Accesorios desbloqueables, todos vectoriales y de coste constante."""
        if self.accessory == "panuelo":
            # Banda baja para no tapar la boca, con el nudo hacia la derecha.
            cr.move_to(-30, 21)
            cr.curve_to(-16, 27, 16, 27, 30, 21)
            cr.line_to(29, 28)
            cr.curve_to(12, 33, -13, 33, -29, 28)
            cr.close_path()
            cr.set_source_rgba(*_oscuro(color, 0.82))
            cr.fill_preserve()
            self._perfil(cr, 0.26, 1.5)
            cr.arc(29, 27, 5.4, 0, math.tau)
            cr.set_source_rgba(*_hex(color))
            cr.fill_preserve()
            self._perfil(cr, 0.28, 1.4)
            cr.move_to(31, 30)
            cr.line_to(38, 39)
            cr.line_to(27, 37)
            cr.close_path()
            cr.set_source_rgba(*_hex(color))
            cr.fill_preserve()
            self._perfil(cr, 0.24, 1.3)
        elif self.accessory == "gafas":
            cr.set_source_rgba(*TINTA, 0.78)
            cr.set_line_width(2.4)
            for dx in (-13.5, 13.5):
                cr.save()
                cr.translate(dx, -5)
                cr.scale(1.12, 1.0)
                cr.arc(0, 0, 10.7, 0, math.tau)
                cr.restore()
                cr.stroke()
            cr.move_to(-2.8, -6)
            cr.curve_to(-1.3, -8, 1.3, -8, 2.8, -6)
            cr.stroke()
            cr.move_to(-24, -8); cr.line_to(-34, -12); cr.stroke()
            cr.move_to(24, -8); cr.line_to(34, -12); cr.stroke()
        elif self.accessory == "corona":
            cr.move_to(-18, -31)
            cr.line_to(-21, -49)
            cr.line_to(-9, -40)
            cr.line_to(0, -54)
            cr.line_to(9, -40)
            cr.line_to(21, -49)
            cr.line_to(18, -31)
            cr.close_path()
            oro = "#F2C14E"
            cr.set_source_rgba(*_hex(oro))
            cr.fill_preserve()
            self._perfil(cr, 0.36, 1.8)
            for x, y in ((-12, -43), (0, -48), (12, -43)):
                cr.arc(x, y, 2.1, 0, math.tau)
                cr.set_source_rgba(*_claro(color, 0.25))
                cr.fill()

    def _destellos_ambiente(self, cr, cx, cy, color):
        """Tres motas de luz cuando Bit está receptivo; discretas y deterministas."""
        if self.reduced_motion:
            return
        emocion = (0.46 if (self.phase("risa") is not None or
                            self.phase("baile") is not None) else
                   0.34 if self.phase("sorpresa") is not None else 0.0)
        intensidad = max(0.34 if self.mood == "feliz" else 0.0,
                         0.55 if self.teaching else 0.0,
                         0.28 * self.hover_suave, emocion)
        if intensidad <= 0:
            return
        for i, radio in enumerate((61, 68, 64)):
            fase = self.t * (0.42 + i * 0.07) + i * math.tau / 3
            pulso_luz = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.t * 2.2 + i * 2.1))
            x = cx + math.cos(fase) * radio
            y = cy - 18 + math.sin(fase) * radio * 0.72
            cr.arc(x, y, 1.5 + 0.7 * pulso_luz, 0, math.tau)
            cr.set_source_rgba(*_claro(color, 0.62, intensidad * pulso_luz))
            cr.fill()

    def _particulas(self, cr, cx, cy):
        for p in self.particulas:
            k = p["t"] / p["vida"]
            base_alpha = 0.85 if p["kind"] == "z" else 1.0
            alpha = min(1.0, (1 - k) * 2.2) * base_alpha
            cr.save()
            cr.translate(cx + p["x"], cy + p["y"])
            cr.rotate(p["giro"] * k)
            cr.scale(p["tam"], p["tam"])
            if p["kind"] == "corazon":
                self._corazon(cr, alpha)
            elif p["kind"] == "chispa":
                self._chispa(cr, alpha)
            elif p["kind"] == "gota":
                cr.arc(0, 0, 3.4, 0, math.tau)
                cr.set_source_rgba(*_hex("#7FA3C0", alpha * 0.9))
                cr.fill()
            elif p["kind"] == "nota":
                cr.select_font_face("sans")
                cr.set_font_size(13)
                cr.move_to(-4, 4)
                cr.set_source_rgba(*_hex("#B08AA8", alpha))
                cr.show_text("♪")
            else:                                   # z
                cr.select_font_face("sans")
                cr.set_font_size(13)
                cr.move_to(-4, 4)
                cr.set_source_rgba(*_hex(CREMA, alpha * 0.85))
                cr.show_text("z")
            cr.restore()

    def _corazon(self, cr, alpha):
        cr.move_to(0, 4.5)
        cr.curve_to(-6.5, -1, -4.5, -7, 0, -3.2)
        cr.curve_to(4.5, -7, 6.5, -1, 0, 4.5)
        cr.close_path()
        cr.set_source_rgba(*_hex(TERRACOTA, alpha))
        cr.fill()

    def _chispa(self, cr, alpha):
        cr.set_source_rgba(*_hex("#D9A441", alpha))
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for ang in (0, math.pi / 2):
            cr.save()
            cr.rotate(ang)
            cr.move_to(0, -4)
            cr.line_to(0, 4)
            cr.stroke()
            cr.restore()

    def _barra(self, cr, cx, y, color):
        """La energía: baja con las horas sin repasar y con lo que se acumula."""
        ancho, alto = 78, 7
        x = cx - ancho / 2
        r = alto / 2

        # Fondo de la barra
        cr.new_sub_path()
        cr.arc(x + ancho - r, y + r, r, -math.pi / 2, math.pi / 2)
        cr.arc(x + r, y + r, r, math.pi / 2, 1.5 * math.pi)
        cr.close_path()
        cr.set_source_rgba(0.16, 0.14, 0.12, 0.22)
        cr.fill()

        # Barra llena con esquinas redondeadas
        energia = max(0.0, min(1.0, self.energy_mostrada))
        w_llena = max(alto, ancho * energia)
        cr.save()
        cr.rectangle(x, y, ancho * energia, alto)
        cr.clip()                        # cero energía debe dejar la pista vacía
        cr.new_sub_path()
        cr.arc(x + w_llena - r, y + r, r, -math.pi / 2, math.pi / 2)
        cr.arc(x + r, y + r, r, math.pi / 2, 1.5 * math.pi)
        cr.close_path()
        cr.set_source_rgba(*_hex(color, 0.95))
        cr.fill_preserve()
        cr.clip()

        if energia > 0.05 and not self.reduced_motion:
            q = (self.t * 0.35) % 1.6
            if q < 1.0:
                bx = x + q * w_llena
                g = cairo.LinearGradient(bx - 9, 0, bx + 9, 0)
                g.add_color_stop_rgba(0, 1, 1, 1, 0)
                g.add_color_stop_rgba(0.5, 1, 1, 1, 0.35)
                g.add_color_stop_rgba(1, 1, 1, 1, 0)
                cr.rectangle(x, y, w_llena, alto)
                cr.set_source(g)
                cr.fill()
        cr.restore()

        # Borde de cristal: mantiene legible el medidor sobre fotos y fondos claros.
        cr.new_sub_path()
        cr.arc(x + ancho - r, y + r, r, -math.pi / 2, math.pi / 2)
        cr.arc(x + r, y + r, r, math.pi / 2, 1.5 * math.pi)
        cr.close_path()
        cr.set_source_rgba(1, 1, 1, 0.20)
        cr.set_line_width(1.0)
        cr.stroke()


class PetWindow(Gtk.ApplicationWindow):
    """Ventana sin bordes, siempre encima, con la criatura y su globo de diálogo."""

    def __init__(self, app, con):
        super().__init__(application=app, title=f"AppStudy · {NOMBRE}")
        self.con = con
        self.xid = None
        self.pos = None
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

        self.creature = Creature(self.escala_guardada())
        self.card_scale = self.card_escala_guardada()
        self.card_css_provider = Gtk.CssProvider()
        disp = Gdk.Display.get_default()
        if disp:
            Gtk.StyleContext.add_provider_for_display(
                disp, self.card_css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.aplicar_escala_tarjeta()

        handle = Gtk.WindowHandle(css_classes=["as-pet-handle"])
        handle.set_child(self.creature)
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

        self.menu = Gtk.PopoverMenu.new_from_model(self.build_menu())
        self.menu.set_parent(self.creature)
        self.menu.set_has_arrow(False)

        self.connect("map", self.on_map)
        GLib.timeout_add_seconds(CHECK_EVERY, self.on_check)
        GLib.timeout_add_seconds(30, self.save_position)
        self.refresh_stats()

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
        GLib.timeout_add_seconds(2, self.restore_position)
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
        self.wmctrl("-e", f"0,{x},{y},-1,-1")

    def restore_position(self):
        guardada = db.get_meta(self.con, "pet_pos")
        if guardada:
            try:
                x, y = json.loads(guardada)
                self.move_to(int(x), int(y))
                self.pos = (int(x), int(y))
                return False
            except (ValueError, TypeError):
                pass
        monitor = self.get_display().get_monitors().get_item(0)
        area = monitor.get_geometry() if monitor else None
        x = (area.x + area.width - ANCHO - 40) if area else 900
        y = (area.y + 60) if area else 80
        self.move_to(x, y)
        self.pos = (x, y)
        return False

    def save_position(self):
        actual = self.read_position()
        if actual and actual != self.pos:
            self.pos = actual
            db.set_meta(self.con, "pet_pos", json.dumps(list(actual)))
        return True

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

        if self.dormida():
            mood = "dormido"
        elif horas >= HORAS_TRISTE:
            mood = "triste"
        elif horas >= HORAS_HAMBRE:
            mood = "hambre"
        elif t["pendientes"] == 0 and t["hoy"] > 0:
            mood = "feliz"
        elif horas >= HORAS_ABURRIDO:
            mood = "aburrido"
        elif energia < 0.3:
            mood = "hambre"
        else:
            mood = "normal"

        self.stats = {**t, "energia": energia, "horas": horas, "abandono": abandono}
        if abs(self.escala_guardada() - self.creature.escala) > 0.01:
            self.creature.set_escala(self.escala_guardada())   # cambiado desde Ajustes
        nueva_card_escala = self.card_escala_guardada()
        if abs(nueva_card_escala - getattr(self, "card_scale", 1.15)) > 0.01:
            self.card_scale = nueva_card_escala
            self.aplicar_escala_tarjeta()
            self.refrescar_globo_activo()
        self.creature.mood = mood
        self.creature.energy = energia
        self.creature.abandono = 0.0 if mood == "dormido" else abandono
        self.creature.reduced_motion = (str(
            db.get_meta(self.con, "reduced_motion", "0")).lower() in ("1", "true")
            or not self.get_settings().get_property("gtk-enable-animations"))
        self.bubble.set_transition_duration(0 if self.creature.reduced_motion else 240)
        repasos = total_repasos(self.con)
        self.creature.accessory = accesorio_valido(
            str(db.get_meta(self.con, "pet_accessory", "ninguno")), repasos)
        self.creature.teaching = self.bubble.get_reveal_child()
        self.set_tooltip_text(
            f"{NOMBRE} · {t['pendientes']} pendientes · {t['hoy']} hoy · "
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
        self.menu.set_menu_model(self.build_menu())     # cambia la etiqueta

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
            self.creature.desanimar()
            self.say(reproche(t["horas"]), titulo=f"{NOMBRE} te echa de menos",
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
            # Nada que repasar: entonces te deja una frase para el rato
            self.quote()
        elif random.random() < 0.30:
            self.quote()
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
        GLib.timeout_add(260, lambda: (self.clear_bubble(), False)[1])

    def open_bubble(self):
        self.sonar("globo")
        self.bubble.set_reveal_child(True)
        self.creature.teaching = True
        self.creature.hablar(1.3)
        self.last_nag = time.time()
        self.keep_above()
        GLib.timeout_add(900, self.fit_on_screen)

    def fit_on_screen(self):
        """Si el globo se sale de la pantalla, acerca la ventana al borde."""
        pos = self.read_position()
        if not pos:
            return False
        monitor = self.get_display().get_monitor_at_surface(self.get_surface())
        if monitor is None:
            return False
        area = monitor.get_geometry()
        x = min(pos[0], area.x + area.width - self.get_width() - 8)
        y = min(pos[1], area.y + area.height - self.get_height() - 8)
        x, y = max(area.x + 8, x), max(area.y + 8, y)
        if (x, y) != pos:
            self.move_to(x, y)
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
                    duracion = voz.hablar(juicio["feedback"], self.voz_cfg, card=self.card)
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

    def on_voz_terminada(self):
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

    def say(self, texto, titulo=f"{NOMBRE} dice", boton=None):
        """Un mensaje corto, con un botón opcional."""
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

    def teach(self):
        """Saca una tarjeta y te la explica: pregunta y respuesta, las dos."""
        current_id = self.card["id"] if self.card else None
        if not hasattr(self, "recent_card_ids"):
            self.recent_card_ids = []
        if current_id and current_id not in self.recent_card_ids:
            self.recent_card_ids.append(current_id)
            if len(self.recent_card_ids) > 30:
                self.recent_card_ids.pop(0)

        self.card = scheduler.next_card(self.con, exclude_ids=self.recent_card_ids,
                                        exclude_id=current_id)
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

        self.card = scheduler.next_card(self.con, exclude_ids=self.recent_card_ids,
                                        exclude_id=current_id)
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

        cabecera = self.bubble_header("💬 Chat con Bit", CHAT)
        self.bubble_box.append(cabecera)
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

        entrada = Gtk.Entry(placeholder_text="Escríbeme…", css_classes=["as-reto-entrada"])
        self.bubble_box.append(entrada)
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
        if not texto or self.chat is None:
            return

        texto_l = texto.lower()
        if any(k in texto_l for k in ("crea una tarjeta", "crear una tarjeta", "haz una tarjeta", "nueva tarjeta")):
            self.crear_tarjeta_con_ia(texto)
            return

        es_c = any(k in texto_l for k in ("platzi", "udemy", "curso", "clase", "reproductor", "video"))
        es_a = any(k in texto_l for k in ("platzi", "udemy", "siguiente", "proximo", "próximo", "ultimo", "último", "abre", "abrir", "pon", "poner", "ver", "reproduce", "reproducir", "mostrar", "muéstrame"))
        if es_c and es_a:
            plat = "platzi" if "platzi" in texto_l else ("udemy" if "udemy" in texto_l else None)
            self.abrir_reproductor_cursos(plat)
            return

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
        ia.hilo(lambda: ia.conversar(cfg, historial, texto, contexto,
                                     trozo=self.escribir_ia),
                self.fin_chat,
                lambda e: self.fin_chat(f"<i>{GLib.markup_escape_text(str(e))}</i>"))

    def fin_chat(self, respuesta):
        self.creature.hablando_hasta = 0
        if self.chat is None:
            return                       # saliste del chat mientras pensaba
        self.texto_hablable = respuesta or ""
        self.chat["historial"].append({"role": "assistant",
                                       "content": respuesta or "(sin respuesta)"})
        self.sonar("listo")
        self.render_chat()
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
        boton = gesture.get_current_button()
        if boton == 3:
            self.abrir_menu_en(self.bubble_box, x, y)
            return

    def abrir_menu_en(self, widget, x, y):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        if self.menu.get_parent() != widget:
            if self.menu.get_parent() is not None:
                self.menu.unparent()
            self.menu.set_parent(widget)
        self.menu.set_pointing_to(rect)
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
            dur = voz.hablar(texto_voz, self.voz_cfg)
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

    def build_menu(self):
        m = Gio.Menu()
        seccion = Gio.Menu()
        seccion.append("Enséñame algo", "win.teach")
        seccion.append("Tarjetas recientes", "win.historial")
        seccion.append("Ponme a prueba", "win.quiz")
        seccion.append("Pregúntame algo", "win.ask")
        seccion.append("Modo chatbot", "win.chat")
        seccion.append("Una frase de libro", "win.quote")
        seccion.append("Cómo va la semana", "win.diario")
        seccion.append("Sesión de estudio", "win.study")
        seccion.append("Abrir AppStudy", "win.open")
        seccion.append("Cómo se usa", "win.ayuda")
        m.append_section(None, seccion)

        # Submenú Cursos Online
        cursos_menu = Gio.Menu()
        cursos_menu.append("🟢 Abrir Platzi", "win.platzi_open")
        cursos_menu.append("🟣 Abrir Udemy", "win.udemy_open")
        m.append_submenu("🎬 Cursos Online", cursos_menu)

        tamano = Gio.Menu()
        tamano.append("Silencio" if self.sonido["activo"] else "Con sonido", "win.mute")

        # Submenú tamaño de tarjeta
        tarjeta_submenu = Gio.Menu()
        tarjeta_submenu.append("Tarjeta más grande (+)", "win.card_bigger")
        tarjeta_submenu.append("Tarjeta más pequeña (-)", "win.card_smaller")
        tarjeta_submenu.append("Tamaño: Normal (100%)", "win.card_size_100")
        tarjeta_submenu.append("Tamaño: Grande (125%)", "win.card_size_125")
        tarjeta_submenu.append("Tamaño: Muy grande (150%)", "win.card_size_150")
        tamano.append_submenu("Tamaño de tarjeta", tarjeta_submenu)

        # Submenú tamaño de la criatura
        mascota_submenu = Gio.Menu()
        mascota_submenu.append(f"{NOMBRE} más grande", "win.bigger")
        mascota_submenu.append(f"{NOMBRE} más pequeño", "win.smaller")
        tamano.append_submenu(f"Tamaño de {NOMBRE}", mascota_submenu)

        m.append_section(None, tamano)
        dormir = Gio.Menu()
        dormir.append(f"Duérmete {SNOOZE_MIN} min", "win.snooze")
        dormir.append("Despertar", "win.wake")
        m.append_section(None, dormir)
        m.append("Salir", "win.quit")
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
                           ("quit", lambda *_: self.get_application().quit())):
            a = Gio.SimpleAction.new(nombre, None)
            a.connect("activate", cb)
            self.add_action(a)
        return m

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


def set_autostart(enabled: bool) -> str:
    if not enabled:
        AUTOSTART.unlink(missing_ok=True)
        return f"{NOMBRE} ya no aparecerá al iniciar sesión."
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name=AppStudy · {NOMBRE}\n"
        "Comment=La mascota de estudio, siempre en el escritorio\n"
        f"Exec={launcher()} --pet\n"
        "Icon=io.github.appstudy.AppStudy\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Delay=8\n")
    return f"{NOMBRE} saldrá solo al iniciar sesión."


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
        PetWindow(a, con).present()

    app.connect("activate", activate)
    return app.run([argv[0]])
