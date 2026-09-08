"""Plan diario explicable, calculado con lo que ya hay en la base.

El panel abre con una sola propuesta —«Hoy: 6 repasos, una lectura de 8 minutos»—
en vez de con cinco modos de estudio y que elijas tú. Para que se pueda confiar
en ella, va siempre acompañada de su razón, y esa razón sale de datos que se
pueden señalar: qué dejaste a medias, qué se te está atragantando y qué tema
estabas mirando.

No hay modelo ni aleatoriedad: con la misma base sale el mismo plan.
"""
import time

from . import db

# Topes de una sesión de arranque. Más repasos que esto ya no es «lo de hoy»,
# es la cola entera; y más de tres ejercicios cansa antes de haber leído nada.
MAX_REPASOS = 8
MAX_EJERCICIOS = 3

# A partir de esta dificultad FSRS (1 a 10) una tarjeta empieza a pesar en el
# cálculo: por debajo, la tarjeta se sostiene sola y no delata un tema flojo.
DIFICULTAD_NEUTRA = 5


def _etiquetas(texto) -> set:
    return {t.strip().lower() for t in (texto or "").split(",") if t.strip()}


def recomendar(con, deck_id=None, ahora=None) -> dict:
    """Qué conviene hacer ahora: capítulo, repasos y ejercicios, con su razón.

    `deck_id` es el tema que estabas mirando. Si no vale —vacío, o un mazo
    borrado o apagado— se usa el que elegiste en el asistente de bienvenida, y
    si tampoco, el primer mazo activo. Así el plan nunca sale vacío por no haber
    dicho todavía qué te interesa.
    """
    ahora = time.time() if ahora is None else ahora
    activos = {d["id"]: dict(d) for d in con.execute(
        "SELECT * FROM decks WHERE enabled=1")}
    if deck_id not in activos:
        principal = db.get_meta(con, "bienvenida_tema", "")
        deck_id = next((did for did, d in activos.items()
                        if d["key"] == principal), None)

    capitulos = [c for c in db.chapters(con) if c["deck_id"] in activos]
    lecturas = {r["chapter_id"]: dict(r) for r in con.execute("SELECT * FROM reading")}
    tarjetas = [dict(c) for c in con.execute(
        """SELECT c.*, s.reps, s.due, s.lapses, s.difficulty, s.leech
           FROM cards c JOIN state s ON s.card_id=c.id
           JOIN decks d ON d.id=c.deck_id WHERE d.enabled=1""")]
    ultima = max(capitulos, key=lambda c: lecturas.get(c["id"], {}).get("ts", 0),
                 default=None)

    def dificultad(cap) -> float:
        """Cuánto se atraganta lo que explica este capítulo.

        Suma los fallos y el exceso de dificultad de las tarjetas de su mismo
        nivel que compartan alguna etiqueta con él. Un capítulo sin etiquetas
        responde por todo su nivel.
        """
        etiquetas = _etiquetas(cap["tags"])
        return sum(t["lapses"] + max(0, t["difficulty"] - DIFICULTAD_NEUTRA)
                   for t in tarjetas
                   if t["deck_id"] == cap["deck_id"] and t["level"] == cap["level"]
                   and (not etiquetas or etiquetas & _etiquetas(t["tags"])))

    def prioridad(cap):
        """Orden de preferencia, de más a menos decisivo (mayor gana)."""
        leido = lecturas.get(cap["id"], {})
        del_ultimo_mazo = (ultima is not None
                           and lecturas.get(ultima["id"], {}).get("ts")
                           and cap["deck_id"] == ultima["deck_id"])
        return (cap["deck_id"] == deck_id,                  # el tema que mirabas
                bool(leido.get("avance")) and not cap["leido"],   # lo dejaste a medias
                leido.get("ts", 0) if not cap["leido"] else 0,    # lo más reciente
                bool(del_ultimo_mazo),                      # sigue por donde ibas
                dificultad(cap),                            # lo que se te resiste
                -cap["level"], -cap["pos"], -cap["id"])     # y de ahí, lo más básico

    pendientes = [c for c in capitulos if not c["leido"]]
    cap = max(pendientes, key=prioridad, default=None)
    if cap is None:
        # Todo leído: se repasa lo que peor se sostiene, no el primero que salga
        cap = max((c for c in capitulos if dificultad(c) > 0), key=prioridad,
                  default=None)

    did = (deck_id if deck_id in activos else
           cap["deck_id"] if cap else next(iter(activos), None))
    elegibles = [c for c in tarjetas if c["deck_id"] == did and not c["leech"]]
    repasos = min(MAX_REPASOS, sum(c["reps"] > 0 and c["due"] <= ahora
                                   for c in elegibles))
    ejercicios = min(MAX_EJERCICIOS, sum(bool(c["back"]) for c in tarjetas
                                         if c["deck_id"] == did))

    if cap and cap.get("avance") and not cap["leido"]:
        razon = "Retoma tu última lectura"
    elif cap and dificultad(cap):
        razon = "Refuerza las dificultades detectadas"
    else:
        razon = "Avanza en el tema elegido"

    partes = [f"{repasos} repasos"] if repasos else []
    if cap:
        partes.append(f"una lectura de {cap['minutes']} minutos")
    if ejercicios:
        partes.append(f"{ejercicios} ejercicios")
    texto = ("Hoy: " + ", ".join(partes) if partes
             else "Todo al día. Elige un tema para empezar.")

    return {"capitulo": cap, "repasos": repasos, "ejercicios": ejercicios,
            "deck": activos.get(did), "razon": razon, "texto": texto}
