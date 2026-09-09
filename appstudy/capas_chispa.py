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

import hashlib
import json
from pathlib import Path

import cairo

# Los mismos colores que declara `chispa.py`, más los del ojo y la lengua, que
# allí no hacían falta porque venían pintados en la ilustración.
PALETA = {
    "naranja":  ((0xFB, 0xA8, 0x5E), (0xF0, 0x87, 0x3A), (0xD3, 0x66, 0x1F)),
    "crema":    ((0xFB, 0xF3, 0xE6), (0xEE, 0xDC, 0xC4)),
    "pardo":    ((0x5C, 0x40, 0x30), (0x48, 0x32, 0x24), (0x33, 0x22, 0x18)),
    "turquesa": ((0x3F, 0xD0, 0xC9),),
    # Blanco de la esclerótica, marrón del iris y casi negro de la pupila.
    # No es una clase limpia: el naranja muy oscuro del pelaje se parece al
    # iris, y los brillos del pelo al blanco. Sirve para encontrar manchas
    # grandes y conexas —que es para lo que se usa—, no para contar píxeles.
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


# Reglas para reconocer las piezas de la cara. Salen de medir los grupos reales
# del atlas, no de suponer dónde están.
OJO_MIN = 600
OJO_ALTURA = (0.28, 0.62)      # ni las orejas (arriba) ni el pecho (abajo)
OJO_PROPORCION = (0.60, 1.60)  # un ojo es casi cuadrado; una oreja, ancha
OJO_SEPARACION = 0.08          # dos ojos no se solapan en horizontal
SIN_OJOS = (3, 5)              # ya vienen dibujadas con los ojos cerrados

# --- extremidades ---------------------------------------------------------
#
# Chispa no tiene brazos: tiene manos pegadas a un cuerpo redondo. Por eso el
# giro va topado —a partir de unos 15 grados la mano se despega y se ve el
# truco— y por eso una pieza que no se distinga limpiamente no se anima.
MIEMBRO_MIN, MIEMBRO_MAX = 600, 4000   # más de esto es varias piezas fundidas
OREJA_PROPORCION = 0.70        # las puntas de oreja son altas y estrechas
OREJA_ARRIBA = 0.30
MANO_ALTURA = (0.42, 0.82)     # por debajo de los ojos y por encima de los pies
PIE_ALTURA = 0.82
SIN_MIEMBROS = (5,)            # dormida y hecha un ovillo: no hay nada que girar
MIEMBROS_PAREJOS = 0.20        # dos manos van más o menos a la misma altura

# La boca queda fuera, y conviene saber por qué antes de volver a intentarlo:
# el rosa de la lengua es casi el mismo que el sombreado rosado del cuello, y
# el negro de la cavidad es el mismo que el de la pupila. Con esta paleta, los
# grupos que salen son pelaje, no boca. Hace falta otro anclaje —la cavidad
# oscura rodeada de crema— y eso toca la clasificación del ojo, que sí funciona.


def _proporcion(grupo) -> float:
    x0, y0, x1, y1 = grupo["caja"]
    alto = max(1e-6, y1 - y0)
    return (x1 - x0) / alto


def piezas(superficie, indice: int) -> dict:
    """Las piezas de la cara de esa celda, como conjuntos de píxeles.

    Devuelve `ojo_izq` y `ojo_der` cuando los encuentra. Una
    pose que no dé dos ojos no parpadea: es preferible que no parpadee a que
    parpadee una oreja.
    """
    clasificado = mapa(superficie)
    salida = {}
    if indice not in SIN_OJOS:
        candidatos = [g for g in grupos(superficie, {"ojo"}, OJO_MIN, clasificado)
                      if OJO_ALTURA[0] < g["centro"][1] < OJO_ALTURA[1]
                      and OJO_PROPORCION[0] <= _proporcion(g) <= OJO_PROPORCION[1]]
        if len(candidatos) >= 2:
            uno, otro = sorted(candidatos[:2], key=lambda g: g["centro"][0])
            if otro["centro"][0] - uno["centro"][0] >= OJO_SEPARACION:
                salida["ojo_izq"] = uno["pixeles"]
                salida["ojo_der"] = otro["pixeles"]
    salida.update(_miembros(superficie, indice, clasificado))
    return salida


def _miembros(superficie, indice, clasificado) -> dict:
    """Manos y pies, cuando se distinguen sin lugar a dudas.

    Las puntas de las orejas también son pardas: se descartan por altas y
    estrechas. Las poses sentadas funden brazos y piernas en una sola mancha, y
    esas se dejan como están: es preferible que una pose no mueva las manos a
    que mueva medio cuerpo.
    """
    if indice in SIN_MIEMBROS:
        return {}
    manos, pies = [], []
    for g in grupos(superficie, {"pardo"}, MIEMBRO_MIN, clasificado):
        if g["n"] > MIEMBRO_MAX:
            continue                       # varias piezas pegadas
        cy = g["centro"][1]
        if _proporcion(g) <= OREJA_PROPORCION and g["caja"][1] <= OREJA_ARRIBA:
            continue                       # punta de oreja
        if cy >= PIE_ALTURA:
            pies.append(g)
        elif MANO_ALTURA[0] <= cy < MANO_ALTURA[1]:
            manos.append(g)
    salida = {}
    for nombre, encontrados in (("mano", manos), ("pie", pies)):
        if len(encontrados) != 2:
            continue                       # o dos, o ninguno
        uno, otro = sorted(encontrados, key=lambda g: g["centro"][0])
        if abs(uno["centro"][1] - otro["centro"][1]) > MIEMBROS_PAREJOS:
            continue
        salida[f"{nombre}_izq"] = uno["pixeles"]
        salida[f"{nombre}_der"] = otro["pixeles"]
    return salida


def caja_de(superficie, pixeles) -> tuple:
    """La caja que ocupa un conjunto de píxeles, en fracciones de la celda."""
    ancho, alto = superficie.get_width(), superficie.get_height()
    xs = [i % ancho for i in pixeles]
    ys = [i // ancho for i in pixeles]
    return (min(xs) / ancho, min(ys) / alto,
            (max(xs) + 1) / ancho, (max(ys) + 1) / alto)


VERSION = "1"
VUELTAS_RELLENO = 400
SUAVIZADOS = 2


def _dilatar(pixeles, ancho, alto, veces=2):
    """Ensancha la máscara: el borde de una pieza arrastra medio píxel de ella."""
    actual = set(pixeles)
    for _ in range(veces):
        nuevo = set(actual)
        for i in actual:
            y, x = divmod(i, ancho)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < ancho and 0 <= yy < alto:
                        nuevo.add(yy * ancho + xx)
        actual = nuevo
    return actual


def reconstruir(superficie, pixeles):
    """La celda sin esa pieza, con el hueco relleno por difusión desde el borde.

    Cada píxel del hueco toma la media de los vecinos ya válidos, y el frente
    avanza hacia dentro. Es lo que hace que detrás del ojo aparezca pelaje y no
    un parche: el relleno sale del pelaje que lo rodea.
    """
    ancho, alto = superficie.get_width(), superficie.get_height()
    paso = superficie.get_stride()
    superficie.flush()
    datos = bytearray(superficie.get_data())
    zona = _dilatar(pixeles, ancho, alto)
    hueco = bytearray(ancho * alto)
    for i in zona:
        hueco[i] = 1
    pendientes = set(zona)
    for _ in range(VUELTAS_RELLENO):
        if not pendientes:
            break
        hechos = []
        for i in sorted(pendientes):
            y, x = divmod(i, ancho)
            acumulado = [0, 0, 0, 0]
            n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < ancho and 0 <= yy < alto and not hueco[yy * ancho + xx]:
                        j = yy * paso + xx * 4
                        for c in range(4):
                            acumulado[c] += datos[j + c]
                        n += 1
            if n:
                j = y * paso + x * 4
                for c in range(4):
                    datos[j + c] = acumulado[c] // n
                hechos.append(i)
        if not hechos:
            break
        for i in hechos:
            hueco[i] = 0
            pendientes.discard(i)
    for _ in range(SUAVIZADOS):
        copia = bytes(datos)
        for i in zona:
            y, x = divmod(i, ancho)
            acumulado = [0, 0, 0, 0]
            n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < ancho and 0 <= yy < alto:
                        j = yy * paso + xx * 4
                        for c in range(4):
                            acumulado[c] += copia[j + c]
                        n += 1
            j = y * paso + x * 4
            for c in range(4):
                datos[j + c] = acumulado[c] // n
    salida = cairo.ImageSurface.create_for_data(datos, cairo.FORMAT_ARGB32,
                                                ancho, alto, paso)
    salida.mark_dirty()
    return salida


def recortar(superficie, pixeles):
    """Solo esa pieza, con el resto transparente."""
    ancho, alto = superficie.get_width(), superficie.get_height()
    paso = superficie.get_stride()
    superficie.flush()
    origen = superficie.get_data()
    salida = cairo.ImageSurface(cairo.FORMAT_ARGB32, ancho, alto)
    destino = salida.get_data()
    for i in pixeles:
        y, x = divmod(i, ancho)
        j = y * paso + x * 4
        k = y * salida.get_stride() + x * 4
        for c in range(4):
            destino[k + c] = origen[j + c]
    salida.mark_dirty()
    return salida


def contar_color(superficie, pixeles, color: str) -> int:
    """Cuántos de esos píxeles se clasifican como ese color. Medible, no a ojo."""
    clasificado, ancho, _ = mapa(superficie)
    return sum(1 for i in pixeles if clasificado[i] == color)


def carpeta() -> Path:
    from . import db
    return db.DATA_DIR / "chispa" / "capas"


def huella_atlas() -> str:
    """Si el atlas cambia, las capas dejan de valer y hay que rehacerlas."""
    from .chispa import ATLAS
    try:
        return hashlib.sha256(ATLAS.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def extraer(destino: Path | None = None) -> dict | None:
    """Genera todas las capas y su manifiesto. Devuelve el manifiesto, o None.

    Lento a propósito: se hace una vez, en segundo plano, no al dibujar.
    """
    from .chispa import cargar_poses
    poses = cargar_poses()
    if poses is None:
        return None
    destino = destino or carpeta()
    destino.mkdir(parents=True, exist_ok=True)
    manifiesto = {"version": VERSION, "atlas": huella_atlas(), "poses": {}}
    for indice, celda in enumerate(poses):
        encontradas = piezas(celda, indice)
        todos = set().union(*encontradas.values()) if encontradas else set()
        base = reconstruir(celda, todos) if todos else celda
        base.write_to_png(str(destino / f"base-{indice}.png"))
        detalle = {}
        for nombre, pixeles in encontradas.items():
            recortar(celda, pixeles).write_to_png(
                str(destino / f"{indice}-{nombre}.png"))
            x0, y0, x1, y1 = caja_de(celda, pixeles)
            detalle[nombre] = {"caja": [x0, y0, x1, y1],
                               "centro": [(x0 + x1) / 2, (y0 + y1) / 2],
                               # El punto de giro no se usa en esta fase: ni el
                               # ojo ni la boca giran. Lo necesitarán los brazos.
                               "pivote": [(x0 + x1) / 2, y0]}
        manifiesto["poses"][str(indice)] = detalle
    (destino / "manifiesto.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifiesto
