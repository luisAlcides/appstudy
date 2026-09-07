"""Recuerdo libre: cierra el libro y suelta todo lo que te quede.

Es el ejercicio con más respaldo de todos los que hay en la aplicación, y el
único que no cubre ninguna tarjeta. Repasar leyendo engaña: reconoces lo que ya
viste y te parece que lo sabes. Aquí no hay nada delante, así que lo que sale es
lo que de verdad está, y lo que importa del resultado no es la nota sino la
lista de lo que te dejaste — que es exactamente lo que hay que volver a mirar.

El módulo reúne el material, contrasta y saca el informe. Ni escribe en la
pantalla ni escucha el micrófono: de eso se encargan `pet.py` y `main_window.py`.
"""
from . import db, ia, util

# Cuánto material se le enseña al modelo para contrastar. Con más, un modelo
# pequeño empieza a perder puntos por el camino y da por olvidado lo que sí
# dijiste.
MAX_TARJETAS = 14
MAX_CARACTERES = 2600


def material_de(con, deck_key: str | None = None, level: int | None = None,
                chapter_uid: str | None = None, limite: int = MAX_TARJETAS) -> list:
    """Las tarjetas que forman el tema del que te vas a examinar de memoria."""
    where = ["d.enabled=1"]
    args: list = []
    if deck_key:
        where.append("d.key=?")
        args.append(deck_key)
    if level:
        where.append("c.level=?")
        args.append(level)
    if chapter_uid:
        where.append("""c.id IN (SELECT card_id FROM card_sources
                                 WHERE chapter_uid=?)""")
        args.append(chapter_uid)
    filas = con.execute(
        f"""SELECT c.id, c.front, c.back, d.name AS deck_name, d.key AS deck_key
            FROM cards c JOIN decks d ON d.id=c.deck_id
            WHERE {' AND '.join(where)}
            ORDER BY c.level ASC, c.id ASC LIMIT ?""", (*args, max(1, limite))).fetchall()
    return [dict(f) for f in filas]


def texto_material(tarjetas: list) -> str:
    """El material en un bloque de texto, recortado a lo que el modelo maneja."""
    lineas = []
    total = 0
    for t in tarjetas:
        linea = f"- {util.plain(t['front'])} → {util.plain(t['back'])}"
        if total + len(linea) > MAX_CARACTERES:
            break
        lineas.append(linea)
        total += len(linea)
    return "\n".join(lineas)


def temas_disponibles(con, minimo: int = 4) -> list[dict]:
    """Mazos con material suficiente para un recuerdo libre que valga de algo."""
    filas = con.execute(
        """SELECT d.key, d.name, COUNT(c.id) AS cuantas
           FROM decks d JOIN cards c ON c.deck_id = d.id
           WHERE d.enabled=1 GROUP BY d.id HAVING cuantas >= ?
           ORDER BY cuantas DESC""", (max(1, minimo),)).fetchall()
    return [dict(f) for f in filas]


def evaluar(cfg_ia: dict, tarjetas: list, recordado: str) -> dict:
    """Contrasta lo recordado con el material y devuelve el informe.

    Sin IA no hay contraste posible que valga la pena: comparar palabras sueltas
    daría por olvidado lo que dijiste con otras palabras, que es justo lo que
    hace bien el recuerdo libre. En ese caso se dice claramente.
    """
    recordado = (recordado or "").strip()
    if not recordado:
        return {"nota": 0, "cubierto": [], "veredicto": "No has dicho nada todavía.",
                "falto": [util.plain(t["front"]) for t in tarjetas][:8], "sin_ia": False}
    if not (cfg_ia or {}).get("activa"):
        return {"nota": 0, "cubierto": [], "falto": [],
                "veredicto": "Necesito la IA local para contrastar lo que recordaste.",
                "sin_ia": True}
    try:
        informe = ia.evaluar_recuerdo(cfg_ia, texto_material(tarjetas), recordado)
    except Exception as e:
        return {"nota": 0, "cubierto": [], "falto": [], "sin_ia": True,
                "veredicto": f"No pude contrastarlo: {e}"}
    informe["nota"] = _nota_coherente(informe, texto_material(tarjetas), recordado)
    if informe["nota"] == 0 and not informe.get("cubierto"):
        informe["veredicto"] = "Eso no es de este tema; no he podido darte nada por bueno."
    informe["sin_ia"] = False
    return informe


# Palabras que aparecen en cualquier texto y no dicen de qué va: no sirven para
# saber si lo que recordaste tiene que ver con el material.
VACIAS = {
    "para", "porque", "cuando", "como", "donde", "sobre", "entre", "desde", "hasta",
    "este", "esta", "estos", "estas", "aquel", "puede", "pueden", "tiene", "tienen",
    "hacer", "hace", "haces", "siempre", "nunca", "menos", "sino", "pues", "acuerdo",
    "cosas", "cosa", "tema", "temas", "algo", "nada", "todo", "todos", "todas",
}


def _distintivas(texto: str) -> set:
    """Las palabras con contenido de un texto, para ver de qué habla."""
    import re
    palabras = re.findall(r"[a-záéíóúñü]{5,}", (texto or "").lower())
    return {p for p in palabras if p not in VACIAS}


def solape(material: str, recordado: str) -> float:
    """Qué parte de lo recordado usa el vocabulario del material, de 0 a 1.

    Es un apaño tosco a propósito: no mide si recordaste bien, solo si estabas
    hablando del tema. Un recuerdo de mecánica sobre material de estadística da
    casi cero por muy bien redactado que esté.
    """
    dichas = _distintivas(recordado)
    if not dichas:
        return 0.0
    return len(dichas & _distintivas(material)) / len(dichas)


# Por debajo de esto, lo recordado no habla del material ni de lejos.
SOLAPE_MINIMO = 0.10


def _nota_coherente(informe: dict, material: str = "", recordado: str = "") -> int:
    """Corrige la nota del modelo cuando se contradice a sí mismo.

    Un modelo pequeño puntúa por impresión y de dos maneras opuestas: le puso un
    65 a un recuerdo de otra asignatura, y dejó la lista de lo cubierto vacía
    mientras el veredicto decía que había recordado casi todo. Así que la nota se
    ata a dos señales, y ninguna se fía de lo que el modelo diga de sí mismo:
    si lo recordado ni siquiera usa el vocabulario del material, no hay nota; y
    si el modelo sí hizo el recuento, la nota no puede pasar de esa proporción.
    """
    nota = int(informe.get("nota", 0))
    if material and recordado and solape(material, recordado) < SOLAPE_MINIMO:
        return min(nota, 5)
    cubierto, falto = len(informe.get("cubierto", [])), len(informe.get("falto", []))
    if not cubierto:
        # Sin recuento no hay techo que aplicar: castigarlo aquí es castigar al
        # que sí recordó y al modelo que no rellenó la lista.
        return nota
    return min(nota, round(100 * cubierto / (cubierto + falto)))


def guardar(con, deck_key: str, informe: dict):
    """Apunta la nota del último recuerdo libre de cada tema."""
    import time
    historial = db.get_meta(con, "recuerdo_libre", "") or ""
    lineas = [l for l in historial.split("\n") if l.strip()][-19:]
    lineas.append(f"{int(time.time())}|{deck_key}|{int(informe.get('nota', 0))}")
    db.set_meta(con, "recuerdo_libre", "\n".join(lineas))


def historial(con) -> list[dict]:
    crudo = db.get_meta(con, "recuerdo_libre", "") or ""
    salida = []
    for linea in crudo.split("\n"):
        partes = linea.strip().split("|")
        if len(partes) != 3:
            continue
        try:
            salida.append({"ts": float(partes[0]), "deck_key": partes[1],
                           "nota": int(partes[2])})
        except ValueError:
            continue
    return salida
