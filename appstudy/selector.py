"""Qué contenido pedir hoy. Solo mira la base: aquí no se toca la red.

La regla cabe en una frase, y eso es a propósito: alimenta al mazo que menos
material tiene, y pídele lo que más fallas dentro de él. Si todavía no fallas
nada, pide por el nombre del mazo.

Separarlo de la descarga tiene un motivo práctico: toda la lógica interesante
queda en una función que se prueba con una base sintética y sin simular ni una
sola respuesta de red.
"""
from __future__ import annotations

import json
import time

from . import catalogo, extensiones

MINIMO_POR_NIVEL = 40      # por debajo de esto, un nivel se considera corto
MAX_TERMINOS = 3
NIVELES_POR_DEFECTO = ["Básico", "Intermedio", "Avanzado"]


def niveles(deck) -> list:
    """Los niveles del mazo. Se guardan como JSON en la columna `levels`."""
    try:
        valor = json.loads(deck["levels"] or "[]")
    except (TypeError, ValueError):
        valor = []
    return [str(n) for n in valor if str(n).strip()] or list(NIVELES_POR_DEFECTO)


def _mazo_mas_flojo(con):
    """El mazo con menos tarjetas. A igualdad, el que lleva más sin alimentarse."""
    return con.execute("""
        SELECT d.*, COUNT(c.id) AS cuantas,
               COALESCE((SELECT MAX(imported) FROM source_imports s
                          WHERE s.deck_id = d.id), 0) AS ultima
          FROM decks d LEFT JOIN cards c ON c.deck_id = d.id
         GROUP BY d.id
         ORDER BY cuantas ASC, ultima ASC, d.id ASC
         LIMIT 1""").fetchone()


def _terminos(con, deck) -> tuple:
    """Qué pedir, por qué, y de dónde ha salido: `fallos` o `mazo`."""
    filas = con.execute("""
        SELECT c.tags, s.lapses FROM cards c JOIN state s ON s.card_id = c.id
         WHERE c.deck_id = ? AND s.lapses > 0 AND c.tags <> ''
         ORDER BY s.lapses DESC LIMIT 20""", (deck["id"],)).fetchall()
    cuenta = {}
    for fila in filas:
        for etiqueta in (e.strip() for e in fila["tags"].split(",")):
            if etiqueta and etiqueta != "inversa":
                cuenta[etiqueta] = cuenta.get(etiqueta, 0) + fila["lapses"]
    if cuenta:
        mejores = sorted(cuenta, key=lambda e: (-cuenta[e], e))[:MAX_TERMINOS]
        return mejores, "porque fallas " + ", ".join(mejores), "fallos"
    return ([deck["name"]], f"para ampliar {deck['name']}, que va corto de material",
            "mazo")


def _nivel_por_llenar(con, deck) -> tuple:
    """El primer nivel que no llega al mínimo. Si todos llegan, el último."""
    lista = niveles(deck)
    for i, nombre in enumerate(lista, start=1):
        cuantas = con.execute("SELECT COUNT(*) c FROM cards WHERE deck_id=? AND level=?",
                              (deck["id"], i)).fetchone()["c"]
        if cuantas < MINIMO_POR_NIVEL:
            return nombre, i
    return lista[-1], len(lista)


def plan(con, ahora: float | None = None) -> dict | None:
    """Qué pedir, a quién y por qué. `None` si hoy no hay nada que pedir."""
    deck = _mazo_mas_flojo(con)
    if not deck:
        return None
    nivel, nivel_num = _nivel_por_llenar(con, deck)
    disponibles = [f for f in catalogo.fuentes_de(deck["key"], nivel)
                   if extensiones.habilitada(con, f["id"])]
    if not disponibles:
        return None
    terminos, motivo, origen = _terminos(con, deck)
    return {"deck": deck, "nivel": nivel, "nivel_num": nivel_num,
            "terminos": terminos, "fuentes": disponibles, "motivo": motivo,
            # De dónde salen los términos. Cuando es el nombre del mazo no se
            # puede medir relevancia: «Inglés» no aparece en un texto en inglés.
            "origen_terminos": origen, "ts": ahora or time.time()}
