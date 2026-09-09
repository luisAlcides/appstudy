"""Chispa: el zorro naranja de cola turquesa, con seis poses ilustradas.

Comparte con Bit el reloj, las poses corporales, los gestos y las partículas.
El atlas local conserva el aspecto de la referencia; el dibujo vectorial sirve
como respaldo si falta el recurso.

En las ilustraciones el pelaje naranja y los detalles turquesa son constantes.
El ánimo se expresa mediante la pose, las partículas y la barra de energía.
"""
import math
from functools import lru_cache
from pathlib import Path

import cairo

from .criatura import Creature, _claro, _hex, _oscuro
from . import animacion_chispa

NARANJA_CLARO = "#FBA85E"
NARANJA = "#F0873A"
NARANJA_SOMBRA = "#D3661F"

# El pecho, el hocico y el interior de las orejas.
CREMA = "#FBF3E6"
CREMA_SOMBRA = "#EEDCC4"

# Patas, brazos y manoplas: el calcetín oscuro del zorro.
PARDO_CLARO = "#5C4030"
PARDO = "#483224"
PARDO_SOMBRA = "#332218"

TURQUESA = "#3FD0C9"            # el acento de la casa

MOODS = {
    "feliz":    "#5FD79A",
    "normal":   TURQUESA,
    "aburrido": "#9C8AA8",
    "hambre":   "#E9B44C",
    "triste":   "#C06055",
    "dormido":  "#9AA5A8",
}

CHAT = "#5B86D6"

# El lienzo es más ancho que el de Bit: la cola es media mascota y necesita
# sitio a la izquierda del cuerpo para leerse como una cola y no como un borrón.
DISENO = (176, 190)
ANCHO = 228
ALTO_PET = 246

# La cola se guarda pintada y luego solo se gira, como el estallido de Bit: es
# la pieza cara del fotograma y lo único que cambia siempre es su vaivén. El
# lienzo no es cuadrado ni está centrado en el pivote: la cola sale toda hacia
# un lado, y un cuadrado que la abarcase gastaría el triple de memoria.
COLA_ANCHO, COLA_ALTO = 124, 100
COLA_PIVOTE = (112, 84)          # dónde cae el nacimiento de la cola en ese lienzo

CUERPO_LADO = 130


ATLAS = Path(__file__).parent / "data" / "chispa-poses.png"


@lru_cache(maxsize=1)
def cargar_poses():
    """Carga el atlas una vez; las seis celdas comparten escala y suelo.

    Cairo conserva el alfa del PNG. Los rectángulos de cada pose impiden que
    el filtrado tome píxeles de la celda vecina al escalar la mascota.
    """
    try:
        atlas = cairo.ImageSurface.create_from_png(str(ATLAS))
    except (OSError, cairo.Error):
        return None
    ancho, alto = atlas.get_width(), atlas.get_height()
    if atlas.get_format() != cairo.FORMAT_ARGB32:
        # El recurso usa magenta de recorte. Se compone como alfa una sola
        # vez al cargar, nunca en el reloj de animación; admite también PNG
        # con transparencia nativa para futuras versiones del atlas.
        pixeles = memoryview(atlas.get_data()).cast("I")
        esquina = pixeles[0]
        r, g, b = (esquina >> 16) & 255, (esquina >> 8) & 255, esquina & 255
        if min(r, b) - g < 180:
            return None
        transparente = cairo.ImageSurface(cairo.FORMAT_ARGB32, ancho, alto)
        salida = memoryview(transparente.get_data()).cast("I")
        for i, pixel in enumerate(pixeles):
            r, g, b = (pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255
            clave = min(255, round(max(0, min(r, b) - g - 20) * 255 / 160))
            # Cairo espera canales premultiplicados; retirar el magenta
            # también de los bordes evita un halo rosa sobre fondos oscuros.
            a = 255 - clave
            salida[i] = (a << 24 | min(a, max(0, r - clave)) << 16 |
                         min(a, g) << 8 | min(a, max(0, b - clave)))
        transparente.mark_dirty()
        atlas = transparente
    celdas = []
    for fila in range(2):
        for columna in range(3):
            x, y = columna * ancho // 3, fila * alto // 2
            w = (columna + 1) * ancho // 3 - x
            h = (fila + 1) * alto // 2 - y
            celda = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            ctx = cairo.Context(celda)
            ctx.set_source_surface(atlas, -x, -y)
            ctx.paint()
            celdas.append(celda)
    return tuple(celdas)


@lru_cache(maxsize=6)
def suelo_pose(superficie):
    """Alinea las patas y la cola dormida sin estirar las poses sentadas."""
    pixeles = memoryview(superficie.get_data()).cast("I")
    ancho = superficie.get_stride() // 4
    for fila in range(superficie.get_height() - 1, -1, -1):
        if any((p >> 24) > 100 for p in pixeles[fila * ancho:(fila + 1) * ancho]):
            return fila + 1
    return superficie.get_height()


class Chispa(Creature):
    """El zorro: cola, orejas, hocico y un rombo en la frente."""

    CLAVE = "chispa"
    NOMBRE = "Chispa"
    DISENO = DISENO
    ANCHO, ALTO_PET = ANCHO, ALTO_PET
    CUERPO_LADO = CUERPO_LADO
    RX, RY = 34, 35
    CUERPO_DX = 15

    MOODS = MOODS
    COLOR_BASE = TURQUESA
    CHAT = CHAT
    COLOR_LENGUA = "#E27D6D"
    COLOR_CORAZON = "#E8705F"
    TINTA = (0.16, 0.12, 0.10)
    PELAJE_CLARO, PELAJE, PELAJE_SOMBRA = NARANJA_CLARO, NARANJA, NARANJA_SOMBRA
    PATA_CLARO, PATA, PATA_SOMBRA = PARDO_CLARO, PARDO, PARDO_SOMBRA

    # Ojos grandes y algo más juntos que los de Bit, y la boca bajo el hocico.
    CARA_ESCALA, CARA_BAJA = 1.06, 1.0
    OJO_DX, OJO_Y, OJO_R = 13.0, -9, 9.6
    CEJA_Y = -25
    BOCA_Y = 16
    CACHETE_DX, CACHETE_Y = 23, 6
    PIE_DX, PIE_R = 15, 11.6
    BRAZO_X, BRAZO_Y = 29, 14

    # De dónde nace la cola, en coordenadas del cuerpo.
    COLA_X, COLA_Y = 20, 20

    def _indice_pose(self):
        """Las acciones explícitas tienen prioridad sobre el ánimo de reposo."""
        if self.mood == "dormido":
            return 5
        if any(self.phase(g) is not None for g in ("victoria", "risa", "baile", "salto")):
            return 3
        if self.phase("saludo") is not None:
            return 1
        if any(self.phase(g) is not None for g in ("curiosear", "ladear", "suspiro", "enojado")):
            return 4
        if self.teaching or self.charlando or self.t < self.hablando_hasta:
            return 2
        if self.mood in ("aburrido", "hambre", "triste") or self.enfadada():
            return 4
        return 0

    # --- capas ---------------------------------------------------------------

    PARPADEO_CADA = 4.2         # segundos entre parpadeos, de media
    PARPADEO_DURA = 0.13        # lo que tarda en bajar y subir el párpado

    def _rig(self):
        """El muñeco por capas, si está. `None` significa dibujar como siempre.

        Se pide una sola vez. Si no está, se lanza la extracción en segundo
        plano y esta sesión sigue con el dibujo plano: generar las capas tarda
        segundos y nadie va a esperar mirando una mascota en blanco.
        """
        if not hasattr(self, "_rig_cargado"):
            from . import rig_chispa
            self._rig_cargado = rig_chispa.cargar()
            if self._rig_cargado is None:
                self._generar_capas()
        return self._rig_cargado

    def _generar_capas(self):
        """Una sola vez por sesión, y callada: si falla, se dibuja como hoy."""
        if getattr(Chispa, "_generando", False):
            return
        Chispa._generando = True

        def trabajo():
            from . import capas_chispa
            return capas_chispa.extraer()

        def listo(_manifiesto):
            from . import rig_chispa
            self._rig_cargado = rig_chispa.cargar()

        try:
            from . import util
            util.hilo(trabajo, listo, lambda _e: None, largo=True)
        except Exception:
            pass                 # sin GTK (pruebas, herramientas): ya está

    def _cierre_parpadeo(self) -> float:
        """Cuánto tiene bajado el párpado ahora mismo, de 0 a 1.

        Los parpadeos son periódicos pero no cuadriculados: la fase depende de
        la ranura, así que no caen siempre en el mismo punto del balanceo.
        """
        if self.reduced_motion:
            return 0.0
        ranura, resto = divmod(self.t, self.PARPADEO_CADA)
        arranque = (hash(int(ranura)) % 1000) / 1000 * (self.PARPADEO_CADA
                                                       - self.PARPADEO_DURA)
        avance = (resto - arranque) / self.PARPADEO_DURA
        if 0 <= avance <= 1:
            return math.sin(math.pi * avance)
        return 0.0

    def _personaje(self, cr, color, dormido):
        poses = cargar_poses()
        if poses is None:
            Creature._personaje(self, cr, color, dormido)
            return
        indice = self._indice_pose()
        superficie = poses[indice]
        # Todas las celdas mantienen el mismo tamaño: sentarse o dormir no
        # agranda a Chispa. El lienzo deja margen para los saltos y el balanceo.
        k = min(158 / superficie.get_width(), 142 / superficie.get_height())
        x = -self.CUERPO_DX - superficie.get_width() * k / 2
        y = 40 - suelo_pose(superficie) * k
        cr.save()
        cr.translate(x, y)
        cr.scale(k, k)
        intensidad = 0.0 if self.reduced_motion else (1 - .65 * self.abandono)
        gestos = animacion_chispa.movimientos(
            indice, self.t, intensidad, self.phase("saludo"))
        pintado = self._pintar_con_capas(cr, indice, intensidad)
        if not pintado:
            animacion_chispa.pintar(cr, superficie, gestos)
        cr.restore()

    def _pintar_con_capas(self, cr, indice, intensidad) -> bool:
        """Dibuja por capas cuando aportan algo. Devuelve si lo ha hecho.

        Con las manos separadas se usa siempre: girarlas desde donde nacen se
        ve mucho más que la deformación de la malla. Sin ellas solo se recurre
        a las capas durante el parpadeo, y el resto del tiempo sigue la malla,
        que es la que mueve las extremidades en esas poses.
        """
        rig = self._rig()
        if rig is None:
            return False
        cierre = self._cierre_parpadeo() if rig.parpadea(indice) else 0.0
        apertura = self._apertura_boca() if rig.habla(indice) else 0.0
        inclinacion = self._inclinacion_cabeza() if rig.inclina(indice) else 0.0
        if rig.mueve_miembros(indice):
            balanceo = 0.0 if self.reduced_motion else math.sin(self.t * 1.9)
            return rig.dibujar(cr, indice, cierre, balanceo * intensidad,
                               apertura, inclinacion)
        if cierre > 0 or apertura > 0 or inclinacion:
            return rig.dibujar(cr, indice, cierre, 0.0, apertura, inclinacion)
        return False

    def _inclinacion_cabeza(self) -> float:
        """Cuánto ladea la cabeza, de -1 a 1.

        Muy despacio y muy poco: una cabeza que se mueve al mismo compás que el
        cuerpo parece un muelle. Cuando toca el gesto de ladear, se marca.
        """
        if self.reduced_motion:
            return 0.0
        lento = math.sin(self.t * 0.43) * 0.35 + math.sin(self.t * 0.19) * 0.15
        gesto = self.phase_motion("ladear")
        if gesto is not None:
            lento += math.sin(math.pi * gesto) * 0.75
        return max(-1.0, min(1.0, lento))

    def _apertura_boca(self) -> float:
        """Cuánto abre la boca ahora. Solo mientras habla."""
        if self.reduced_motion or self.t >= self.hablando_hasta:
            return 0.0
        # Dos frecuencias: una boca que sube y baja a compás parece un juguete
        onda = math.sin(self.t * 13) * 0.6 + math.sin(self.t * 7.3) * 0.4
        return max(0.0, onda)
        # Anclajes de la cara en las seis celdas del atlas de referencia.
        # Se expresan como fracciones para admitir un PNG de mayor resolución.
        caras = ((.625, .412), (.543, .422), (.559, .516),
                 (.557, .324), (.539, .385), (.594, .553))
        fx, fy = caras[indice]
        cr.save()
        cr.translate(x + fx * superficie.get_width() * k,
                     y + fy * superficie.get_height() * k + 9)
        if indice == 5:
            cr.rotate(.65)
        elif indice == 4:
            cr.rotate(-.35)
        if self.accessory == "panuelo":
            cr.translate(0, -14)
        self._accesorio(cr, color)
        cr.restore()

    def _utileria_gestos(self, cr):
        # Las poses ya incluyen manos y portátil; no superponer las manos
        # del dibujo vectorial sobre la ilustración.
        if cargar_poses() is None:
            Creature._utileria_gestos(self, cr)

    # -- silueta --------------------------------------------------------------

    def _forma(self, cr, rx, ry):
        """Pera peluda: mejillas anchas arriba y el pecho recogido abajo."""
        cr.move_to(0, -ry)
        cr.curve_to(rx * 0.72, -ry, rx * 1.02, -ry * 0.58, rx, -ry * 0.06)
        cr.curve_to(rx * 0.98, ry * 0.46, rx * 0.60, ry, 0, ry)
        cr.curve_to(-rx * 0.60, ry, -rx * 0.98, ry * 0.46, -rx, -ry * 0.06)
        cr.curve_to(-rx * 1.02, -ry * 0.58, -rx * 0.72, -ry, 0, -ry)
        cr.close_path()

    def _marca(self, cr, color):
        """El rombo de la frente: lo único del cuerpo que lleva el ánimo.

        No hay pechera: el hocico ya ocupa todo el crema que cabe en una cara
        tan grande, y una segunda mancha clara debajo solo la ensuciaba.
        """
        # El rombo va en la frente, por encima de las cejas, y es lo único del
        # cuerpo que cambia de color: hace de piloto del ánimo.
        cr.move_to(0, -34)
        cr.line_to(5.4, -27)
        cr.line_to(0, -20)
        cr.line_to(-5.4, -27)
        cr.close_path()
        cr.set_source_rgba(*_claro(color, 0.18))
        cr.fill_preserve()
        cr.set_source_rgba(*_oscuro(color, 0.72, 0.55))
        cr.set_line_width(1.2)
        cr.stroke()

    # -- orejas ---------------------------------------------------------------

    def _tras_fondo(self, cr, color):
        """Dos orejas grandes, de interior crema y punta oscura.

        Van entre la cola y el cuerpo: la base queda tapada por la cabeza, que
        es lo que las hace parecer nacer de ella. Se agitan con el gesto
        «antena» —el mismo que a Bit le daba un tirón al asterisco— y se abren
        un poco cuando te acercas, que es cómo un zorro dice que te ha oído.
        """
        tiron = self.phase_motion("antena")
        agita = (0.0 if tiron is None or self.reduced_motion else
                 math.sin(tiron * math.pi * 5) * 0.22 * (1 - tiron))
        alerta = 0.10 * self.hover_suave - 0.20 * self.abandono
        for lado in (-1, 1):
            cr.save()
            cr.translate(lado * 13, -24)
            cr.rotate(lado * (0.10 - alerta + agita))
            cr.scale(lado, 1)

            def oreja():
                cr.move_to(-3, 2)
                cr.curve_to(0, -14, 6, -30, 15, -40)
                cr.curve_to(21, -30, 22, -14, 18, 1)
                cr.curve_to(10, 5, 2, 5, -3, 2)
                cr.close_path()

            self._halo(cr, oreja, 0.7)
            oreja()
            g = cairo.LinearGradient(0, -40, 6, 2)
            g.add_color_stop_rgba(0, *_hex(NARANJA_CLARO))
            g.add_color_stop_rgba(1, *_hex(NARANJA_SOMBRA))
            cr.set_source(g)
            cr.fill_preserve()
            cr.save()
            cr.clip()
            # La punta oscura: en el zorro es lo que separa la oreja del pelaje.
            cr.move_to(4, -26)
            cr.curve_to(8, -34, 12, -38, 15, -40)
            cr.curve_to(19, -33, 20, -28, 20, -23)
            cr.close_path()
            cr.set_source_rgba(*_hex(PARDO, 0.92))
            cr.fill()
            cr.restore()
            oreja()
            self._perfil(cr, 0.34, 1.8)

            # El interior, encajado y un poco más abajo que el borde.
            cr.move_to(3, -1)
            cr.curve_to(5, -13, 9, -24, 14, -31)
            cr.curve_to(17, -22, 17, -11, 15, -2)
            cr.curve_to(10, 1, 6, 1, 3, -1)
            cr.close_path()
            ig = cairo.LinearGradient(0, -31, 0, 0)
            ig.add_color_stop_rgba(0, *_hex(CREMA))
            ig.add_color_stop_rgba(1, *_hex(CREMA_SOMBRA))
            cr.set_source(ig)
            cr.fill()
            cr.restore()

    # -- hocico ---------------------------------------------------------------

    def _rasgos_previos(self, cr, color):
        """El hocico crema con la nariz; va bajo los ojos y sobre el pecho."""
        cr.save()
        cr.translate(0, 13)
        cr.scale(1.30, 1.0)
        cr.arc(0, 0, 10.6, 0, math.tau)
        cr.restore()
        g = cairo.RadialGradient(-3, 8, 2, 0, 13, 17)
        g.add_color_stop_rgba(0, 1, 0.99, 0.96, 1)
        g.add_color_stop_rgba(1, *_hex(CREMA_SOMBRA))
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(*self.TINTA, 0.16)
        cr.set_line_width(1.2)
        cr.stroke()

        # La nariz: un triángulo de esquinas redondeadas, como un botón.
        cr.move_to(-4.6, 3.2)
        cr.curve_to(-4.9, 0.8, -2.8, -0.6, 0, -0.6)
        cr.curve_to(2.8, -0.6, 4.9, 0.8, 4.6, 3.2)
        cr.curve_to(3.6, 5.8, 1.6, 7.4, 0, 7.4)
        cr.curve_to(-1.6, 7.4, -3.6, 5.8, -4.6, 3.2)
        cr.close_path()
        nariz = cairo.LinearGradient(0, -1, 0, 7.4)
        nariz.add_color_stop_rgba(0, 0.32, 0.24, 0.20, 1)
        nariz.add_color_stop_rgba(1, *self.TINTA, 1)
        cr.set_source(nariz)
        cr.fill()
        cr.arc(-1.5, 1.2, 1.1, 0, math.tau)
        cr.set_source_rgba(1, 1, 1, 0.42)
        cr.fill()

    # -- cola -----------------------------------------------------------------

    def _pintar_cola(self, cr, color):
        """La cola en su pivote, sin menear: el vaivén lo pone `_capa_fondo`.

        El penacho no nace en el pivote sino bastante más afuera: lo que se ve
        de una cola es el penacho, y si cae detrás del cuerpo no se lee.
        """
        cr.save()
        cr.translate(-14, -8)

        def silueta():
            cr.move_to(6, 14)
            cr.curve_to(-20, 24, -50, 20, -64, -2)
            cr.curve_to(-80, -24, -72, -56, -47, -66)
            cr.curve_to(-34, -70, -23, -62, -22, -50)
            cr.curve_to(-21, -40, -27, -32, -33, -24)
            cr.curve_to(-42, -12, -30, 4, 6, 14)
            cr.close_path()

        self._halo(cr, silueta, 1.1)
        silueta()
        g = cairo.RadialGradient(-20, 0, 4, -46, -30, 70)
        g.add_color_stop_rgba(0, *_hex(NARANJA_CLARO))
        g.add_color_stop_rgba(0.5, *_hex(NARANJA))
        g.add_color_stop_rgba(1, *_hex(NARANJA_SOMBRA))
        cr.set_source(g)
        cr.fill_preserve()

        # La punta se tiñe del ánimo. El degradado va a lo largo de la cola, de
        # la cadera a la punta, y se pinta recortado a ella: así el color ocupa
        # el último tercio del pelo y no una mancha redonda en mitad del lomo.
        cr.save()
        cr.clip()
        punta = cairo.LinearGradient(-18, 4, -44, -58)
        punta.add_color_stop_rgba(0.52, *_hex(color, 0.0))
        punta.add_color_stop_rgba(0.82, *_hex(color, 0.92))
        punta.add_color_stop_rgba(1.0, *_claro(color, 0.26))
        cr.set_source(punta)
        cr.paint()
        cr.restore()

        silueta()
        self._perfil(cr, 0.30, 2.0)
        cr.restore()

    def _cola_grabada(self, color):
        """La cola ya pintada; solo el color del ánimo invalida la copia."""
        clave = tuple(round(c, 2) for c in color[:3])
        if self._cache_fondo and self._cache_fondo[0] == clave:
            return self._cache_fondo[1]

        ancho, alto = COLA_ANCHO * self._ss, COLA_ALTO * self._ss
        superficie = self._cache_fondo[1] if self._cache_fondo else \
            cairo.ImageSurface(cairo.FORMAT_ARGB32, ancho, alto)
        ctx = cairo.Context(superficie)
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_CLEAR)
        ctx.paint()
        ctx.restore()
        ctx.scale(self._ss, self._ss)
        ctx.translate(*COLA_PIVOTE)
        self._pintar_cola(ctx, color)
        superficie.flush()
        self._cache_fondo = (clave, superficie)
        return superficie

    def _capa_fondo(self, cr, color):
        """La cola, meneándose detrás del cuerpo.

        El vaivén es un giro alrededor de su nacimiento, que es barato: la cola
        se pinta una vez y girarla la hace Cairo al pegar la imagen. Se acelera
        cuando tiene algo que enseñarte y se apaga cuando llevas días sin venir,
        que es cuando un zorro deja de menear la cola.
        """
        vel = 5.2 if self.teaching else 1.5
        amplitud = (0.0 if self.reduced_motion else
                    (0.17 if self.teaching else 0.09) * (1 - 0.7 * self.abandono))
        vaiven = math.sin(self.t * vel) * amplitud + self.inercia * 0.5
        if self.mood == "dormido":
            vaiven = 0.0 if self.reduced_motion else math.sin(self.t * 0.8) * 0.02

        superficie = self._cola_grabada(color)
        cr.save()
        cr.translate(self.COLA_X, self.COLA_Y)
        cr.rotate(vaiven)
        cr.scale(1 / self._ss, 1 / self._ss)
        cr.set_source_surface(superficie, -COLA_PIVOTE[0] * self._ss,
                              -COLA_PIVOTE[1] * self._ss)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        cr.restore()

    # -- accesorios -----------------------------------------------------------

    def _accesorio(self, cr, color):
        """Los mismos de Bit, colocados sobre un zorro."""
        if self.accessory == "panuelo":
            cr.move_to(-27, 26)
            cr.curve_to(-14, 32, 14, 32, 27, 26)
            cr.line_to(26, 33)
            cr.curve_to(11, 38, -12, 38, -26, 33)
            cr.close_path()
            cr.set_source_rgba(*_oscuro(color, 0.82))
            cr.fill_preserve()
            self._perfil(cr, 0.26, 1.5)
            cr.arc(26, 32, 5.2, 0, math.tau)
            cr.set_source_rgba(*_hex(color))
            cr.fill_preserve()
            self._perfil(cr, 0.28, 1.4)
            cr.move_to(28, 35)
            cr.line_to(35, 43)
            cr.line_to(24, 41)
            cr.close_path()
            cr.set_source_rgba(*_hex(color))
            cr.fill_preserve()
            self._perfil(cr, 0.24, 1.3)
        elif self.accessory == "gafas":
            cr.save()
            cr.translate(0, self.CARA_BAJA)
            cr.scale(self.CARA_ESCALA, self.CARA_ESCALA)
            cr.set_source_rgba(*self.TINTA, 0.78)
            cr.set_line_width(2.4)
            for dx in (-self.OJO_DX, self.OJO_DX):
                cr.save()
                cr.translate(dx, self.OJO_Y)
                cr.scale(1.10, 1.0)
                cr.arc(0, 0, 11.0, 0, math.tau)
                cr.restore()
                cr.stroke()
            cr.move_to(-2.6, self.OJO_Y - 1)
            cr.curve_to(-1.2, self.OJO_Y - 3, 1.2, self.OJO_Y - 3, 2.6, self.OJO_Y - 1)
            cr.stroke()
            cr.move_to(-24, self.OJO_Y - 3); cr.line_to(-33, self.OJO_Y - 7); cr.stroke()
            cr.move_to(24, self.OJO_Y - 3); cr.line_to(33, self.OJO_Y - 7); cr.stroke()
            cr.restore()
        elif self.accessory == "corona":
            # Entre las orejas, más alta que en Bit para que no se le monte.
            cr.move_to(-15, -38)
            cr.line_to(-18, -55)
            cr.line_to(-7, -46)
            cr.line_to(0, -60)
            cr.line_to(7, -46)
            cr.line_to(18, -55)
            cr.line_to(15, -38)
            cr.close_path()
            cr.set_source_rgba(*_hex("#F2C14E"))
            cr.fill_preserve()
            self._perfil(cr, 0.36, 1.8)
            for x, y in ((-10, -49), (0, -54), (10, -49)):
                cr.arc(x, y, 2.0, 0, math.tau)
                cr.set_source_rgba(*_claro(color, 0.25))
                cr.fill()
