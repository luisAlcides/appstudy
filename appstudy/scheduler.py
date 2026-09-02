"""Repetición espaciada con FSRS, y selección de la próxima tarjeta.

Las fórmulas están en `fsrs.py`; aquí se aplican a una tarjeta concreta, se
guarda el resultado y se decide qué toca estudiar ahora.

Lo que cambia respecto al SM-2 de antes: ya no hay un «factor de facilidad» que
sube y baja a ojo, sino una **estabilidad** en días (cuánto aguanta el recuerdo)
y una **dificultad** de 1 a 10. El intervalo sale de preguntarle al modelo qué
día tu probabilidad de acordarte cae hasta la **retención objetivo**, que eliges
tú en Ajustes. Con la misma retención, salen bastantes menos repasos.

Se conserva un peldaño corto de diez minutos para lo que fallas: FSRS diría casi
diez horas, y una tarjeta que acabas de fallar hay que volver a verla hoy.
"""
import json
import random
import time

from . import fsrs

DAY = 86400.0

# Calificaciones
AGAIN, HARD, GOOD, EASY = 0, 1, 2, 3
RATING_LABELS = {AGAIN: "Otra vez", HARD: "Difícil", GOOD: "Bien", EASY: "Fácil"}

# Lo que fallas vuelve hoy mismo, no dentro de medio día
PASO_CORTO = 10 / 1440

RETENCION_POR_DEFECTO = 0.90
MAX_INTERVALO = 365.0

# Fallos seguidos a partir de los cuales una tarjeta es una «sanguijuela»: te
# come el tiempo y no se queda. Se aparta para que la reescribas o la partas.
UMBRAL_SANGUIJUELA = 8

# El estado de una tarjeta que nunca se ha visto
NUEVA = {"due": 0.0, "interval": 0.0, "ease": 2.5, "reps": 0, "lapses": 0,
         "last": 0.0, "stability": 0.0, "difficulty": 0.0}


def config(con) -> dict:
    """Retención objetivo, pesos y umbral de sanguijuela, tal como los tengas."""
    from . import db
    try:
        retencion = float(db.get_meta(con, "retencion", RETENCION_POR_DEFECTO))
    except (TypeError, ValueError):
        retencion = RETENCION_POR_DEFECTO
    pesos = fsrs.W_POR_DEFECTO
    crudo = db.get_meta(con, "fsrs_w", "")
    if crudo:
        try:
            leidos = tuple(float(x) for x in json.loads(crudo))
            if len(leidos) == len(fsrs.W_POR_DEFECTO):
                pesos = leidos
        except (ValueError, TypeError):
            pass
    try:
        umbral = int(db.get_meta(con, "umbral_sanguijuela", UMBRAL_SANGUIJUELA))
    except (TypeError, ValueError):
        umbral = UMBRAL_SANGUIJUELA
    return {"retencion": min(max(retencion, 0.70), 0.99), "w": pesos,
            "umbral": max(0, umbral)}


def review(state: dict, rating: int, ahora: float | None = None,
           retencion: float = RETENCION_POR_DEFECTO, w=fsrs.W_POR_DEFECTO) -> dict:
    """Devuelve el estado nuevo tras calificar. Función pura, sin base de datos.

    `ahora` permite rehacer el pasado (es lo que usa el deshacer, que reproduce
    los repasos que quedan con sus fechas de verdad).
    """
    ahora = time.time() if ahora is None else ahora
    rating = min(max(int(rating), AGAIN), EASY)
    reps = int(state.get("reps") or 0)
    lapses = int(state.get("lapses") or 0)
    estabilidad = float(state.get("stability") or 0.0)
    dificultad = float(state.get("difficulty") or 0.0)
    ultimo = float(state.get("last") or 0.0)

    if reps == 0 or estabilidad <= 0 or dificultad <= 0:
        # Primer contacto: la estabilidad y la dificultad salen de la nota
        estabilidad = fsrs.estabilidad_inicial(rating, w)
        dificultad = fsrs.dificultad_inicial(rating, w)
        recordado = None
    else:
        dias = max(0.0, (ahora - ultimo) / DAY) if ultimo else 0.0
        recordado = fsrs.recuperabilidad(dias, estabilidad)
        dificultad = fsrs.siguiente_dificultad(dificultad, rating, w)
        if dias < 1.0:
            # Volver a verla el mismo día consolida, pero no cuenta como repaso
            estabilidad = fsrs.estabilidad_mismo_dia(estabilidad, rating, w)
        elif rating == AGAIN:
            estabilidad = fsrs.estabilidad_tras_fallo(dificultad, estabilidad, recordado, w)
        else:
            estabilidad = fsrs.estabilidad_tras_acierto(dificultad, estabilidad,
                                                        recordado, rating, w)

    if rating == AGAIN:
        lapses += 1
        reps = 0                       # vuelve a la fase corta
        programado = PASO_CORTO
    else:
        reps += 1
        programado = max(fsrs.intervalo(estabilidad, retencion), PASO_CORTO)

    programado = min(programado, MAX_INTERVALO)
    # Pequeño ruido para que los repasos no se acumulen todos el mismo día
    ruido = 1.0 + random.uniform(-0.05, 0.05) if programado >= 1 else 1.0
    return {
        "due": ahora + programado * ruido * DAY,
        "interval": programado,
        "stability": estabilidad,
        "difficulty": dificultad,
        # Se sigue guardando un «factor de facilidad» equivalente para que las
        # bases y las vistas antiguas no se queden con un hueco.
        "ease": round(3.0 - (dificultad - 1) * (3.0 - 1.3) / 9, 4),
        "reps": reps,
        "lapses": lapses,
        "last": ahora,
        "recordado": recordado,        # informativo: qué probabilidad había
    }


_COLUMNAS = ("due", "interval", "ease", "reps", "lapses", "last",
             "stability", "difficulty")


def _guardar(con, card_id: int, st: dict):
    datos = {k: st[k] for k in _COLUMNAS}
    con.execute(
        """INSERT INTO state(card_id,due,interval,ease,reps,lapses,last,stability,difficulty)
           VALUES(:cid,:due,:interval,:ease,:reps,:lapses,:last,:stability,:difficulty)
           ON CONFLICT(card_id) DO UPDATE SET
               due=:due, interval=:interval, ease=:ease, reps=:reps, lapses=:lapses,
               last=:last, stability=:stability, difficulty=:difficulty""",
        {"cid": card_id, **datos})


def apply_review(con, card_id: int, rating: int, elapsed_ms: int = 0):
    """Califica una tarjeta: guarda el estado nuevo y deja rastro en el log.

    Devuelve el estado, con `sanguijuela` a True si esta calificación acaba de
    apartarla por haberla fallado demasiadas veces.
    """
    ajustes = config(con)
    row = con.execute("SELECT * FROM state WHERE card_id=?", (card_id,)).fetchone()
    previo = dict(row) if row else {}
    st = review(previo, rating, retencion=ajustes["retencion"], w=ajustes["w"])
    _guardar(con, card_id, st)
    con.execute("INSERT INTO log(card_id,rating,ts,ms) VALUES(?,?,?,?)",
                (card_id, rating, st["last"], elapsed_ms))

    st["sanguijuela"] = False
    umbral = ajustes["umbral"]
    if umbral and rating == AGAIN and st["lapses"] >= umbral and not previo.get("leech"):
        con.execute("UPDATE state SET leech=1 WHERE card_id=?", (card_id,))
        st["sanguijuela"] = True
    con.commit()
    return st


# ------------------------------------------------------------------- deshacer

def _rehacer(con, card_id: int, ajustes: dict):
    """Reconstruye el estado de una tarjeta con los repasos que le queden.

    El estado no se puede «restar», así que se rehace desde cero con las fechas
    de verdad de cada repaso.
    """
    estado = {}
    for r in con.execute("SELECT rating, ts FROM log WHERE card_id=? ORDER BY ts",
                         (card_id,)):
        estado = review(estado, r["rating"], ahora=r["ts"],
                        retencion=ajustes["retencion"], w=ajustes["w"])
    if not estado:
        estado = dict(NUEVA)
    _guardar(con, card_id, estado)
    umbral = ajustes["umbral"]
    apartada = bool(umbral and estado.get("lapses", 0) >= umbral)
    con.execute("UPDATE state SET leech=? WHERE card_id=?", (int(apartada), card_id))
    return estado


def undo_last(con, card_id: int | None = None) -> dict | None:
    """Deshace la última calificación. Devuelve qué se deshizo, o None.

    Es lo que hace la tecla Z del popup: te has equivocado de botón y quieres
    esa tarjeta como estaba hace un segundo.
    """
    sql = "SELECT id, card_id, rating, ts FROM log"
    args: tuple = ()
    if card_id is not None:
        sql += " WHERE card_id=?"
        args = (card_id,)
    fila = con.execute(f"{sql} ORDER BY ts DESC, id DESC LIMIT 1", args).fetchone()
    if not fila:
        return None
    con.execute("DELETE FROM log WHERE id=?", (fila["id"],))
    estado = _rehacer(con, fila["card_id"], config(con))
    con.commit()
    return {"card_id": fila["card_id"], "rating": fila["rating"],
            "ts": fila["ts"], "estado": estado}


def undo_recent(con, segundos: float = 86400) -> int:
    """Borra los repasos de las últimas `segundos` y deja cada tarjeta como estaba.

    Devuelve cuántos repasos se quitaron.
    """
    ajustes = config(con)
    desde = time.time() - segundos
    tocadas = [r[0] for r in con.execute("SELECT DISTINCT card_id FROM log WHERE ts>=?",
                                         (desde,))]
    n = con.execute("SELECT COUNT(*) FROM log WHERE ts>=?", (desde,)).fetchone()[0]
    con.execute("DELETE FROM log WHERE ts>=?", (desde,))
    for cid in tocadas:
        _rehacer(con, cid, ajustes)
    con.commit()
    return n


# --------------------------------------------------------------- sanguijuelas

def perdonar(con, card_id: int):
    """Devuelve una sanguijuela al ciclo y le borra los fallos acumulados."""
    con.execute("UPDATE state SET leech=0, lapses=0 WHERE card_id=?", (card_id,))
    con.commit()


def recalcular_sanguijuelas(con) -> int:
    """Reaplica el umbral actual a todas las tarjetas. Devuelve cuántas quedan."""
    umbral = config(con)["umbral"]
    if not umbral:
        con.execute("UPDATE state SET leech=0")
    else:
        con.execute("UPDATE state SET leech=(lapses >= ?)", (umbral,))
    con.commit()
    return con.execute("SELECT COUNT(*) FROM state WHERE leech=1").fetchone()[0]


# ------------------------------------------------------------ próxima tarjeta

def next_card(con, deck_key: str | None = None, new_ratio: float = 0.25,
              level: int | None = None, tags: str | None = None,
              exclude_id: int | None = None,
              exclude_ids: set[int] | list[int] | None = None,
              incluir_sanguijuelas: bool = False):
    """Elige la próxima tarjeta: primero lo vencido, si no algo nuevo, si no un repaso adelantado.

    `deck_key`, `level` y `tags` acotan la selección — es lo que usa «practicar
    este capítulo» para preguntar solo sobre lo que acabas de leer.
    `exclude_id` / `exclude_ids` evitan repetir la tarjeta actual al pedir otra.
    Las sanguijuelas se quedan fuera: para eso se apartan.
    """
    now = time.time()
    where = "d.enabled=1" if not deck_key else "d.key=?"
    args: list = []
    if deck_key:
        args.append(deck_key)
    if not incluir_sanguijuelas:
        where += " AND COALESCE(s.leech, 0)=0"
    if level:
        where += " AND c.level=?"
        args.append(level)
    if tags:
        etiquetas = [t.strip().lower() for t in tags.split(",") if t.strip()]
        if etiquetas:
            where += " AND (" + " OR ".join(["LOWER(c.tags) LIKE ?"] * len(etiquetas)) + ")"
            args += [f"%{t}%" for t in etiquetas]

    base = f"""SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.color AS deck_color,
                      d.icon AS deck_icon, d.levels AS deck_levels,
                      s.due, s.interval, s.ease, s.reps, s.lapses, s.last,
                      s.stability, s.difficulty, s.leech
               FROM cards c JOIN decks d ON d.id=c.deck_id JOIN state s ON s.card_id=c.id
               WHERE {where}"""

    def q(extra, extra_args=(), limit=1):
        return con.execute(f"{base} {extra} LIMIT {limit}", (*args, *extra_args)).fetchall()

    excluded = set()
    if exclude_id is not None:
        excluded.add(exclude_id)
    if exclude_ids:
        excluded.update(exclude_ids)

    raw_due = q("AND s.reps>0 AND s.due<=? ORDER BY s.due ASC", (now,), 50)
    raw_new = q("AND s.reps=0 ORDER BY c.level ASC, RANDOM()", (), 50)

    due = [c for c in raw_due if c["id"] not in excluded]
    new = [c for c in raw_new if c["id"] not in excluded]

    pool = []
    if due and new:
        pool = new if random.random() < new_ratio else due
    elif due:
        pool = due
    elif new:
        pool = new
    else:
        # Todo al día: repaso de refuerzo, priorizando lo que vence antes
        raw_fallback = q("ORDER BY s.due ASC", (), 50)
        fallback = [c for c in raw_fallback if c["id"] not in excluded]
        if fallback:
            pool = fallback
        elif raw_fallback:
            pool = raw_fallback

    # Si por estar excluido se quedó sin candidatos pero en raw había opciones:
    if not pool:
        if raw_due:
            pool = [c for c in raw_due if c["id"] != exclude_id] or raw_due
        elif raw_new:
            pool = [c for c in raw_new if c["id"] != exclude_id] or raw_new

    if not pool:
        return None

    if pool is new or (not due and pool is raw_new):
        # Entre las nuevas se respeta el nivel: solo se sortea dentro del más bajo
        minimo = pool[0]["level"]
        pool = [c for c in pool if c["level"] == minimo]

    return dict(random.choice(pool[:6]) if len(pool) > 1 else pool[0])


def due_label(due_ts: float) -> str:
    d = due_ts - time.time()
    if d <= 0:
        return "ahora"
    if d < 3600:
        return f"{int(d/60)} min"
    if d < DAY:
        return f"{int(d/3600)} h"
    if d < 30 * DAY:
        return f"{int(d/DAY)} d"
    return f"{d/DAY/30:.1f} meses"
