"""Las gráficas, dibujadas a mano con Cairo.

Nada de bibliotecas de gráficos: son cuatro dibujos sencillos y Cairo ya está
aquí por la mascota. Cada uno es un `Gtk.DrawingArea` con su función de pintado,
así que se redibujan al cambiar de tamaño y siguen el tema claro u oscuro.

Los datos vienen ya masticados de `estadisticas.py`; aquí solo se convierten en
rectángulos y líneas.
"""
import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango, PangoCairo  # noqa: E402

# Verdes del mapa de calor, de menos a más, como el cuadro de contribuciones
VERDES = ((0.85, 0.93, 0.86), (0.60, 0.83, 0.65), (0.35, 0.72, 0.48),
          (0.18, 0.58, 0.36), (0.08, 0.42, 0.25))
VERDES_OSCURO = ((0.13, 0.22, 0.16), (0.15, 0.38, 0.25), (0.20, 0.55, 0.34),
                 (0.30, 0.72, 0.45), (0.45, 0.87, 0.58))


def oscuro() -> bool:
    try:
        return Adw.StyleManager.get_default().get_dark()
    except Exception:
        return False


def _tinta(alfa=1.0):
    """El color del texto y las líneas, según el tema."""
    return (0.92, 0.92, 0.92, alfa) if oscuro() else (0.12, 0.12, 0.12, alfa)


def _hex_a_rgb(color: str):
    h = (color or "#3584e4").lstrip("#")
    if len(h) != 6:
        h = "3584e4"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _texto(cr, x, y, texto, tam=11, alfa=0.75, centrado=False, derecha=False,
           negrita=False, ancho_max=None):
    """Una etiqueta con Pango, que sabe de acentos y de tipografías del sistema.

    Con `ancho_max`, lo que no cabe se recorta con puntos suspensivos en vez de
    partirse a mitad de palabra.
    """
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription()
    desc.set_size(int(tam * Pango.SCALE))
    if negrita:
        desc.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(desc)
    layout.set_text(texto, -1)
    if ancho_max:
        layout.set_width(int(ancho_max * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        # Con ancho fijo el texto se coloca dentro de la caja, así que la
        # alineación va dentro del layout y no restando la anchura después.
        layout.set_alignment(Pango.Alignment.RIGHT if derecha
                             else Pango.Alignment.CENTER if centrado
                             else Pango.Alignment.LEFT)
    ancho, alto = layout.get_pixel_size()
    # Ojo: con ancho fijo, get_pixel_size devuelve lo que mide el *texto*, no la
    # caja. Colocar por ahí manda las etiquetas cortas fuera de su sitio.
    caja = ancho_max if ancho_max else ancho
    if centrado:
        x -= caja / 2
    elif derecha:
        x -= caja
    cr.set_source_rgba(*_tinta(alfa))
    cr.move_to(x, y - alto / 2)
    PangoCairo.show_layout(cr, layout)
    return ancho, alto


def _redondeado(cr, x, y, ancho, alto, radio):
    radio = min(radio, ancho / 2, alto / 2)
    if radio <= 0:
        cr.rectangle(x, y, ancho, alto)
        return
    cr.new_sub_path()
    cr.arc(x + ancho - radio, y + radio, radio, -math.pi / 2, 0)
    cr.arc(x + ancho - radio, y + alto - radio, radio, 0, math.pi / 2)
    cr.arc(x + radio, y + alto - radio, radio, math.pi / 2, math.pi)
    cr.arc(x + radio, y + radio, radio, math.pi, 3 * math.pi / 2)
    cr.close_path()


def area(alto, pintar, datos_fn):
    """Un lienzo que se repinta solo, pidiendo los datos cuando toca."""
    lienzo = Gtk.DrawingArea(content_height=alto, hexpand=True)
    lienzo.set_draw_func(lambda _a, cr, w, h: pintar(cr, w, h, datos_fn()))
    return lienzo


# ---------------------------------------------------------------- mapa de calor

LADO_MIN, LADO_MAX = 7, 15
MESES = ("ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic")


def pintar_mapa_calor(cr, ancho, alto, datos):
    """Un año de repasos: una columna por semana, una fila por día."""
    import time

    semanas = datos["semanas"]
    if not semanas:
        return
    margen_izq, margen_arriba = 26, 16
    hueco = 3
    disponible = ancho - margen_izq - 6
    lado = max(LADO_MIN, min(LADO_MAX,
                             int((disponible - len(semanas) * hueco) / len(semanas))))
    paleta = VERDES_OSCURO if oscuro() else VERDES
    maximo = max(datos["maximo"], 1)

    # Los nombres de mes, encima de la primera semana que cae en cada uno
    ultimo_mes = None
    for i, semana in enumerate(semanas):
        primero = semana[0]
        mes = time.localtime(primero["ts"]).tm_mon
        if mes != ultimo_mes:
            ultimo_mes = mes
            x = margen_izq + i * (lado + hueco)
            if x < ancho - 24:
                _texto(cr, x, margen_arriba / 2, MESES[mes - 1], tam=8, alfa=0.55)

    for i, nombre in ((0, "L"), (2, "X"), (4, "V")):
        y = margen_arriba + i * (lado + hueco) + lado / 2
        _texto(cr, margen_izq - 8, y, nombre, tam=8, alfa=0.5, derecha=True)

    for i, semana in enumerate(semanas):
        for j, celda in enumerate(semana):
            x = margen_izq + i * (lado + hueco)
            y = margen_arriba + j * (lado + hueco)
            if celda["futuro"]:
                continue
            if celda["n"] == 0:
                cr.set_source_rgba(*_tinta(0.09))
            else:
                # Escala por raíz: si no, un solo día de cien aplana el resto
                fuerza = math.sqrt(celda["n"] / maximo)
                cr.set_source_rgb(*paleta[min(len(paleta) - 1,
                                              int(fuerza * len(paleta)))])
            _redondeado(cr, x, y, lado, lado, 2)
            cr.fill()
            if celda["hoy"]:
                cr.set_source_rgba(*_tinta(0.55))
                cr.set_line_width(1.2)
                _redondeado(cr, x - 0.6, y - 0.6, lado + 1.2, lado + 1.2, 2.5)
                cr.stroke()

    # La leyenda, abajo a la derecha
    base_y = margen_arriba + 7 * (lado + hueco) + 10
    if base_y + lado < alto:
        x = ancho - 6 - (len(paleta) + 1) * (lado + hueco) - 34
        ancho_menos, _ = _texto(cr, x, base_y + lado / 2, "menos", tam=8, alfa=0.5)
        x += ancho_menos + 6
        cr.set_source_rgba(*_tinta(0.09))
        _redondeado(cr, x, base_y, lado, lado, 2)
        cr.fill()
        x += lado + hueco
        for color in paleta:
            cr.set_source_rgb(*color)
            _redondeado(cr, x, base_y, lado, lado, 2)
            cr.fill()
            x += lado + hueco
        _texto(cr, x + 2, base_y + lado / 2, "más", tam=8, alfa=0.5)


def alto_mapa_calor(semanas: int) -> int:
    """Lo que ocupa el mapa, para reservarle sitio sin recortarlo."""
    return 16 + 7 * (LADO_MAX + 3) + 30


# ------------------------------------------------------------------- retención

def pintar_retencion(cr, ancho, alto, datos):
    """Una barra por mazo, con la retención objetivo marcada con una línea."""
    mazos = [m for m in datos["mazos"] if m["retencion"] is not None]
    if not mazos:
        _texto(cr, ancho / 2, alto / 2,
               "Todavía no hay repasos suficientes para medirlo",
               tam=10, alfa=0.5, centrado=True)
        return

    etiqueta = 150
    izq = etiqueta + 8
    der = ancho - 52
    if der <= izq:
        return
    fila_alto = min(30, (alto - 22) / len(mazos))
    grosor = min(16, fila_alto - 8)

    # El eje va del 50 % al 100 %: por debajo del 50 no hay nada que enseñar
    def x_de(valor):
        return izq + (max(0.5, min(1.0, valor)) - 0.5) / 0.5 * (der - izq)

    objetivo = datos.get("objetivo")
    if objetivo:
        x = x_de(objetivo)
        cr.set_source_rgba(*_tinta(0.35))
        cr.set_line_width(1)
        cr.set_dash([3, 3])
        cr.move_to(x, 12)
        cr.line_to(x, 12 + len(mazos) * fila_alto)
        cr.stroke()
        cr.set_dash([])
        _texto(cr, x, 6, f"pedido {objetivo * 100:.0f} %", tam=8, alfa=0.5,
               centrado=True)

    for i, m in enumerate(mazos):
        y = 16 + i * fila_alto + (fila_alto - grosor) / 2
        _texto(cr, etiqueta, y + grosor / 2,
               f"{m['icon']} {m['name']}", tam=10, alfa=0.85, derecha=True,
               ancho_max=etiqueta - 4)
        cr.set_source_rgba(*_tinta(0.08))
        _redondeado(cr, izq, y, der - izq, grosor, grosor / 2)
        cr.fill()
        largo = x_de(m["retencion"]) - izq
        if largo > 1:
            cr.set_source_rgb(*_hex_a_rgb(m["color"]))
            _redondeado(cr, izq, y, largo, grosor, grosor / 2)
            cr.fill()
        _texto(cr, ancho - 6, y + grosor / 2,
               f"{m['retencion'] * 100:.0f} %", tam=10, alfa=0.9, derecha=True,
               negrita=True)


# --------------------------------------------------------------- vencimientos

def pintar_vencimientos(cr, ancho, alto, datos):
    """Las tarjetas que vencen cada día del próximo mes."""
    if not datos:
        return
    izq, der = 34, ancho - 6
    arriba, abajo = 14, alto - 20
    if der <= izq or abajo <= arriba:
        return

    maximo = max((d["total"] for d in datos), default=0)
    if maximo == 0:
        _texto(cr, ancho / 2, alto / 2, "No hay nada pendiente en 30 días",
               tam=10, alfa=0.5, centrado=True)
        return

    hueco = 2
    paso = (der - izq) / len(datos)
    barra = max(2.0, paso - hueco)

    # Tres líneas de referencia con su número a la izquierda
    for parte in (0.0, 0.5, 1.0):
        y = abajo - parte * (abajo - arriba)
        cr.set_source_rgba(*_tinta(0.10))
        cr.set_line_width(1)
        cr.move_to(izq, y)
        cr.line_to(der, y)
        cr.stroke()
        _texto(cr, izq - 6, y, f"{int(maximo * parte)}", tam=8, alfa=0.5,
               derecha=True)

    for i, d in enumerate(datos):
        x = izq + i * paso
        altura = (d["total"] / maximo) * (abajo - arriba)
        # Lo atrasado se dibuja en rojo, encima del primer día
        if d["atrasadas"]:
            alto_atras = (d["atrasadas"] / maximo) * (abajo - arriba)
            cr.set_source_rgb(0.75, 0.11, 0.16)
            _redondeado(cr, x, abajo - alto_atras, barra, alto_atras, 2)
            cr.fill()
            altura -= alto_atras
            if altura > 0.5:
                cr.set_source_rgb(*_hex_a_rgb("#3584e4"))
                _redondeado(cr, x, abajo - alto_atras - altura, barra, altura, 2)
                cr.fill()
        elif altura > 0.5:
            cr.set_source_rgb(*_hex_a_rgb("#3584e4"))
            _redondeado(cr, x, abajo - altura, barra, altura, 2)
            cr.fill()
        if i % 7 == 0:
            _texto(cr, x + barra / 2, abajo + 10,
                   "hoy" if i == 0 else f"+{i}d", tam=8, alfa=0.5, centrado=True)


# ------------------------------------------------------ tiempo de respuesta

def pintar_tiempos(cr, ancho, alto, datos):
    """Cuánto tardas en contestar según el nivel del contenido."""
    if not datos:
        _texto(cr, ancho / 2, alto / 2, "Aún no hay respuestas cronometradas",
               tam=10, alfa=0.5, centrado=True)
        return
    etiqueta = 130
    izq, der = etiqueta + 8, ancho - 60
    if der <= izq:
        return
    maximo = max(d["mediana_ms"] for d in datos) or 1
    fila_alto = min(32, (alto - 16) / len(datos))
    grosor = min(16, fila_alto - 8)

    for i, d in enumerate(datos):
        y = 10 + i * fila_alto + (fila_alto - grosor) / 2
        _texto(cr, etiqueta, y + grosor / 2, d["nombre"], tam=10, alfa=0.85,
               derecha=True, ancho_max=etiqueta - 4)
        cr.set_source_rgba(*_tinta(0.08))
        _redondeado(cr, izq, y, der - izq, grosor, grosor / 2)
        cr.fill()
        largo = (d["mediana_ms"] / maximo) * (der - izq)
        if largo > 1:
            # Más oscuro cuanto más te cuesta
            fuerza = d["mediana_ms"] / maximo
            cr.set_source_rgb(0.90 - 0.55 * fuerza, 0.55 - 0.28 * fuerza,
                              0.06 + 0.10 * fuerza)
            _redondeado(cr, izq, y, largo, grosor, grosor / 2)
            cr.fill()
        segundos = d["mediana_ms"] / 1000
        _texto(cr, ancho - 6, y + grosor / 2, f"{segundos:.1f} s", tam=10,
               alfa=0.9, derecha=True, negrita=True)


# ------------------------------------------------------------------- madurez

def pintar_madurez(cr, ancho, alto, datos):
    """Una sola barra apilada con el reparto de tus tarjetas."""
    total = sum(d["n"] for d in datos)
    if not total:
        return
    grosor = 22
    y = 8
    x = 0
    for d in datos:
        if not d["n"]:
            continue
        largo = d["n"] / total * ancho
        cr.set_source_rgb(*_hex_a_rgb(d["color"]))
        cr.rectangle(x, y, largo + 0.5, grosor)
        cr.fill()
        x += largo

    # La leyenda debajo, en una fila
    x = 0
    y_leyenda = y + grosor + 14
    for d in datos:
        if not d["n"]:
            continue
        cr.set_source_rgb(*_hex_a_rgb(d["color"]))
        _redondeado(cr, x, y_leyenda - 4, 8, 8, 2)
        cr.fill()
        etiqueta = f"{d['nombre']} · {d['n']}"
        w, _ = _texto(cr, x + 13, y_leyenda, etiqueta, tam=9, alfa=0.75)
        x += 13 + w + 16
        if x > ancho - 60:
            break


def leyenda_madurez(datos) -> str:
    total = sum(d["n"] for d in datos)
    if not total:
        return ""
    return " · ".join(f"{d['nombre']}: {d['n']}" for d in datos if d["n"])


# ------------------------------------------------------------ la semana, mini

def pintar_semana(cr, ancho, alto, datos):
    """Siete barras con los días de la semana: la versión pequeña del mapa."""
    serie = datos.get("serie") or []
    if not serie:
        return
    maximo = max((d["n"] for d in serie), default=0) or 1
    abajo = alto - 16
    arriba = 8
    paso = ancho / len(serie)
    barra = min(28, paso - 8)
    for i, d in enumerate(serie):
        x = i * paso + (paso - barra) / 2
        altura = max(2.0, (d["n"] / maximo) * (abajo - arriba))
        cr.set_source_rgb(*(_hex_a_rgb("#2ec27e") if d["n"] else (0.6, 0.6, 0.6)))
        if not d["n"]:
            cr.set_source_rgba(*_tinta(0.12))
        _redondeado(cr, x, abajo - altura, barra, altura, 3)
        cr.fill()
        _texto(cr, x + barra / 2, abajo + 8, d["nombre"][:2], tam=8, alfa=0.55,
               centrado=True)
        if d["n"]:
            _texto(cr, x + barra / 2, abajo - altura - 7, str(d["n"]), tam=8,
                   alfa=0.8, centrado=True)
