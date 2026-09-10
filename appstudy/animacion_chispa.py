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


def movimientos(indice, tiempo, intensidad=1.0, saludo=None, voz=0.0,
                risa=None, bostezo=None, estirar=None, rascarse=None, enojado=None):
    """Desplazamientos suaves con alcance local; el descanso no mueve patas."""
    if indice == 5 or intensidad <= 0:
        return ()
    salida = []
    val_enojo = (enojado if isinstance(enojado, (int, float)) else 1.0) if enojado else 0.0
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
            if risa is not None:
                envolvente = math.sin(math.pi * risa)
                dx += math.sin(tiempo * 22 + n * math.pi) * .015 * envolvente
                dy += math.sin(tiempo * 26) * .020 * envolvente
        elif indice == 2:
            # Toques cortos sobre el teclado, sin mover la pantalla del portátil.
            dx = 0
            dy = math.sin(tiempo * 13 + n * math.pi) * (.007 if mano else .003)
            rx, ry = (.07, .055) if mano else (.085, .065)
        elif indice == 4 and mano:
            dx *= .45
            dy *= .45
            rx, ry = .09, .10
            if rascarse is not None and n == 0:
                # La pata izquierda sube hacia la oreja y rasca con rapidez rítmica
                envolvente = math.sin(math.pi * rascarse)
                rx, ry = .14, .16
                dx += .015 * envolvente
                dy += (-0.035 + math.sin(tiempo * 24) * .024) * envolvente
        if voz and mano and indice == 0:
            # Alternar el énfasis evita que ambos brazos funcionen como un
            # metrónomo. La elevación se concentra en el antebrazo.
            enfasis = (.5 + .5 * math.sin(tiempo * 4.6 + n * 2.1)) ** 2
            lado = -1 if n == 0 else 1
            dx += lado * .012 * enfasis * voz
            dy -= .012 * enfasis * voz
            rx, ry = .14, .19
        if bostezo is not None and indice == 0 and mano:
            envolvente = math.sin(math.pi * bostezo)
            lado = -1 if n == 0 else 1
            dx += lado * .016 * envolvente
            dy += .016 * envolvente
            rx, ry = .14, .18
        if estirar is not None and indice == 0:
            envolvente = math.sin(math.pi * estirar)
            if mano:
                lado = -1 if n == 0 else 1
                dx += lado * .012 * envolvente
                dy += .030 * envolvente
                rx, ry = .15, .20
            else:
                dy -= .010 * envolvente
        if risa is not None and indice == 0 and mano:
            envolvente = math.sin(math.pi * risa)
            dy += math.sin(tiempo * 24) * .018 * envolvente
        if val_enojo > 0:
            # Pie impaciente que da toquecitos en el suelo
            if n == 3:
                tap = max(0.0, math.sin(tiempo * 12)) ** 2
                dy -= .016 * tap * val_enojo
            elif mano:
                lado = -1 if n == 0 else 1
                dx += lado * .012 * val_enojo
                dy -= .010 * val_enojo
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


# Centros de los ojos en cada pose, medidos sobre el atlas original.
OJOS = (
    ((.519, .406), (.715, .379)),
    ((.458, .421), (.635, .380)),
    ((.483, .518), (.654, .529)),
    (),  # Celebración: la ilustración ya tiene los ojos cerrados.
    ((.469, .400), (.639, .307)),
    (),  # Descanso: no abrir los ojos de la pose dormida.
)
BOCAS = {0: (.626, .502), 1: (.545, .502), 3: (.550, .381)}


def expresiones(indice, tiempo, mirada=(0, 0), parpadeo=None, guino=None,
                voz=0.0, reducido=False,
                bostezo=None, risa=None, caricia=None, enojado=None):
    """Campos locales de mirada, párpados y boca; no sustituyen el pelaje."""
    if reducido or indice == 5:
        return ()
    cierre = 0.0
    if parpadeo is not None:
        cierre = math.sin(math.pi * parpadeo) ** 2
    salida = []
    mx = max(-1, min(1, mirada[0])) * .004
    my = max(-1, min(1, mirada[1])) * .003
    for n, (x, y) in enumerate(OJOS[indice]):
        c = cierre
        if n == 1 and guino is not None:
            c = max(c, math.sin(math.pi * guino) ** 2)
        if mx or my:
            salida.append((x, y, .068, .075, mx * (1-c), my * (1-c), 0))
    if indice in BOCAS:
        x, y = BOCAS[indice]
        if bostezo is not None:
            # El bostezo abre ampliamente la boca hacia abajo
            envolvente = math.sin(math.pi * bostezo)
            salida.append((x, y, .072, .035, 0, 0, -0.60 * envolvente))
        elif risa is not None:
            envolvente = math.sin(math.pi * risa)
            temblor = math.sin(tiempo * 24) * 0.25 * envolvente
            salida.append((x, y, .072, .028, 0, 0, temblor))
        elif voz:
            # Sílabas visuales con cadencia regular y pausas suaves, ligadas a la
            # duración de voz. La apertura alterna sin espasmos cuadráticos.
            pulso = (.5 + .5 * math.sin(tiempo * 13 + .5 * math.sin(tiempo * 2.3)))
            cierre_boca = .85 * pulso * voz
            salida.append((x, y, .072, .028, 0, 0, cierre_boca))
        elif enojado:
            val_enojo = (enojado if isinstance(enojado, (int, float)) else 1.0)
            salida.append((x, y, .072, .028, 0, 0, 0.45 * val_enojo))
    return tuple(salida)


def parpados(cr, indice, ancho, alto, parpadeo=None, guino=None, reducido=False,
             bostezo=None, risa=None, estirar=None, caricia=None, rascarse=None,
             enojado=None):
    """Párpados sobre el ojo, sin comprimir mejillas ni estirar el hocico."""
    if reducido or indice in (3, 5):
        return
    val_enojo = (enojado if isinstance(enojado, (int, float)) else 1.0) if enojado else 0.0
    for n, (x, y) in enumerate(OJOS[indice]):
        cierre = math.sin(math.pi * parpadeo) ** 2 if parpadeo is not None else 0
        if n == 1 and guino is not None:
            cierre = max(cierre, math.sin(math.pi * guino) ** 2)
        if bostezo is not None:
            cierre = max(cierre, math.sin(math.pi * bostezo) * 0.95)
        if risa is not None:
            cierre = max(cierre, math.sin(math.pi * risa) * 0.90)
        if estirar is not None:
            cierre = max(cierre, math.sin(math.pi * estirar) * 0.75)
        if caricia is not None:
            cierre = max(cierre, caricia * 0.65)
        if rascarse is not None and n == 0:
            cierre = max(cierre, math.sin(math.pi * rascarse) * 0.85)
        if val_enojo > 0:
            cierre = max(cierre, 0.48 * val_enojo)
        if cierre < .001:
            continue
        cr.save()
        cr.translate(x * ancho, y * alto)
        cr.scale(ancho / 512, alto / 512)
        if val_enojo > 0:
            # Ceño fruncido: inclinación hacia el interior de la cara
            angulo = 0.35 if n == 0 else -0.35
            cr.rotate(angulo * val_enojo)
        # El arco abraza la forma del ojo ilustrado; el párpado inferior
        # mantiene el crema del hocico y el superior el naranja del pelaje.
        cr.save()
        cr.scale(34, 32)
        cr.arc(0, 0, 1, 0, math.tau)
        cr.restore()
        cr.clip()
        superior = -32 * (1-cierre)
        inferior = 32 * (1-cierre)
        naranja = cairo.LinearGradient(0, -32, 0, 8)
        naranja.add_color_stop_rgb(0, .96, .53, .19)
        naranja.add_color_stop_rgb(1, 1.0, .66, .32)
        cr.set_source(naranja)
        cr.rectangle(-34, -34, 68, superior+34)
        cr.fill()
        crema = cairo.LinearGradient(0, -2, 0, 32)
        crema.add_color_stop_rgb(0, .98, .91, .80)
        crema.add_color_stop_rgb(1, 1, .97, .90)
        cr.set_source(crema)
        cr.rectangle(-34, inferior, 68, 34-inferior)
        cr.fill()
        cr.set_source_rgba(.20, .12, .08, min(1, cierre * 2))
        cr.set_line_width(2.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(-29, superior)
        cr.curve_to(-10, superior+3*cierre, 10, superior+3*cierre, 29, superior)
        cr.stroke()
        cr.restore()


def desplazar_rasgos(x, y, rasgos):
    for cx, cy, rx, ry, mx, my, cierre in rasgos:
        distancia = math.hypot((x-cx)/rx, (y-cy)/ry)
        if distancia < 1:
            borde = min(1.0, (1-distancia)/.40)
            peso = borde*borde*(3-2*borde)
            x += mx*peso
            # La mandíbula inferior sube para cerrar la boca al hablar;
            # el hocico y los dientes superiores se mantienen firmes.
            factor_cierre = 0.1 if y < cy else 1.0
            y += (my - (y-cy)*cierre*factor_cierre)*peso
    return x, y


def pintar(cr, superficie, gestos, rasgos=()):
    """Texturiza solo los triángulos móviles; pinta el resto en una pasada."""
    if not gestos and not rasgos:
        cr.set_source_surface(superficie, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
        cr.paint()
        return
    w, h = superficie.get_width(), superficie.get_height()
    pasos = 32 if rasgos else 24
    xs = {i / pasos for i in range(pasos + 1)}
    ys = set(xs)
    # La boca mide pocos píxeles: la cuadrícula general caía casi entera
    # fuera de ella y anulaba el gesto. Añadir vértices locales conserva
    # los límites del hocico y permite cerrar la sonrisa visiblemente.
    for cx, cy, rx, ry, _mx, _my, cierre in rasgos:
        if cierre:
            xs.update(cx + rx*f for f in (-1, -.6, 0, .6, 1))
            ys.update(cy + ry*f for f in (-1, -.6, -.3, 0, .3, .6, 1))
    xs, ys = sorted(xs), sorted(ys)
    columnas, filas = len(xs)-1, len(ys)-1
    vertices = []
    for y in ys:
        for x in xs:
            nx, ny = desplazar(x, y, gestos)
            nx, ny = desplazar_rasgos(nx, ny, rasgos)
            vertices.append(((x * w, y * h), (nx * w, ny * h)))
    moviles = []
    for fila in range(filas):
        for columna in range(columnas):
            a = fila * (columnas + 1) + columna
            indices = (a, a + 1, a + columnas + 2, a + columnas + 1)
            puntos = [vertices[i] for i in indices]
            if not all(origen == destino for origen, destino in puntos):
                moviles.extend(((puntos[0], puntos[1], puntos[2]),
                                (puntos[0], puntos[2], puntos[3])))
    # Pintar la superficie completa como base sólida garantiza que ninguna
    # contracción de malla ni corte de cuadrícula deje huecos transparentes
    # que se verían como cuadros negros de fondo en ventanas compuestas.
    cr.save()
    cr.set_source_surface(superficie, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_BILINEAR)
    cr.paint()
    cr.restore()

    cr.save()
    # Sin antialias en los recortes compartidos: no aparecen costuras alfa.
    # La textura sí conserva su filtrado bilineal.
    cr.set_antialias(cairo.ANTIALIAS_NONE)
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
