"""Retos de la mascota: una misma tarjeta preguntada de varias maneras.

Aquí no hay nada de GTK, solo la lógica de convertir una tarjeta en un reto
concreto —opción múltiple, adivinar la pregunta, verdadero o falso, rellenar un
hueco, escribir la respuesta o contrarreloj— para poder probarla sin abrir
ninguna ventana.

El material de AppStudy tiene respuestas largas (un párrafo explicando), así
que las opciones no son la respuesta entera: se destila su esencia, que es lo
que cabe en el globo y lo que de verdad hay que reconocer.
"""
import difflib
import json
import random
import re
import unicodedata

from . import cloze, util

# Cuánto tiempo da cada formato, en segundos
SEGUNDOS = {"opciones": 22, "invertido": 22, "vf": 16, "hueco": 30,
            "escribir": 40, "relampago": 12, "caza_error": 26, "emparejar": 26}

# Icono y título con el que se presenta cada formato en el globo
TITULOS = {
    "opciones":   ("🎯", "Elige la buena"),
    "invertido":  ("🔄", "¿De qué hablo?"),
    "vf":         ("⚖️", "¿Verdadero o falso?"),
    "hueco":      ("🧩", "Rellena el hueco"),
    "escribir":   ("✍️", "Escríbelo tú"),
    "relampago":  ("⚡", "Contrarreloj"),
    "caza_error": ("🕵️", "Caza el error"),
    "emparejar":  ("🔗", "Empareja conceptos"),
}

# Cada cuánto sale cada formato.
PESOS = {"opciones": 4, "invertido": 2, "vf": 2, "hueco": 2,
         "escribir": 1, "relampago": 1, "caza_error": 3, "emparejar": 2}

MAX_OPCION = 92        # una opción más larga que esto no cabe en el globo
MAX_ESCRIBIR = 34      # a partir de aquí, escribir la respuesta entera es un castigo

# Palabras que no sirven para dejar un hueco: son de relleno o se adivinan solas
COMUNES = {
    "porque", "cuando", "entre", "sobre", "puede", "pueden", "hasta", "segun",
    "menos", "donde", "mismo", "misma", "estos", "estas", "aunque", "tambien",
    "siempre", "ejemplo", "decir", "hacer", "tiene", "tienen", "sirve", "suele",
    "cada", "para", "como", "toda", "todo", "todos", "todas", "otra", "otras",
    "mientras", "ademas", "luego", "antes", "despues", "manera", "forma", "parte",
}


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin puntuación: para comparar respuestas."""
    t = unicodedata.normalize("NFD", util.plain(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def parecido(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()


PARECIDO_MINIMO = 0.82
PARECIDO_ESTRICTO = 0.9


def acierta_escrito(escrito: str, respuesta: str, estricto: bool = False) -> bool:
    """¿Cuenta como acierto lo que ha escrito? Se perdona el acento y la errata.

    En modo estricto se cae la regla de «contenida en la otra»: escribir la
    mitad larga de una respuesta no es saberla, es reconocerla. Lo que se sigue
    perdonando son los acentos y las erratas, porque eso no es no saberlo.
    """
    e, r = normalizar(escrito), normalizar(respuesta)
    if not e or not r:
        return False
    if e == r:
        return True
    if not estricto and len(e) >= 0.6 * len(r) and (e in r or r in e):
        return True
    minimo = PARECIDO_ESTRICTO if estricto else PARECIDO_MINIMO
    return difflib.SequenceMatcher(None, e, r).ratio() >= minimo


# ------------------------------------------------------------------- destilar

_NUMERACION = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s*")
_SIGUIENTE = re.compile(r"\s\d+[.)]\s")     # el «2.» de una respuesta enumerada


def _primeras_lineas(texto: str, minimo: int) -> str:
    """Las primeras líneas con texto, hasta juntar algo con sentido."""
    junto = ""
    for linea in util.lines(texto):
        limpia = _NUMERACION.sub("", linea).strip()
        if not limpia:
            continue
        junto = f"{junto} {limpia}".strip()
        if len(junto) >= minimo:
            break
    return junto


def esencia(texto: str, maximo: int = MAX_OPCION) -> str:
    """La primera idea de una respuesta larga, cortada por donde no duele."""
    if cloze.tiene_huecos(texto):
        texto = cloze.completo(texto)
    t = _primeras_lineas(texto, 28)
    corta = _SIGUIENTE.search(t)
    if corta and corta.start() >= 16:
        # Una respuesta en pasos se queda en el primero: el resto no es una opción
        t = t[:corta.start()].strip()
    if len(t) <= maximo:
        return t
    corte = t[:maximo]
    for sep in (". ", "; ", ": ", ", "):
        i = corte.rfind(sep)
        if i >= maximo * 0.45:
            return corte[:i].strip()
    i = corte.rfind(" ")
    return (corte[:i] if i > 0 else corte).strip() + "…"


def primera_frase(texto: str, maximo: int = 120) -> str:
    """La frase con la que se puede dejar un hueco sin marear a nadie."""
    t = _primeras_lineas(texto, 40)
    m = re.search(r"(?<=[.;:])\s", t)
    if m and m.start() >= 25:
        t = t[:m.start()]
    return t[:maximo]


_TOKEN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{5,}|\d[\d.,]{1,}")


def hueco(texto: str):
    """Una frase con un hueco y la palabra que falta, o None si no da para tanto."""
    frase = primera_frase(texto)
    candidatos = [w for w in _TOKEN.findall(frase)
                  if normalizar(w) and normalizar(w) not in COMUNES]
    if not candidatos:
        return None
    elegida = random.choice(candidatos)
    return frase.replace(elegida, "_____", 1), elegida


# ---------------------------------------------------------------- distractores

def _candidatos(con, card, columna, n):
    """Textos de otras tarjetas del mismo mazo, ya destilados, que puedan colar."""
    correcta = esencia(card["back"] if columna == "back" else card["front"])
    filas = con.execute(
        f"""SELECT {columna} AS texto FROM cards
            WHERE deck_id=? AND id<>? AND TRIM({columna})<>''
            ORDER BY ABS(level - ?) ASC, RANDOM() LIMIT 90""",
        (card["deck_id"], card["id"], card["level"])).fetchall()
    vistas, salida = {normalizar(correcta)}, []
    for fila in filas:
        texto = esencia(fila["texto"])
        clave = normalizar(texto)
        if not clave or clave in vistas:
            continue
        # Ni un calco de la buena (podría ser igual de válida) ni de otro tamaño:
        # si la larga fuera siempre la correcta, el reto se adivinaría a ojo.
        if parecido(texto, correcta) > 0.80:
            continue
        if correcta and not 0.35 <= len(texto) / len(correcta) <= 2.8:
            continue
        vistas.add(clave)
        salida.append(texto)
        if len(salida) >= n:
            break
    return salida


def distractores(con, card, n=3) -> list:
    """Respuestas de otras tarjetas que puedan pasar por la buena."""
    return _candidatos(con, card, "back", n)


def _baraja(correcta, malas):
    opciones = [correcta, *malas]
    random.shuffle(opciones)
    return {"opciones": opciones, "correcta": opciones.index(correcta)}


def _opciones_propias(card):
    """Las opciones que ya trae la tarjeta, si es de tipo quiz."""
    if card["kind"] != "quiz" or not card["choices"]:
        return None
    try:
        opciones = [util.plain(o) for o in json.loads(card["choices"])]
    except (ValueError, TypeError):
        return None
    if len(opciones) < 2 or not 0 <= card["answer"] < len(opciones):
        return None
    return {"opciones": opciones, "correcta": card["answer"]}


# --------------------------------------------------------------------- armado

def es_cloze(card) -> bool:
    """¿Es una tarjeta de huecos escritos a mano?"""
    try:
        tipo = card["kind"]
        frente = card["front"]
    except (KeyError, IndexError, TypeError):
        return False
    return (tipo == "cloze" or cloze.tiene_huecos(frente)) and cloze.tiene_huecos(frente)


def preparar(con, card, evitar=None, estricto: bool = False) -> dict:
    """Convierte una tarjeta en un reto concreto, con formato elegido al azar.

    `evitar` es el formato de la vez anterior: mientras haya alternativas no se
    repite, que es de donde sale la sensación de variedad.

    En modo `estricto` se descarta el relámpago, que no comprueba nada: enseña
    la respuesta y te pregunta si la tenías. Cuando es el único formato posible
    —una respuesta demasiado larga para escribirla y sin compañeras de las que
    sacar opciones— el reto sale marcado `verificable: False`, y quien lo pida
    sabrá que eso no se puede dar por estudiado.
    """
    respuesta = util.plain(card["back"])
    posibles: dict = {}

    elegir = _opciones_propias(card)
    if elegir is None and respuesta:
        malas = distractores(con, card, 3)
        if len(malas) >= 2:
            elegir = _baraja(esencia(card["back"]), malas)

    if elegir:
        posibles["opciones"] = elegir
        # Verdadero o falso: se enseña la buena o una de las malas, a cara o cruz
        correcta = elegir["opciones"][elegir["correcta"]]
        falsa = next((o for o in elegir["opciones"] if o != correcta), None)
        verdadera = falsa is None or random.random() < 0.5
        posibles["vf"] = {"afirmacion": correcta if verdadera else falsa,
                          "verdadera": verdadera}

    # Al revés: se enseña la respuesta y hay que reconocer de qué iba la pregunta
    frentes = _candidatos(con, card, "front", 3)
    if respuesta and len(frentes) >= 2:
        posibles["invertido"] = {"pregunta": esencia(card["back"]),
                                 **_baraja(esencia(card["front"]), frentes)}

    if es_cloze(card):
        # La tarjeta dice qué se tapa: mejor eso que adivinar la palabra.
        texto = card["front"]
        indice = cloze.elegir(texto)
        palabra = cloze.respuesta(texto, indice)
        posibles["hueco"] = {"frase": util.plain(cloze.enmascarar(texto, indice)),
                             "palabra": palabra}
        if len(palabra) <= MAX_ESCRIBIR:
            posibles["escribir"] = {"respuesta_corta": palabra}
    else:
        con_hueco = hueco(card["back"]) if respuesta else None
        if con_hueco:
            posibles["hueco"] = {"frase": con_hueco[0], "palabra": con_hueco[1]}
        if respuesta and len(respuesta) <= MAX_ESCRIBIR and card["kind"] != "quiz":
            posibles["escribir"] = {}

    # Cazador de errores: 2 afirmaciones verdaderas y 1 trampa/error que hay que detectar
    if respuesta:
        malas_ce = distractores(con, card, 2)
        if malas_ce and len(malas_ce) >= 1:
            verdadera_1 = esencia(card["back"])
            card_dict = dict(card) if hasattr(card, "keys") else card
            hint_val = card_dict.get("hint") or ""
            deck_val = card_dict.get("deck_name") or "este tema"
            verdadera_2 = (f"Concepto clave de {deck_val}"
                           if not hint_val else esencia(hint_val))
            if verdadera_1 != verdadera_2 and normalizar(verdadera_1) != normalizar(malas_ce[0]):
                error_falso = malas_ce[0]
                opciones_ce = [verdadera_1, verdadera_2, error_falso]
                random.shuffle(opciones_ce)
                posibles["caza_error"] = {
                    "opciones": opciones_ce,
                    "correcta": opciones_ce.index(error_falso),
                    "error": error_falso,
                }

    # Emparejar: relaciona dos conceptos y sus definiciones
    filas_otra = con.execute(
        """SELECT front, back FROM cards
           WHERE deck_id=? AND id<>? AND TRIM(back)<>''
           ORDER BY RANDOM() LIMIT 1""", (card["deck_id"], card["id"])).fetchone()
    if respuesta and filas_otra and util.plain(filas_otra["back"]):
        c1_nom, c1_def = esencia(card["front"], 32), esencia(card["back"], 40)
        c2_nom, c2_def = esencia(filas_otra["front"], 32), esencia(filas_otra["back"], 40)
        if (c1_nom != c2_nom and c1_def != c2_def and
            normalizar(c1_nom) != normalizar(c2_nom) and
            normalizar(c1_def) != normalizar(c2_def)):
            buena = f"• {c1_nom} ➔ {c1_def}\n• {c2_nom} ➔ {c2_def}"
            cruzada = f"• {c1_nom} ➔ {c2_def}\n• {c2_nom} ➔ {c1_def}"
            ops_emp = [buena, cruzada]
            random.shuffle(ops_emp)
            posibles["emparejar"] = {
                "opciones": ops_emp,
                "correcta": ops_emp.index(buena),
                "pregunta": f"¿Cómo se relacionan «{c1_nom}» y «{c2_nom}»?",
            }

    # Pensar y comprobar siempre vale, aunque la tarjeta no dé para más
    posibles["relampago"] = {}

    comprobables = [f for f in posibles if f != "relampago"]
    disponibles = comprobables if (estricto and comprobables) else list(posibles)
    candidatos = [f for f in disponibles if f != evitar] or disponibles
    formato = random.choices(candidatos, [PESOS[f] for f in candidatos])[0]
    icono, titulo = TITULOS[formato]
    if es_cloze(card):
        # En una cloze la «respuesta» es el texto entero con lo tapado a la vista
        pregunta = util.plain(cloze.enmascarar(card["front"]))
        solucion = cloze.resaltado(card["front"])
        if card["back"]:
            solucion += "\n\n" + card["back"]
    else:
        pregunta, solucion = card["front"], card["back"] or ""
    return {"formato": formato, "segundos": SEGUNDOS[formato], "icono": icono,
            "titulo": titulo, "pregunta": pregunta, "respuesta": solucion,
            "verificable": formato != "relampago", **posibles[formato]}
