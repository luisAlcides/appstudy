"""Tarjetas de huecos («cloze») escritas a mano en el JSON.

El reto «Rellena el hueco» que se inventa la mascota elige la palabra por su
cuenta, y a veces se equivoca de palabra: tapa un adjetivo cuando lo que hay que
saber es el número. Una tarjeta cloze dice **tú** qué se tapa, marcándolo entre
dobles llaves:

    El comando {{chmod}} cambia los permisos, y {{chown}} el dueño.

De ahí salen dos huecos numerados. Cada vez que la tarjeta aparece se tapa uno,
o todos a la vez si lo pides. Se puede dar una pista por hueco con una barra
vertical: `{{755::en octal}}` tapa «755» y ofrece «en octal» como ayuda.

Aquí no hay ni base de datos ni interfaz: solo el análisis del texto.
"""
import re

# {{respuesta}} o {{respuesta::pista}}
MARCA = re.compile(r"\{\{(.+?)\}\}", re.S)
SEPARADOR = "::"

HUECO = "＿＿＿＿"          # ancho completo: se distingue de un guion bajo del texto


def tiene_huecos(texto: str) -> bool:
    return bool(texto) and MARCA.search(texto) is not None


def _partes(texto: str):
    """Trocea el texto en literales y huecos, conservando el orden."""
    piezas, pos, n = [], 0, 0
    for m in MARCA.finditer(texto or ""):
        if m.start() > pos:
            piezas.append({"tipo": "texto", "valor": texto[pos:m.start()]})
        cuerpo = m.group(1)
        respuesta, _, pista = cuerpo.partition(SEPARADOR)
        piezas.append({"tipo": "hueco", "indice": n,
                       "valor": respuesta.strip(), "pista": pista.strip()})
        n += 1
        pos = m.end()
    if pos < len(texto or ""):
        piezas.append({"tipo": "texto", "valor": texto[pos:]})
    return piezas


def huecos(texto: str) -> list[dict]:
    """Los huecos de la tarjeta, en orden: respuesta e (opcional) pista."""
    return [p for p in _partes(texto) if p["tipo"] == "hueco"]


def cuantos(texto: str) -> int:
    return len(huecos(texto))


def completo(texto: str) -> str:
    """El texto con todas las respuestas puestas: es lo que se enseña al final."""
    return "".join(p["valor"] for p in _partes(texto))


def resaltado(texto: str, indice: int | None = None, etiqueta: str = "b") -> str:
    """El texto completo con la respuesta marcada, para enseñarla al revelar."""
    salida = []
    for p in _partes(texto):
        if p["tipo"] == "hueco" and (indice is None or p["indice"] == indice):
            salida.append(f"<{etiqueta}>{p['valor']}</{etiqueta}>")
        else:
            salida.append(p["valor"])
    return "".join(salida)


def enmascarar(texto: str, indice: int | None = None) -> str:
    """El texto con un hueco tapado (o todos, si `indice` es None).

    Si el hueco trae pista, se enseña entre paréntesis: es lo que distingue un
    hueco resoluble de una adivinanza.
    """
    salida = []
    for p in _partes(texto):
        if p["tipo"] == "texto":
            salida.append(p["valor"])
        elif indice is None or p["indice"] == indice:
            salida.append(HUECO + (f" ({p['pista']})" if p["pista"] else ""))
        else:
            salida.append(p["valor"])
    return "".join(salida)


def respuesta(texto: str, indice: int | None = None) -> str:
    """Lo que hay que decir: un hueco concreto, o todos separados por comas."""
    encontrados = huecos(texto)
    if not encontrados:
        return ""
    if indice is None:
        return " · ".join(h["valor"] for h in encontrados)
    for h in encontrados:
        if h["indice"] == indice:
            return h["valor"]
    return ""


def pista(texto: str, indice: int | None = None) -> str:
    for h in huecos(texto):
        if indice is None or h["indice"] == indice:
            if h["pista"]:
                return h["pista"]
    return ""


def elegir(texto: str, evitar: int | None = None) -> int | None:
    """Qué hueco tapar esta vez, sin repetir el de la vez anterior."""
    import random
    encontrados = huecos(texto)
    if not encontrados:
        return None
    candidatos = [h["indice"] for h in encontrados if h["indice"] != evitar]
    return random.choice(candidatos or [h["indice"] for h in encontrados])
