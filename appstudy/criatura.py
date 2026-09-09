"""El motor de la mascota: todo lo que se mueve, sin decidir a qué se parece.

`Creature` lleva el reloj de fotogramas, los gestos, la pose, las partículas, la
mirada y la barra de energía. No sabe si por debajo hay un mochi crema o un
zorro naranja: el dibujo concreto lo ponen las pieles (`bit.Bit`,
`chispa.Chispa`) rellenando unos pocos ganchos y sus constantes de clase.

La separación existe porque el motor es difícil y la piel es larga: sin ella,
una segunda mascota obliga a duplicar la trigonometría de una docena de gestos.
"""
import math
import random

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

# Los gestos siguen el reloj de fotogramas de GTK; acotamos los FPS activos y de reposo.
FRAME_ACTIVO = 16   # ~60 FPS máximo en pantallas de alta tasa de refresco (144Hz/165Hz+)
FRAME_REPOSO = 50   # 20 FPS en reposo

ESCALA_MIN, ESCALA_MAX, ESCALA_PASO = 0.5, 2.5, 0.15   # «Más grande» / «Más pequeño»

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
    """Una mascota viva, sea cual sea su piel.

    Nunca se queda quieta: respira, se balancea, parpadea, sigue al ratón con la
    mirada y cada pocos segundos hace un gesto suelto (saltar, estirarse,
    ladear la cabeza, agitar la antena). Los gestos puntuales se lanzan con
    `play(nombre, segundos)` y viven en `self.anims` hasta que se les acaba el
    tiempo; `phase(nombre)` devuelve por dónde van, de 0 a 1. Aparte vuelan las
    partículas: corazones al acertar, gotas al fallar, chispas y zZz.

    Las subclases aportan la identidad visual: la paleta y las medidas de abajo,
    y los ganchos `_forma`, `_capa_fondo`, `_tras_fondo`, `_marca`,
    `_rasgos_previos` y `_accesorio`.
    """

    # -- lo que define cada piel ---------------------------------------------
    NOMBRE = "?"
    DISENO = (152, 184)               # el lienzo en el que está dibujada
    ANCHO, ALTO_PET = 168, 203        # su tamaño real en pantalla al 100 %
    CUERPO_LADO = 120                 # lienzo del cuerpo guardado en caché
    RX, RY = 39, 35                   # medias del cuerpo

    MOODS = {}                        # ánimo -> color del acento
    COLOR_BASE = "#D97757"            # el acento en reposo
    CHAT = "#5B86D6"                  # el azul frío del modo conversación
    COLOR_LENGUA = "#D97757"
    COLOR_CORAZON = "#D97757"
    TINTA = (0.16, 0.14, 0.12)        # ojos, cejas y boca
    PELAJE_CLARO, PELAJE, PELAJE_SOMBRA = "#FAF8F2", "#F0EDE4", "#DED7C7"

    CARA_ESCALA, CARA_BAJA = 1.09, 3.0    # cuánto se agrandan y bajan los rasgos
    OJO_DX, OJO_Y, OJO_R = 13.5, -5, 9.2
    CEJA_Y = -21
    BOCA_Y = 13
    CACHETE_DX, CACHETE_Y = 23, 8
    PIE_DX, PIE_R = 15, 12.3
    BRAZO_X, BRAZO_Y = 30, 6.5

    # Cuánto más fino que la pantalla se pintan las piezas guardadas. Lo ajusta
    # `set_escala`; aquí queda el valor de una mascota a tamaño normal.
    _ss = 2

    # -- ganchos que rellena la piel -----------------------------------------

    def _forma(self, cr, rx, ry):
        """La silueta del cuerpo, centrada en el origen."""
        cr.arc(0, 0, min(rx, ry), 0, math.tau)

    def _capa_fondo(self, cr, color):
        """Lo que va detrás del cuerpo: el estallido de Bit, la cola de Chispa."""

    def _tras_fondo(self, cr, color):
        """Entre el fondo y el cuerpo: las orejas de Chispa."""

    def _marca(self, cr, color):
        """La señal del pecho o de la frente que lleva el color del ánimo."""

    def _rasgos_previos(self, cr, color):
        """Bajo los ojos y sobre el cuerpo: el hocico de Chispa."""

    def _accesorio(self, cr, color):
        """Los accesorios desbloqueables, con los offsets de cada mascota."""


    # Lo que hace cuando nadie lo molesta (repetido = más probable). A esta
    # base se le suman gestos propios de cada ánimo en `_gestos_idle`.
    IDLES = ("parpadeo", "parpadeo", "parpadeo", "parpadeo2", "mirar", "mirar",
             "antena", "salto", "estirar", "ladear", "asentir", "curiosear", "guino")
    DURACION_GESTO = {
        "antena": 0.9, "salto": 0.68, "estirar": 1.3, "ladear": 1.4,
        "asentir": 0.95, "sorpresa": 0.9, "risa": 1.25, "baile": 1.9,
        "bostezo": 1.8, "suspiro": 1.35, "tiritar": 1.15,
        "guino": 1.15, "reverencia": 2.4, "curiosear": 3.2, "victoria": 1.7,
        "enojado": 2.2,
    }
    EXPRESIONES = {"sorpresa", "risa", "baile", "bostezo", "suspiro", "tiritar",
                   "guino", "reverencia", "curiosear", "victoria", "enojado"}
    GESTOS_MENU = (("guino", "😉 Guiño"), ("reverencia", "🙇 Reverencia"),
                   ("curiosear", "🔎 Curiosidad"), ("victoria", "🙌 Victoria"),
                   ("baile", "🎵 Baile"), ("enojado", "😠 Enojado"))

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
        self.enojado = False
        self.accessory = "ninguno"
        # 'f', 'm' o '': de quién es la voz con la que habla. Cambia la cara,
        # para que a quien le contesta una voz de mujer no le hable un muñeco
        # con cara de otra cosa.
        self.genero = ""
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
        self.giro_fondo = 0.0
        self.color_actual = _hex(self.MOODS["normal"])[:3]
        self.energy_mostrada = 1.0
        self.next_idle = random.uniform(1.5, 4)
        self.inercia = self.inercia_vel = 0.0
        self._pose_y = 0.0
        self._frame_time = None
        self._cache_fondo = None     # (clave, imagen) del estallido ya pintado
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
        intervalo = 0.1 if self.reduced_motion else (FRAME_REPOSO / 1000 if not self.ocupada() else FRAME_ACTIVO / 1000)
        if dt < intervalo:
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
            self._cache_fondo = self._cache_cuerpo = None
        self.set_content_width(round(self.ANCHO * self.escala))
        self.set_content_height(round(self.ALTO_PET * self.escala))
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
        self.play("victoria", self.DURACION_GESTO["victoria"])
        self.play("brillo", 1.5)
        self.emitir("corazon", 4)
        self.emitir("chispa", 9)

    def desanimar(self):
        self.play("negar", 0.8)
        self.play("suspiro", 1.35)
        self.emitir("gota", 2)

    def pensar(self):
        self.play("curiosear", self.DURACION_GESTO["curiosear"])
        self.emitir("nota", 2)

    def actuar(self, nombre):
        """Gesto pedido por el usuario; no mueve ni redimensiona la ventana."""
        if nombre not in dict(self.GESTOS_MENU):
            return
        if nombre == "victoria":
            self.celebrar()
        else:
            self.play(nombre, self.DURACION_GESTO[nombre])
        self.next_idle = self.t + self.DURACION_GESTO[nombre] + 2

    def _gestos_idle(self):
        """Gestos disponibles ahora: Bit se comporta según cómo se siente."""
        gestos = list(self.IDLES)
        if getattr(self, "enojado", False):
            gestos = ["parpadeo", "mirar", "enojado", "suspiro"]
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
        ultimo = getattr(self, "_ultimo_idle", None)
        return [g for g in gestos if g != ultimo] or list(self.IDLES)

    def emitir(self, kind, n):
        if self.reduced_motion:
            return
        arriba = kind in ("corazon", "chispa", "nota")
        # Interacciones rápidas no deben acumular una nube de partículas.
        for _ in range(min(n, max(0, 48 - len(self.particulas)))):
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
        if (self.mood == "dormido" or self.teaching or self.charlando
                or self.t < self.hablando_hasta
                or self.t < getattr(self, "_proximo_saludo_cursor", 0)):
            return
        self._proximo_saludo_cursor = self.t + 8
        self.play("antena", 0.7)
        # A veces Bit se sorprende al verte llegar; no lo repite si ya está
        # expresando otra cosa importante.
        expresivos = self.EXPRESIONES
        if not expresivos.intersection(self.anims) and random.random() < 0.35:
            self.play("guino", self.DURACION_GESTO["guino"])

    def on_leave(self, _c):
        self.hover = False
        self.puntero = None

    # ------------------------------------------------------------------ tiempo

    def tick(self, dt):
        dt = max(0.0, min(dt, 0.1))      # reloj monotónico, acotado tras una pausa
        self.t += dt
        vel_fondo = (0.0 if self.reduced_motion else
                        0.85 if self.teaching else 0.22 * (1 - 0.75 * self.abandono))
        self.giro_fondo = (self.giro_fondo + vel_fondo * dt) % math.tau

        ahora = self.t
        self.anims = {k: v for k, v in self.anims.items() if ahora - v[0] < v[1]}
        objetivo_color = _hex(self.CHAT if self.charlando else
                              self.MOODS.get(self.mood, self.MOODS["normal"]))[:3]
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
        # Escuchar y leer tienen prioridad sobre los gestos espontáneos.
        # Durante una reacción explícita tampoco se le cambia la expresión.
        tranquilo = (self.teaching or self.charlando or ahora < self.hablando_hasta
                     or bool(self.EXPRESIONES.intersection(self.anims)) or self.reduced_motion)
        gesto = random.choice(("parpadeo", "mirar") if tranquilo else self._gestos_idle())
        self._ultimo_idle = gesto
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
        objetivo_color = _hex(self.CHAT if self.charlando else
                              self.MOODS.get(self.mood, self.MOODS["normal"]))[:3]
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

        # Envolventes con velocidad cero en ambos extremos: regresan a su
        # postura sin tirones y permanecen dentro del lienzo de la mascota.
        p = self.phase_motion("guino")
        if p is not None:
            k = math.sin(math.pi * p) ** 2
            rot -= 0.09 * k
            dy -= 1.5 * k
        p = self.phase_motion("reverencia")
        if p is not None:
            k = self.presencia_gesto(p)
            dy += 14 * k
            sx += 0.10 * k
            sy -= 0.28 * k
            rot += 0.035 * k
        p = self.phase_motion("curiosear")
        if p is not None:
            k = math.sin(math.pi * p) ** 2
            rot += 0.035 * math.sin(math.tau * p) * k
            dy -= 1.5 * k
        p = self.phase_motion("enojado")
        if p is not None:
            k = math.sin(math.pi * p) ** 2
            dy += 2 * abs(math.sin(p * math.pi * 6)) * k
            rot += 0.025 * math.sin(p * math.pi * 6) * k
        p = self.phase_motion("victoria")
        if p is not None:
            k = math.sin(math.pi * p) ** 2
            dy -= 4 * k
            sy += 0.04 * k

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
        k = min(w / self.DISENO[0], h / self.DISENO[1])
        cr.translate((w - self.DISENO[0] * k) / 2, (h - self.DISENO[1] * k) / 2)
        cr.scale(k, k)
        w, h = self.DISENO
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
        self._capa_fondo(cr, color)       # lo que va detrás de todo
        self._tras_fondo(cr, color)
        self._pies(cr)
        self._brazos(cr, color)
        self._cuerpo(cr, color)
        cr.save()
        # La cara acompaña la mirada, con menos recorrido que las pupilas.
        cr.translate(self.mirada[0] * 1.2, self.mirada[1] * 0.8)
        cr.save()
        # Los rasgos, un punto mayores y algo más abajo: centrados en el mochi
        # se leen mejor de lejos y no dejan medio cuerpo vacío bajo la boca.
        cr.translate(0, self.CARA_BAJA)
        cr.scale(self.CARA_ESCALA, self.CARA_ESCALA)
        self._cara(cr, color, dormido)
        cr.restore()
        self._accesorio(cr, color)
        cr.restore()
        self._utileria_gestos(cr)
        cr.restore()

        self._particulas(cr, cx, base + dy)
        self._barra(cr, cx, h - 14, color)
        cr.restore()

    # -- piezas ---------------------------------------------------------------

    def presencia_gesto(self, p):
        """Entrada y salida suaves con una pausa central para leer el gesto."""
        return suave(min(1.0, p / .25)) * suave(min(1.0, (1 - p) / .25))

    def enfadada(self):
        if self.mood == "dormido":
            return False
        if self.phase("enojado") is not None:
            return True
        return (getattr(self, "enojado", False)
                and not any(self.phase(n) is not None for n in self.EXPRESIONES))

    def _utileria_gestos(self, cr):
        """Manos y objetos delante del cuerpo, para que no queden ocultos."""
        p = self.phase("curiosear")
        if p is not None and self.mood != "dormido":
            k = 1 if self.reduced_motion else self.presencia_gesto(p)
            cr.save()
            cr.translate(18 + 18 * (1 - k), -2 + 16 * (1 - k))
            cr.push_group()
            # Mango de madera y borde metálico de la lupa.
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.move_to(13, 13)
            cr.line_to(29, 31)
            cr.set_source_rgb(.35, .22, .14)
            cr.set_line_width(9)
            cr.stroke()
            cr.arc(0, 0, 20, 0, math.tau)
            cr.set_source_rgba(.79, .93, .98, .95)
            cr.fill_preserve()
            cr.set_source_rgb(.19, .32, .39)
            cr.set_line_width(4)
            cr.stroke()
            # Ojo ampliado: hace que la lupa tenga una función visual clara.
            cr.save()
            cr.scale(.85, 1.1)
            cr.arc(0, 0, 12, 0, math.tau)
            cr.set_source_rgb(1, .99, .96)
            cr.fill()
            cr.restore()
            cr.arc(self.mirada[0] * 2, self.mirada[1] * 2, 7, 0, math.tau)
            cr.set_source_rgb(.28, .18, .12)
            cr.fill()
            cr.arc(-2, -3, 2.5, 0, math.tau)
            cr.set_source_rgb(1, 1, 1)
            cr.fill()
            cr.arc(0, 0, 15.5, math.pi * 1.05, math.pi * 1.40)
            cr.set_source_rgba(1, 1, 1, .8)
            cr.set_line_width(2.5)
            cr.stroke()
            cr.arc(24, 25, 6.5, 0, math.tau)
            cr.set_source_rgba(*_hex(self.PELAJE))
            cr.fill_preserve()
            cr.set_source_rgba(.34, .24, .18, .6)
            cr.set_line_width(1.5)
            cr.stroke()
            cr.pop_group_to_source()
            cr.paint_with_alpha(k)
            cr.restore()

        p = self.phase("reverencia")
        if p is not None:
            k = 1 if self.reduced_motion else self.presencia_gesto(p)
            for lado in (-1, 1):
                cr.save()
                cr.translate(lado * (27 - 23 * k), 21)
                cr.scale(.72, 1)
                cr.arc(0, 0, 8, 0, math.tau)
                cr.set_source_rgba(*_hex(self.PELAJE_CLARO))
                cr.fill_preserve()
                cr.set_source_rgba(.34, .24, .18, .55)
                cr.set_line_width(1.5)
                cr.stroke()
                cr.restore()

        if self.enfadada():
            # Brazos cruzados y marca de enfado: visible incluso sin movimiento.
            for lado in (-1, 1):
                cr.move_to(lado * 29, 15)
                cr.line_to(-lado * 13, 24)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.set_source_rgba(.34, .24, .18, .75)
                cr.set_line_width(12)
                cr.stroke_preserve()
                cr.set_source_rgba(*_hex(self.PELAJE))
                cr.set_line_width(9)
                cr.stroke()
            cr.set_source_rgb(.77, .19, .14)
            cr.set_line_width(2.5)
            for lado in (-1, 1):
                for vertical in (-1, 1):
                    cr.move_to(43 + lado * 2, -36 + vertical * 8)
                    cr.line_to(43 + lado * 2, -36 + vertical * 2)
                    cr.line_to(43 + lado * 8, -36 + vertical * 2)
                    cr.stroke()

    def _halo(self, cr, dibujar, ancho=1.0):
        """Sombra suave alrededor de una pieza.

        Cairo no tiene desenfoque, así que se imita con trazos concéntricos cada
        vez más tenues. Sin esto la mascota se perdería sobre un fondo claro.
        """
        for grosor, alpha in ((6.0, 0.022), (2.8, 0.038)):
            dibujar()
            cr.set_source_rgba(0.10, 0.07, 0.05, alpha)
            cr.set_line_width(grosor * ancho)
            cr.stroke()

    def _perfil(self, cr, alpha=0.30, grosor=1.9):
        """El contorno cálido que separa a Bit de cualquier escritorio.

        Marrón cálido y fino: el gris azulado y el trazo grueso son lo que le
        daban aire de pegatina recortada en vez de dibujo.
        """
        cr.set_source_rgba(0.34, 0.24, 0.18, alpha * 0.88)
        cr.set_line_width(grosor * 0.82)
        cr.stroke()

    def _cuerpo(self, cr, color):
        """El mochi, con su sombra, sus luces y su insignia.

        El dibujo no depende del tiempo —la respiración y el balanceo se los
        aplica `draw` por fuera, al deformar el lienzo—, así que se guarda ya
        pintado y solo se vuelve a trazar cuando cambia el color del ánimo.
        """
        cr.save()
        cr.scale(1 / self._ss, 1 / self._ss)
        lado = self.CUERPO_LADO * self._ss
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

        lado = self.CUERPO_LADO * self._ss
        superficie = self._cache_cuerpo[1] if self._cache_cuerpo else \
            cairo.ImageSurface(cairo.FORMAT_ARGB32, lado, lado)
        ctx = cairo.Context(superficie)
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.restore()
        ctx.scale(self._ss, self._ss)
        ctx.translate(self.CUERPO_LADO / 2, self.CUERPO_LADO / 2)
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
        g.add_color_stop_rgba(0, *_hex(self.PELAJE_CLARO))
        g.add_color_stop_rgba(0.55, *_hex(self.PELAJE))
        g.add_color_stop_rgba(1, *_hex(self.PELAJE_SOMBRA))
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

        self._marca(cr, color)

    def color_hex(self) -> str:
        """El color del ánimo en curso, en hexadecimal."""
        return self.MOODS.get("normal" if self.charlando else self.mood, self.COLOR_BASE) \
            if not self.charlando else self.CHAT

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
                cr.translate(lado * (self.PIE_DX + levanta * 0.35),
                             self.RY - 1 + fase * 0.4 - levanta)
                cr.rotate(lado * (0.12 + levanta * 0.025))
                cr.scale(1.0, 0.58)
                cr.arc(0, 0, self.PIE_R, 0, math.tau)
                cr.restore()
            self._halo(cr, pie, 0.7)
            # Sombra de contacto: sin ella los pies flotan sobre el escritorio
            cr.save()
            cr.translate(lado * (self.PIE_DX + levanta * 0.35), self.RY + 4.2)
            cr.scale(1.0, 0.3)
            sombra = cairo.RadialGradient(0, 0, 1, 0, 0, 11)
            opacidad = 0.26 * max(0.0, 1 - levanta / 9.0)   # al levantar el pie, se va
            sombra.add_color_stop_rgba(0, 0.16, 0.10, 0.07, opacidad)
            sombra.add_color_stop_rgba(1, 0.16, 0.10, 0.07, 0.0)
            cr.arc(0, 0, 11, 0, math.tau)
            cr.set_source(sombra)
            cr.fill()
            cr.restore()

            pie()
            # Volumen en vez de un relleno plano: claro arriba, sombra abajo,
            # que es lo que los sacaba grises y apagados al lado del cuerpo.
            g = cairo.RadialGradient(lado * (self.PIE_DX - 3), self.RY - 6, 1,
                                     lado * self.PIE_DX, self.RY + 1, 15)
            g.add_color_stop_rgba(0, *_hex(self.PELAJE))
            g.add_color_stop_rgba(1, *_hex(self.PELAJE_SOMBRA))
            cr.set_source(g)
            cr.fill_preserve()
            cr.save()
            cr.clip_preserve()
            # El mismo rebote de color que tiene el cuerpo en el borde: sin él
            # los pies se leen grises al lado de un cuerpo cálido.
            rebote = cairo.RadialGradient(lado * self.PIE_DX, self.RY - 4, 2,
                                          lado * self.PIE_DX, self.RY + 3, 13)
            rebote.add_color_stop_rgba(0, *_hex(self.color_hex(), 0.0))
            rebote.add_color_stop_rgba(1, *_hex(self.color_hex(), 0.30))
            cr.set_source(rebote)
            cr.paint()
            cr.restore()
            self._perfil(cr, 0.46, 2.2)

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
        victoria = self.phase_motion("victoria")
        reverencia = self.phase_motion("reverencia")
        curiosear = self.phase_motion("curiosear")
        for lado in (1, -1):
            ang = 0.62 + vaiven - 0.10 * self.hover_suave
            largo = 15 + 1.2 * self.hover_suave
            if victoria is not None:
                k = math.sin(math.pi * victoria) ** 2
                ang -= 1.55 * k
                largo += 18 * k
            if reverencia is not None:
                ang += 0.42 * math.sin(math.pi * reverencia) ** 2
            if curiosear is not None and lado == 1:
                ang += 0.15 * self.presencia_gesto(curiosear)
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
            cr.translate(lado * self.BRAZO_X, self.BRAZO_Y)
            cr.scale(lado, 1)               # el izquierdo, en espejo
            cr.rotate(ang)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for grosor, rgba in ((13.5, (0.10, 0.07, 0.05, 0.06)),
                                 (11.9, (0.34, 0.24, 0.18, 0.40)),
                                 (9.4, _hex(self.PELAJE))):
                cr.move_to(0, 0)
                cr.line_to(largo, 0)
                cr.set_source_rgba(*rgba)
                cr.set_line_width(grosor)
                cr.stroke()
            cr.arc(largo + 1.5, 0, 7.4, 0, math.tau)     # la manopla
            g = cairo.RadialGradient(largo - 0.8, -2.4, 0.5, largo + 1.5, 0.5, 8.2)
            g.add_color_stop_rgba(0, *_hex(self.PELAJE_CLARO))
            g.add_color_stop_rgba(1, *_hex(self.PELAJE_SOMBRA))
            cr.set_source(g)
            cr.fill_preserve()
            cr.save()
            cr.clip_preserve()
            rebote = cairo.RadialGradient(largo + 0.5, -1.5, 1, largo + 1.5, 1.5, 8.5)
            rebote.add_color_stop_rgba(0, *_hex(color, 0.0))
            rebote.add_color_stop_rgba(1, *_hex(color, 0.28))
            cr.set_source(rebote)
            cr.paint()
            cr.restore()
            self._perfil(cr, 0.44, 2.2)
            cr.restore()

    def _cara(self, cr, color, dormido):
        self._rasgos_previos(cr, color)
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
        reverencia = self.phase("reverencia")
        if reverencia is not None:
            apertura *= max(.04, 1 - self.presencia_gesto(reverencia))
        if self.enfadada():
            apertura *= .68
        cerrado = apertura < 0.16
        apertura_base = apertura
        guino = self.phase("guino")

        mx, my = self.mirada[0] * 3.0, self.mirada[1] * 2.2
        pupila_sorpresa = pulso(sorpresa) if sorpresa is not None else 0.0
        for dx in (-self.OJO_DX, self.OJO_DX):
            apertura = apertura_base
            if guino is not None and dx > 0 and not dormido:
                apertura *= max(0.04, 1 - 1.2 * math.sin(math.pi * guino) ** 2)
            ex, ey = dx, self.OJO_Y
            if apertura < 0.16:         # ojo cerrado: un arco tranquilo
                curva = -5.8 if self.mood == "feliz" or risa is not None else 4.8
                cr.move_to(ex - 7.5, ey)
                cr.curve_to(ex - 2.4, ey + curva, ex + 2.4, ey + curva, ex + 7.5, ey)
                cr.set_source_rgba(*self.TINTA, 0.92)
                cr.set_line_width(2.8)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.stroke()
                if self.genero == "f":
                    self._pestanas(cr, ex, ey, dx, 0.55)
                continue

            def ojo():
                cr.save()
                cr.translate(ex, ey)
                cr.scale(1.0, 1.18 * apertura)
                cr.arc(0, 0, self.OJO_R, 0, math.tau)
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
            cr.set_source_rgba(*self.TINTA)
            cr.fill()
            # dos brillos: el grande arriba a la izquierda, el chico abajo
            cr.arc(px - 2.3, py - 2.6, 2.5, 0, math.tau)
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.fill()
            cr.arc(px + 2.2, py + 2.4, 1.15, 0, math.tau)
            cr.set_source_rgba(1, 1, 1, 0.6)
            cr.fill()
            cr.restore()

            if self.genero == "f":
                self._pestanas(cr, ex, ey, dx, apertura)

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
        for dx in (-self.OJO_DX, self.OJO_DX):
            cr.move_to(dx - 7, self.OJO_Y + 11.5)
            cr.curve_to(dx - 2.6, self.OJO_Y + 14.4, dx + 2.6, self.OJO_Y + 14.4,
                      dx + 7, self.OJO_Y + 11.5)
            cr.stroke()

    def _cachetes(self, cr, color):
        fuerte = (self.mood == "feliz" or self.phase("brillo") is not None or
                  self.phase("risa") is not None or self.phase("baile") is not None
                  or self.phase("guino") is not None or self.phase("victoria") is not None)
        for dx in (-self.CACHETE_DX, self.CACHETE_DX):
            g = cairo.RadialGradient(dx, self.CACHETE_Y, 1, dx, self.CACHETE_Y, 8)
            intensidad = 0.40 if fuerte else 0.22
            if self.genero == "f":
                intensidad += 0.08
            g.add_color_stop_rgba(0, *_hex(color, intensidad))
            g.add_color_stop_rgba(1, *_hex(color, 0.0))
            cr.save()
            cr.translate(dx, self.CACHETE_Y)
            cr.scale(1.3, 1.0)
            cr.arc(0, 0, 8, 0, math.tau)
            cr.restore()
            cr.set_source(g)
            cr.fill()

    def _pestanas(self, cr, ex, ey, lado, apertura):
        """Tres pestañas en la esquina de fuera de cada ojo."""
        fuera = 1 if lado > 0 else -1
        rx, ry = self.OJO_R, self.OJO_R * 1.18 * max(0.35, apertura)
        cr.save()
        cr.set_source_rgba(*self.TINTA, 0.85)
        cr.set_line_width(1.6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        # Nacen del borde del ojo, en el cuarto de arriba y hacia fuera, y
        # apuntan en la misma dirección en la que sale el borde.
        for grados, largo in ((22, 4.6), (46, 5.4), (70, 5.0)):
            ang = math.radians(grados)
            base_x = ex + fuera * rx * math.cos(ang)
            base_y = ey - ry * math.sin(ang)
            cr.move_to(base_x, base_y)
            cr.line_to(base_x + fuera * largo * math.cos(ang),
                       base_y - largo * math.sin(ang))
            cr.stroke()
        cr.restore()

    def _cejas(self, cr, cerrado):
        if self.mood == "dormido":
            return
        # Positivo = extremo interior hacia arriba, que es la cara de pena
        inclinacion = {"triste": 0.46, "hambre": 0.30, "aburrido": 0.14,
                       "feliz": -0.20}.get(self.mood, 0.0)
        inclinacion -= 0.08 * self.hover_suave
        alto = self.CEJA_Y - (2 if self.mood == "feliz" else 0) - 1.8 * self.hover_suave
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
        if self.enfadada():
            inclinacion = -.55
            alto = -17
        marcada = self.mood in ("triste", "hambre", "aburrido", "feliz")
        cr.set_source_rgba(*self.TINTA, 0.72 if marcada else 0.50)
        grosor = 2.7 if marcada else 2.4
        if self.genero == "f":
            grosor -= 0.55        # ceja más fina, un pelo más arqueada
            alto -= 1.2
        cr.set_line_width(grosor)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for lado in (-1, 1):
            cr.save()
            cr.translate(lado * self.OJO_DX, alto)
            cr.rotate(inclinacion * lado)
            arco = -3.0 if self.genero == "f" else -2.2
            cr.move_to(-6, 0)
            cr.curve_to(-2, arco, 2, arco, 6, 0)
            cr.stroke()
            cr.restore()

    def _boca(self, cr, color):
        my = self.BOCA_Y
        cr.set_source_rgba(*self.TINTA, 0.9)
        cr.set_line_width(2.7)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if self.enfadada() and self.t >= self.hablando_hasta:
            cr.move_to(-7, my + 1)
            cr.curve_to(-3, my - 4, 3, my - 4, 7, my + 1)
            cr.stroke()
            return
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
            cr.set_source_rgba(*_hex(self.COLOR_LENGUA, 0.82))
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
        if (self.mood == "feliz" or risa is not None or baile is not None
                or self.phase("victoria") is not None or self.phase("guino") is not None):
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
            cr.set_source_rgba(*self.TINTA, 0.92)
            cr.fill_preserve()
            cr.save()
            cr.clip()
            cr.arc(0, my + 9, 5.4, 0, math.tau)
            cr.set_source_rgba(*_hex(self.COLOR_LENGUA, 0.95))
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
                cr.set_source_rgba(*_hex(self.PELAJE, alpha * 0.85))
                cr.show_text("z")
            cr.restore()

    def _corazon(self, cr, alpha):
        cr.move_to(0, 4.5)
        cr.curve_to(-6.5, -1, -4.5, -7, 0, -3.2)
        cr.curve_to(4.5, -7, 6.5, -1, 0, 4.5)
        cr.close_path()
        cr.set_source_rgba(*_hex(self.COLOR_CORAZON, alpha))
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
