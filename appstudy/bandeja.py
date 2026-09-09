"""La cola de lo que ha llegado solo y espera tu visto bueno.

Nada entra a un mazo sin pasar por aquí. Aceptar reutiliza
`fuentes.importar()`, que ya conserva la identidad y el progreso al reimportar
y añade al pie el bloque de atribución con origen, autor y licencia.
"""
from __future__ import annotations

import json
import time

from . import db, fuentes


def guardar(con, doc: dict, plan: dict, veredicto: dict) -> int:
    """Deja un documento esperando. Si ya estaba, no lo duplica."""
    deck_id = plan["deck"]["id"]
    con.execute("""
        INSERT INTO inbox(provider,origin,deck_id,title,summary,text,author,license,
                          score,nivel,motivo,cards,estado,created)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'pendiente',?)
        ON CONFLICT(provider,origin,deck_id) DO NOTHING""",
        (doc["provider"], doc["origin"], deck_id, doc["title"], doc.get("summary", ""),
         doc.get("text", ""), doc.get("author", ""), doc.get("license", ""),
         veredicto.get("score", 0), veredicto.get("nivel", 1), veredicto.get("motivo", ""),
         json.dumps(doc.get("cards", []), ensure_ascii=False), time.time()))
    con.commit()
    return con.execute("SELECT id FROM inbox WHERE provider=? AND origin=? AND deck_id=?",
                       (doc["provider"], doc["origin"], deck_id)).fetchone()["id"]


def pendientes(con) -> list:
    """Lo mejor primero: quien abre la bandeja con prisa ve antes lo que vale."""
    return con.execute("""
        SELECT i.*, d.name AS deck_name, d.key AS deck_key
          FROM inbox i JOIN decks d ON d.id = i.deck_id
         WHERE i.estado = 'pendiente'
         ORDER BY i.score DESC, i.created DESC""").fetchall()


def cuantas(con) -> int:
    return con.execute(
        "SELECT COUNT(*) c FROM inbox WHERE estado='pendiente'").fetchone()["c"]


def descartar(con, inbox_id: int) -> None:
    """Se marca, no se borra: así mañana no se vuelve a proponer lo mismo."""
    con.execute("UPDATE inbox SET estado='descartado' WHERE id=?", (inbox_id,))
    con.commit()


def aceptar(con, inbox_id: int, cards=None):
    """Crea el capítulo y las tarjetas elegidas.

    `cards` son los índices de las tarjetas propuestas que se aceptan; `None`
    las acepta todas.
    """
    fila = con.execute("SELECT * FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    if not fila:
        raise fuentes.FuenteError("Ese elemento ya no está en la bandeja")
    deck = con.execute("SELECT * FROM decks WHERE id=?", (fila["deck_id"],)).fetchone()
    item = {"provider": fila["provider"], "origin": fila["origin"], "title": fila["title"],
            "text": fila["text"], "author": fila["author"], "license": fila["license"],
            "retrieved": fila["created"]}
    capitulo = fuentes.importar(con, item, deck, commit=False)
    # `importar` no sabe de niveles: el que dedujo el filtro se aplica aquí
    con.execute("UPDATE chapters SET level=? WHERE id=?", (fila["nivel"], capitulo["id"]))
    propuestas = json.loads(fila["cards"] or "[]")
    elegidas = (propuestas if cards is None else
                [propuestas[i] for i in cards if 0 <= i < len(propuestas)])
    for t in elegidas:
        card_id, _ = db.add_card(con, deck["id"], deck["key"], "card", t["front"],
                                 t.get("back", ""), tags=f"fuente-{fila['provider']}",
                                 level=fila["nivel"])
        db.set_card_source(con, card_id, {"kind": "chapter", "chapter_uid": capitulo["uid"],
                                          "title": capitulo["title"]})
    con.execute("UPDATE inbox SET estado='aceptado' WHERE id=?", (inbox_id,))
    con.commit()
    return db.chapter_by_id(con, capitulo["id"])
