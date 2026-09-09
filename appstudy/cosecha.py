"""Trae contenido nuevo y decide si vale la pena. El único módulo con red.

«Calidad» tiene que ser algo que el código pueda decidir, así que son siete
comprobaciones con un motivo legible cada una. El motivo se guarda también
cuando se rechaza: sin eso, «no me trae nada» sería indepurable.

Toda la red pasa por `fuentes.descargar`, que valida HTTPS, dominio en lista
blanca, cada redirección y el tamaño del cuerpo.
"""
from __future__ import annotations

import json
import re
import time

from . import catalogo, db, fuentes, selector

MIN_PALABRAS, MAX_PALABRAS = 400, 20000
MIN_PROSA = 0.35            # renglones que son frases, no entradas de un menú
MIN_RELEVANCIA = 0.20
UMBRAL = 0.5

# Palabras vacías: bastan para distinguir un idioma de otro sin dependencias.
# No hay que acertar siempre, solo no colar un texto en inglés en un mazo en
# español y al revés.
_ES = {"de", "la", "que", "el", "en", "y", "los", "se", "del", "las", "un", "por",
       "con", "una", "para", "es", "al", "lo", "como", "más", "o", "si", "su",
       "sus", "este", "esta", "son", "pero", "sobre", "entre", "cuando"}
_EN = {"the", "of", "and", "to", "in", "a", "is", "that", "for", "it", "as", "with",
       "on", "be", "by", "this", "are", "from", "or", "an", "which", "you", "at",
       "was", "were", "can", "has", "have", "its", "not", "but", "when"}


def idioma(texto: str) -> str:
    palabras = re.findall(r"[a-záéíóúñü]+", texto.lower())[:2000]
    if not palabras:
        return "?"
    return "es" if sum(p in _ES for p in palabras) >= sum(p in _EN for p in palabras) else "en"


def nivel_de(texto: str, cuantos: int = 3) -> int:
    """Frases largas y palabras largas.

    Es lo más parecido a «dificultad» que se puede medir sin entender el texto,
    y basta para colocar un capítulo en su nivel dentro del mazo.
    """
    frases = [f for f in re.split(r"[.!?]+", texto) if f.strip()]
    palabras = texto.split()
    if not frases or not palabras:
        return 1
    media = len(palabras) / len(frases)
    largas = sum(len(p) > 9 for p in palabras) / len(palabras)
    if media < 16 and largas < 0.14:
        return 1
    if media < 24 and largas < 0.22:
        return min(2, cuantos)
    return min(3, cuantos)


def _prosa(texto: str) -> float:
    renglones = [l.strip() for l in texto.splitlines() if l.strip()]
    if not renglones:
        return 0.0
    return sum(len(l.split()) >= 8 for l in renglones) / len(renglones)


RAIZ = 6      # letras que se comparan de cada palabra


def _relevancia(doc: dict, plan: dict) -> float:
    """Cuánto tiene que ver el documento con lo que se pidió.

    Se compara por raíz y no por palabra entera: en español «electricidad» y
    «eléctrica» son lo mismo para esto, y exigir la palabra exacta descartaría
    casi todo lo que de verdad sirve.
    """
    # Cuando el término es el nombre del mazo no hay nada que medir: la fuente
    # ya está elegida por mazo, y «Inglés» no sale en un texto en inglés.
    if plan.get("origen_terminos") != "fallos":
        return 1.0
    campo = fuentes.clave(doc["title"] + " " + doc.get("text", "")[:3000])
    partes = [p for t in plan["terminos"] for p in fuentes.clave(t).split() if len(p) > 3]
    if not partes:
        return 1.0
    return sum(p[:RAIZ] in campo for p in partes) / len(partes)


def filtrar(con, doc: dict, plan: dict) -> dict:
    """Si el documento entra, con qué nota y por qué. Nunca lanza."""
    def no(motivo, score=0.0):
        return {"ok": False, "score": score, "nivel": 1, "motivo": motivo}

    if not catalogo.abierta(doc["provider"]):
        return no("licencia: esta fuente solo permite el enlace, no el texto completo")
    texto = doc.get("text", "") or ""
    palabras = len(texto.split())
    if palabras < MIN_PALABRAS:
        return no(f"demasiado corto: {palabras} palabras")
    if palabras > MAX_PALABRAS:
        return no(f"demasiado largo: {palabras} palabras")
    titulo = fuentes.clave(doc.get("title", ""))
    if "desambiguacion" in titulo or "disambiguation" in titulo:
        return no("es una página de desambiguación, no un artículo")
    prosa = _prosa(texto)
    if prosa < MIN_PROSA:
        return no(f"no es prosa: solo el {prosa:.0%} de los renglones son frases")
    esperado = "en" if plan["deck"]["key"] == "ingles" else "es"
    if idioma(texto) != esperado:
        return no(f"idioma equivocado: se esperaba {esperado}")
    relevancia = _relevancia(doc, plan)
    if relevancia < MIN_RELEVANCIA:
        return no(f"poco que ver con {', '.join(plan['terminos'])}", round(relevancia, 3))
    if con.execute("SELECT 1 FROM source_imports WHERE fingerprint=? AND deck_id=?",
                   (fuentes.huella(doc), plan["deck"]["id"])).fetchone():
        return no("ya lo tienes importado en este mazo")
    if con.execute("SELECT 1 FROM inbox WHERE provider=? AND origin=? AND deck_id=?",
                   (doc["provider"], doc["origin"], plan["deck"]["id"])).fetchone():
        return no("ya está esperando en la bandeja")
    score = round(0.5 * min(1.0, relevancia * 2) + 0.3 * prosa +
                  0.2 * min(1.0, palabras / 1500), 3)
    return {"ok": score >= UMBRAL, "score": score,
            "nivel": nivel_de(texto, len(selector.niveles(plan["deck"]))),
            "motivo": plan["motivo"] if score >= UMBRAL else f"nota baja: {score}"}
