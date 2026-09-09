"""Compone a Chispa a partir de sus capas. Aquí es donde parpadea de verdad.

La diferencia con lo que había: el ojo es una capa propia y debajo hay pelaje
reconstruido, así que el párpado no *tapa* el ojo —lo cierra—. Lo que queda
descubierto al bajar el párpado es la base, que ya es cara.
"""
from __future__ import annotations

import json
from pathlib import Path

import cairo

from . import capas_chispa

# Grosor y color de la pestaña, el filo del párpado. El tono sale del contorno
# del ojo del propio dibujo, no de un negro inventado.
PESTANA = (0.11, 0.075, 0.06)
PESTANA_GROSOR = 0.16          # fracción de la altura del ojo
CIERRE_VISIBLE = 0.06          # por debajo de esto no se dibuja nada encima

# Chispa no tiene brazos: la mano nace pegada al cuerpo. Pasados unos 15 grados
# se despega y se ve el truco, así que el giro va topado ahí.
GIRO_MANO = 0.26               # radianes ≈ 15°
GIRO_PIE = 0.10
MIEMBROS = ("mano_izq", "mano_der", "pie_izq", "pie_der")
BOCA_ABRE = 0.55               # cuánto crece la boca al hablar, en su propia altura


class Rig:
    """Las capas de una pose y cómo se componen."""

    def __init__(self, manifiesto: dict, carpeta: Path):
        self.manifiesto = manifiesto
        self.carpeta = carpeta
        self._cache: dict = {}

    def _superficie(self, nombre: str):
        if nombre not in self._cache:
            ruta = self.carpeta / f"{nombre}.png"
            try:
                self._cache[nombre] = cairo.ImageSurface.create_from_png(str(ruta))
            except (OSError, cairo.Error):
                self._cache[nombre] = None
        return self._cache[nombre]

    def piezas(self, indice: int) -> dict:
        return self.manifiesto["poses"].get(str(indice), {})

    def tiene(self, indice: int, pieza: str) -> bool:
        return pieza in self.piezas(indice)

    def parpadea(self, indice: int) -> bool:
        """Hay poses que ya vienen dibujadas con los ojos cerrados."""
        return self.tiene(indice, "ojo_izq") and self.tiene(indice, "ojo_der")

    def mueve_miembros(self, indice: int) -> bool:
        """Si esta pose tiene manos y pies separados y se pueden girar."""
        return all(self.tiene(indice, m) for m in MIEMBROS)

    def habla(self, indice: int) -> bool:
        return self.tiene(indice, "boca")

    def dibujar(self, cr, indice: int, cierre: float = 0.0,
                balanceo: float = 0.0, apertura: float = 0.0) -> bool:
        """Pinta la pose entera. Devuelve False si le faltan capas.

        `balanceo` va de -1 a 1 y mueve manos y pies en oposición, que es como
        se balancea cualquier bicho al andar o al esperar. `apertura` va de 0 a
        1 y abre la boca.
        """
        base = self._superficie(f"base-{indice}")
        if base is None:
            return False
        cr.save()
        cr.set_source_surface(base, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()
        for nombre, datos in self.piezas(indice).items():
            capa = self._superficie(f"{indice}-{nombre}")
            if capa is None:
                return False
            if nombre.startswith("ojo"):
                self._ojo(cr, capa, datos, cierre,
                          base.get_width(), base.get_height())
            elif nombre == "boca":
                self._boca(cr, capa, datos, apertura,
                           base.get_width(), base.get_height())
            else:
                self._miembro(cr, capa, datos, nombre, balanceo,
                              base.get_width(), base.get_height())
        return True

    def _boca(self, cr, capa, datos, apertura, ancho, alto):
        """La boca se estira desde su borde de arriba, que es por donde se abre.

        Al cerrarse del todo no desaparece: se queda en su tamaño del dibujo,
        que ya es una boca. Lo que se ve por debajo, si crece, es el hocico
        reconstruido.
        """
        apertura = max(0.0, min(1.0, apertura))
        if apertura <= 0.01:
            cr.save()
            cr.set_source_surface(capa, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BEST)
            cr.paint()
            cr.restore()
            return
        x0, y0, x1, y1 = datos["caja"]
        techo = y0 * alto
        cr.save()
        cr.translate(0, techo)
        cr.scale(1.0, 1.0 + BOCA_ABRE * apertura)
        cr.translate(0, -techo)
        cr.set_source_surface(capa, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()

    def _miembro(self, cr, capa, datos, nombre, balanceo, ancho, alto):
        """Una mano o un pie, girando desde donde nace."""
        lado = -1 if nombre.endswith("izq") else 1
        tope = GIRO_MANO if nombre.startswith("mano") else GIRO_PIE
        angulo = max(-1.0, min(1.0, balanceo)) * tope * lado
        px, py = datos["pivote"]
        cr.save()
        if angulo:
            cr.translate(px * ancho, py * alto)
            cr.rotate(angulo)
            cr.translate(-px * ancho, -py * alto)
        cr.set_source_surface(capa, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()

    def _ojo(self, cr, capa, datos, cierre, ancho, alto):
        """El ojo, recortado contra el párpado que baja.

        El párpado es una línea que cruza el ojo de lado a lado. Lo que queda
        por encima no se pinta, y ahí aparece la base: pelaje.
        """
        x0, y0, x1, y1 = datos["caja"]
        cierre = max(0.0, min(1.0, cierre))
        # Un pelo por debajo del borde inferior, para que al cerrar del todo no
        # quede una raya de ojo asomando
        borde = y0 + (y1 - y0) * cierre * 1.04
        cr.save()
        if cierre > 0:
            cr.rectangle(0, borde * alto, ancho, alto)
            cr.clip()
        cr.set_source_surface(capa, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BEST)
        cr.paint()
        cr.restore()
        if cierre <= CIERRE_VISIBLE:
            return
        # La pestaña: el filo del párpado, más marcado cuanto más cerrado
        cr.save()
        cr.set_source_rgba(*PESTANA, min(1.0, (cierre - CIERRE_VISIBLE) * 3.0))
        cr.set_line_width(max(1.0, (y1 - y0) * alto * PESTANA_GROSOR))
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        medio = (x0 + x1) / 2 * ancho
        semi = (x1 - x0) / 2 * ancho * 0.94
        hundido = (y1 - y0) * alto * 0.16 * cierre
        cr.move_to(medio - semi, borde * alto - hundido * 0.3)
        cr.curve_to(medio - semi * 0.45, borde * alto + hundido,
                    medio + semi * 0.45, borde * alto + hundido,
                    medio + semi, borde * alto - hundido * 0.3)
        cr.stroke()
        cr.restore()


def cargar(carpeta: Path | None = None) -> Rig | None:
    """El rig si las capas están y valen; `None` si no. Nunca lanza.

    Que devuelva `None` no es un error: es la señal de que hay que dibujar como
    siempre. La mascota nunca se queda sin dibujar.
    """
    carpeta = carpeta or capas_chispa.carpeta()
    try:
        manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifiesto.get("version") != capas_chispa.VERSION:
        return None
    if manifiesto.get("atlas") != capas_chispa.huella_atlas():
        return None
    if not isinstance(manifiesto.get("poses"), dict):
        return None
    return Rig(manifiesto, carpeta)
