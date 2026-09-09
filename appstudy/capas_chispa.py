"""Convierte el atlas de Chispa en capas, y reconstruye lo que tapan.

Chispa es una ilustración renderizada: manos, pies, boca y ojos son píxeles
cocidos dentro de cada celda. Eso tiene un techo que se alcanza al intentar
hacerla parpadear —detrás del ojo no hay nada, así que un párpado solo puede
taparlo, no cerrarlo—. Este módulo rompe ese techo: separa cada pieza y rellena
el hueco que deja, de modo que al cerrar el ojo aparezca pelaje de verdad.

Las piezas se **buscan**, no se estiman. La paleta de Chispa está muy separada,
así que cada píxel se clasifica contra ella y los grupos conexos se asignan por
color, tamaño y posición. Un intento anterior situaba las elipses a ojo y una
quedó 22 píxeles desviada.

No se ejecuta al dibujar: produce archivos.
"""
from __future__ import annotations

# Los mismos colores que declara `chispa.py`, más los del ojo y la lengua, que
# allí no hacían falta porque venían pintados en la ilustración.
PALETA = {
    "naranja":  ((0xFB, 0xA8, 0x5E), (0xF0, 0x87, 0x3A), (0xD3, 0x66, 0x1F)),
    "crema":    ((0xFB, 0xF3, 0xE6), (0xEE, 0xDC, 0xC4)),
    "pardo":    ((0x5C, 0x40, 0x30), (0x48, 0x32, 0x24), (0x33, 0x22, 0x18)),
    "turquesa": ((0x3F, 0xD0, 0xC9),),
    # Blanco de la esclerótica, marrón del iris y casi negro de la pupila
    "ojo":      ((0xFF, 0xFF, 0xFF), (0x8B, 0x5A, 0x2B), (0x20, 0x14, 0x0C)),
    "lengua":   ((0xE2, 0x7D, 0x6D),),
}


def clasificar(r: int, g: int, b: int) -> str:
    """A qué color de la paleta se parece más. Nunca falla: siempre hay uno."""
    mejor, cerca = "naranja", None
    for nombre, referencias in PALETA.items():
        for R, G, B in referencias:
            d = (r - R) ** 2 + (g - G) ** 2 + (b - B) ** 2
            if cerca is None or d < cerca:
                cerca, mejor = d, nombre
    return mejor


MIN_ALFA = 128          # por debajo de esto es borde, y el color no es fiable


def mapa(superficie) -> tuple:
    """Clasifica la celda entera. Devuelve (colores, ancho, alto).

    `colores` es una lista con el nombre del color de cada píxel, o `None` si
    es transparente. Cairo guarda ARGB32 premultiplicado, así que hay que
    dividir por el alfa antes de comparar: sin eso, todo lo semitransparente
    se clasificaría como un color oscuro.
    """
    superficie.flush()
    datos = superficie.get_data()
    ancho, alto = superficie.get_width(), superficie.get_height()
    paso = superficie.get_stride()
    salida = [None] * (ancho * alto)
    for y in range(alto):
        fila = y * paso
        base = y * ancho
        for x in range(ancho):
            i = fila + x * 4
            a = datos[i + 3]
            if a < MIN_ALFA:
                continue
            salida[base + x] = clasificar(min(255, datos[i + 2] * 255 // a),
                                          min(255, datos[i + 1] * 255 // a),
                                          min(255, datos[i] * 255 // a))
    return salida, ancho, alto


def grupos(superficie, colores, minimo: int = 200, colores_mapa=None) -> list:
    """Los grupos conexos de esos colores, de mayor a menor.

    `colores_mapa` permite reutilizar una clasificación ya hecha: recorrer una
    celda de 512×512 cuesta, y las piezas se buscan varias veces sobre la misma.
    """
    if colores_mapa is None:
        colores_mapa, ancho, alto = mapa(superficie)
    else:
        colores_mapa, ancho, alto = colores_mapa
    vistos = bytearray(ancho * alto)
    salida = []
    for inicio in range(ancho * alto):
        if vistos[inicio] or colores_mapa[inicio] not in colores:
            continue
        color = colores_mapa[inicio]
        pila, pixeles = [inicio], set()
        vistos[inicio] = 1
        x0 = x1 = inicio % ancho
        y0 = y1 = inicio // ancho
        while pila:
            i = pila.pop()
            pixeles.add(i)
            y, x = divmod(i, ancho)
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < ancho and 0 <= yy < alto:
                        j = yy * ancho + xx
                        if not vistos[j] and colores_mapa[j] == color:
                            vistos[j] = 1
                            pila.append(j)
        if len(pixeles) >= minimo:
            salida.append({
                "color": color, "pixeles": pixeles, "n": len(pixeles),
                "caja": (x0 / ancho, y0 / alto, (x1 + 1) / ancho, (y1 + 1) / alto),
                "centro": ((x0 + x1 + 1) / 2 / ancho, (y0 + y1 + 1) / 2 / alto),
            })
    salida.sort(key=lambda g: -g["n"])
    return salida
