"""Deformación local de las extremidades del atlas, sin separar el pelaje.

Una malla continua mantiene unidos hombros, muñecas y tobillos. Los anclajes
usan coordenadas 0..1 dentro de cada celda, independientes del tamaño del PNG.
"""
import math

import cairo

# mano izquierda, derecha, pie izquierdo, derecho; vistos desde la pantalla.
ANCLAJES = (
    ((.49, .73), (.80, .72), (.49, .92), (.73, .92)),
    ((.40, .72), (.78, .44), (.44, .92), (.67, .92)),
    ((.49, .77), (.58, .77), (.53, .89), (.73, .89)),
    ((.26, .30), (.79, .34), (.43, .84), (.69, .84)),
    ((.56, .49), (.67, .73), (.50, .84), (.69, .84)),
)


def movimientos(indice, tiempo, intensidad=1.0, saludo=None):
    """Desplazamientos suaves con alcance local; el descanso no mueve patas."""
    if indice == 5 or intensidad <= 0:
        return ()
    salida = []
    for n, (x, y) in enumerate(ANCLAJES[indice]):
        mano = n < 2
        fase = tiempo * (3.0 if mano else 2.4) + n * math.pi
        dx = math.sin(fase) * (.010 if mano else .004)
        dy = math.sin(fase + .7) * (.006 if mano else .009)
        rx, ry = (.12, .17) if mano else (.11, .10)
        if indice == 1 and n == 1:
            # El saludo empieza y termina en la posición del atlas.
            envolvente = math.sin(math.pi * saludo) ** 2 if saludo is not None else 1
            dx = math.sin(tiempo * 14) * .040 * envolvente
            dy = math.sin(tiempo * 14 + .5) * .012 * envolvente
            rx, ry = .15, .17
        elif indice == 3 and mano:
            dx = math.sin(tiempo * 9 + n * math.pi) * .025
            dy = math.sin(tiempo * 9 + n * math.pi) * .024
        elif indice == 2:
            # Toques cortos sobre el teclado, sin mover la pantalla del portátil.
            dx = 0
            dy = math.sin(tiempo * 13 + n * math.pi) * (.007 if mano else .003)
            rx, ry = (.07, .055) if mano else (.085, .065)
        elif indice == 4 and mano:
            dx *= .45
            dy *= .45
            rx, ry = .09, .10
        salida.append((x, y, rx, ry, dx * intensidad, dy * intensidad))
    return tuple(salida)


def desplazar(x, y, gestos):
    """La influencia y su pendiente llegan a cero en el borde de cada zona."""
    dx = dy = 0.0
    for cx, cy, rx, ry, mx, my in gestos:
        distancia = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
        if distancia < 1:
            peso = (1 - distancia) ** 2
            dx += mx * peso
            dy += my * peso
    return x + dx, y + dy


def pintar(cr, superficie, gestos):
    """Texturiza solo los triángulos móviles; pinta el resto en una pasada."""
    if not gestos:
        cr.set_source_surface(superficie, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        return
    w, h = superficie.get_width(), superficie.get_height()
    pasos = 24
    vertices = []
    for fila in range(pasos + 1):
        for columna in range(pasos + 1):
            x, y = columna / pasos, fila / pasos
            nx, ny = desplazar(x, y, gestos)
            vertices.append(((x * w, y * h), (nx * w, ny * h)))
    moviles = []
    cr.save()
    # Sin antialias en los recortes compartidos: no aparecen costuras alfa.
    # La textura sí conserva su filtrado bilineal.
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    cr.new_path()
    for fila in range(pasos):
        for columna in range(pasos):
            a = fila * (pasos + 1) + columna
            indices = (a, a + 1, a + pasos + 2, a + pasos + 1)
            puntos = [vertices[i] for i in indices]
            if all(origen == destino for origen, destino in puntos):
                cr.rectangle(columna * w / pasos, fila * h / pasos, w / pasos, h / pasos)
            else:
                moviles.extend(((puntos[0], puntos[1], puntos[2]),
                                (puntos[0], puntos[2], puntos[3])))
    cr.save()
    cr.clip()
    cr.set_source_surface(superficie, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_BILINEAR)
    cr.paint()
    cr.restore()
    cr.new_path()
    for triangulo in moviles:
        origen, destino = zip(*triangulo)
        p, q, r = origen
        u, v, z = destino
        fuente = cairo.Matrix(q[0]-p[0], q[1]-p[1], r[0]-p[0], r[1]-p[1], p[0], p[1])
        fuente.invert()
        objetivo = cairo.Matrix(v[0]-u[0], v[1]-u[1], z[0]-u[0], z[1]-u[1], u[0], u[1])
        cr.save()
        cr.move_to(*u); cr.line_to(*v); cr.line_to(*z); cr.close_path()
        cr.clip()
        cr.transform(fuente.multiply(objetivo))
        cr.set_source_surface(superficie, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        cr.restore()
    cr.restore()
