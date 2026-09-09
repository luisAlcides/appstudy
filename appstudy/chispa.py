"""Chispa: el zorro naranja de cola turquesa.

La segunda mascota. Comparte motor con Bit —respira, parpadea, salta, sigue al
ratón—, así que aquí solo vive lo que la hace un zorro: la cola que se menea
detrás, las orejas, el hocico, el rombo de la frente y la paleta.

El pelaje naranja no cambia nunca. Lo que lleva el color del ánimo son el rombo,
la punta de la cola y los cachetes, igual que el asterisco de Bit: así el estado
se lee de un vistazo sin que la mascota cambie de especie cada pocas horas.
"""
import math

import cairo

from .criatura import Creature, _claro, _hex, _oscuro

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
ANCHO = 194
ALTO_PET = 210

# La cola se guarda pintada y luego solo se gira, como el estallido de Bit: es
# la pieza cara del fotograma y lo único que cambia siempre es su vaivén. El
# lienzo no es cuadrado ni está centrado en el pivote: la cola sale toda hacia
# un lado, y un cuadrado que la abarcase gastaría el triple de memoria.
COLA_ANCHO, COLA_ALTO = 124, 100
COLA_PIVOTE = (112, 84)          # dónde cae el nacimiento de la cola en ese lienzo

CUERPO_LADO = 130


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
