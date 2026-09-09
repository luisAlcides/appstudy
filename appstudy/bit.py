"""Bit: el mochi crema con el asterisco de rayos girando sobre la cabeza.

Es un homenaje hecho a mano a la mascota de Claude —cuerpo crema, tinta cálida,
once rayos en el color del ánimo—, no el logotipo de nadie. Aquí vive solo lo
que le da su aspecto; el movimiento entero lo pone `criatura.Creature`.
"""
import math

import cairo

from .criatura import Creature, _claro, _hex, _oscuro

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

# Bit está dibujado en un lienzo fijo de 152x184 y luego se escala al tamaño
# real del widget: para hacerlo más grande o más pequeño basta con tocar ANCHO y
# ALTO_PET, que las proporciones se mantienen solas.
DISENO = (152, 184)
ANCHO = 168          # el ancho de la mascota al 100 %; el globo manda cuando está abierto
ALTO_PET = 203

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


class Bit(Creature):
    """El mochi crema, con su estallido de once rayos y su insignia de luz."""

    CLAVE = "bit"
    NOMBRE = "Bit"
    DISENO = DISENO
    ANCHO, ALTO_PET = ANCHO, ALTO_PET
    CUERPO_LADO = CUERPO_LADO
    RX, RY = 39, 35                       # mejillas amplias, silueta de mochi

    MOODS = MOODS
    COLOR_BASE = TERRACOTA
    CHAT = CHAT
    COLOR_LENGUA = COLOR_CORAZON = TERRACOTA
    PELAJE_CLARO, PELAJE, PELAJE_SOMBRA = CREMA_CLARO, CREMA, CREMA_SOMBRA

    # Cuánto se agrandan y bajan los rasgos dentro del cuerpo. Los accesorios no
    # se tocan: las gafas y la corona van con la cabeza, no con la cara.
    CARA_ESCALA, CARA_BAJA = 1.09, 3.0

    def _marca(self, cr, color):
        """Pequeña insignia de luz: un detalle propio, legible incluso al 50 %.

        Va más abajo que la cara, que ocupa bastante sitio, para no montársele
        a la boca.
        """
        cr.move_to(0, 26)
        cr.curve_to(1, 29, 2, 30, 5, 31)
        cr.curve_to(2, 32, 1, 33, 0, 36)
        cr.curve_to(-1, 33, -2, 32, -5, 31)
        cr.curve_to(-2, 30, -1, 29, 0, 26)
        cr.set_source_rgba(*_hex(color, 0.72))
        cr.fill()

    def _forma(self, cr, rx, ry):
        """La silueta del cuerpo: un mochi, redondo arriba y ancho y plano abajo."""
        k = 0.5523
        cr.move_to(0, -ry)
        cr.curve_to(rx * 0.88 * k * 1.25, -ry, rx * 0.93, -ry * k * 1.08, rx * 0.95, -ry * 0.08)
        cr.curve_to(rx * 0.99, ry * 0.50, rx * 0.66, ry, 0, ry)
        cr.curve_to(-rx * 0.66, ry, -rx * 0.99, ry * 0.50, -rx * 0.95, -ry * 0.08)
        cr.curve_to(-rx * 0.93, -ry * k * 1.08, -rx * 0.88 * k * 1.25, -ry, 0, -ry)
        cr.close_path()

    def _pintar_estrella(self, cr, color, r, inercia, fase):
        """Dibuja el estallido centrado en el origen, sin girarlo ni latir.

        Es la parte cara del fotograma: once rayos con dos trazos anchos de halo
        encima. Se mantiene aparte para poder guardarla en `_cache_fondo` y
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
        self._halo(cr, silueta, 1.2)
        silueta()
        self._perfil(cr, 0.30, 2.4)

        silueta()
        # Más recorrido de luz a sombra: la punta se separa del cuerpo del rayo
        # y los once dejan de leerse como una mancha.
        g = cairo.RadialGradient(-r * 0.28, -r * 0.34, 3, 0, 0, r * 1.02)
        g.add_color_stop_rgba(0, *_claro(color, 0.42))
        g.add_color_stop_rgba(0.38, *_claro(color, 0.10))
        g.add_color_stop_rgba(0.72, *_hex(color))
        g.add_color_stop_rgba(1, *_oscuro(color, 0.72))
        cr.set_source(g)
        cr.fill()

        # Relieves cortos: cada pétalo tiene volumen sin añadir textura ruidosa.
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for i in range(11):
            cr.save()
            cr.rotate(i * math.tau / 11 + inercia * math.sin(i * 1.73) * 0.45)
            cr.move_to(r * 0.58, -3.2)
            cr.curve_to(r * 0.70, -4.8, r * 0.84, -3.8, r * 0.92, -1.2)
            cr.set_source_rgba(1, 0.96, 0.87, 0.30)
            cr.set_line_width(2.3)
            cr.stroke()
            cr.restore()

    def _estrella_grabada(self, color, r, inercia, fase):
        """El estallido ya pintado en una imagen, listo para girar y pegar.

        Girar y escalar son cosas que Cairo hace al pegar la imagen, así que no
        entran en la clave: mientras el color, el tamaño y la onda sigan siendo
        los mismos, el fotograma siguiente reutiliza este dibujo tal cual.
        """
        clave = (tuple(round(c, 2) for c in color[:3]), round(r, 1),
                 round(inercia, 1), round(fase, 2), self.reduced_motion,
                 round(self.abandono, 2))
        if self._cache_fondo and self._cache_fondo[0] == clave:
            return self._cache_fondo[1]

        # El lienzo se reaprovecha entre repintados: pedir 280 kB al sistema cada
        # vez que la onda avanza costaba más que volver a trazar los rayos.
        lado = ESTRELLA_LADO * self._ss
        superficie = self._cache_fondo[1] if self._cache_fondo else \
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
        self._cache_fondo = (clave, superficie)
        return superficie

    def _capa_fondo(self, cr, color):
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
        vuelta = self.giro_fondo + inercia
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
            # Las gafas van sobre los ojos, así que siguen a la cara cuando esta
            # se agranda o se baja; el pañuelo y la corona no, que van al cuerpo.
            cr.save()
            cr.translate(0, self.CARA_BAJA)
            cr.scale(self.CARA_ESCALA, self.CARA_ESCALA)
            cr.set_source_rgba(*self.TINTA, 0.78)
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
            cr.restore()
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
