"""Repetición espaciada (variante de SM-2) y selección de la próxima tarjeta."""
import random
import time

DAY = 86400.0

# Calificaciones
AGAIN, HARD, GOOD, EASY = 0, 1, 2, 3
RATING_LABELS = {AGAIN: "Otra vez", HARD: "Difícil", GOOD: "Bien", EASY: "Fácil"}

# Pasos de aprendizaje en minutos, antes de pasar a intervalos de días
# Escalera de aprendizaje (en días): 10 min -> 1 h -> 1 día. Al completarla la
# tarjeta "se gradúa" y pasa a intervalos calculados con el factor de facilidad.
LEARN_STEPS = [10 / 1440, 60 / 1440, 1.0]
GRADUATE_AT = len(LEARN_STEPS)


def review(state: dict, rating: int) -> dict:
    """Devuelve el nuevo estado (due, interval, ease, reps, lapses, last)."""
    ease = float(state.get("ease") or 2.5)
    interval = float(state.get("interval") or 0.0)
    reps = int(state.get("reps") or 0)
    lapses = int(state.get("lapses") or 0)
    now = time.time()

    if rating == AGAIN:
        lapses += 1
        ease = max(1.3, ease - 0.20)
        interval = LEARN_STEPS[0]
        reps = 0
    elif reps < GRADUATE_AT:
        # Fase de aprendizaje: 10 min -> 1 h -> 1 día
        if rating == HARD:
            interval = LEARN_STEPS[0]
        elif rating == GOOD:
            interval = LEARN_STEPS[reps]
            reps += 1
        else:  # EASY salta el aprendizaje
            interval = 4.0
            ease = min(3.0, ease + 0.15)
            reps = GRADUATE_AT
    else:
        if rating == HARD:
            ease = max(1.3, ease - 0.15)
            interval = max(interval * 1.2, interval + 1)
        elif rating == GOOD:
            interval = interval * ease
        else:
            ease = min(3.0, ease + 0.15)
            interval = interval * ease * 1.3
        reps += 1

    interval = min(interval, 365.0)
    # Pequeño ruido para que los repasos no se acumulen todos el mismo día
    jitter = 1.0 + random.uniform(-0.05, 0.05) if interval >= 1 else 1.0
    return {
        "due": now + interval * jitter * DAY,
        "interval": interval,
        "ease": ease,
        "reps": reps,
        "lapses": lapses,
        "last": now,
    }


def apply_review(con, card_id: int, rating: int, elapsed_ms: int = 0):
    row = con.execute("SELECT * FROM state WHERE card_id=?", (card_id,)).fetchone()
    st = review(dict(row) if row else {}, rating)
    con.execute(
        """INSERT INTO state(card_id,due,interval,ease,reps,lapses,last)
           VALUES(:cid,:due,:interval,:ease,:reps,:lapses,:last)
           ON CONFLICT(card_id) DO UPDATE SET due=:due, interval=:interval, ease=:ease,
                                              reps=:reps, lapses=:lapses, last=:last""",
        {"cid": card_id, **st})
    con.execute("INSERT INTO log(card_id,rating,ts,ms) VALUES(?,?,?,?)",
                (card_id, rating, time.time(), elapsed_ms))
    con.commit()
    return st


def next_card(con, deck_key: str | None = None, new_ratio: float = 0.25,
              level: int | None = None, tags: str | None = None):
    """Elige la próxima tarjeta: primero lo vencido, si no algo nuevo, si no un repaso adelantado.

    `deck_key`, `level` y `tags` acotan la selección — es lo que usa «practicar
    este capítulo» para preguntar solo sobre lo que acabas de leer.
    """
    now = time.time()
    where = "d.enabled=1" if not deck_key else "d.key=?"
    args: list = []
    if deck_key:
        args.append(deck_key)
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
                      s.due, s.interval, s.ease, s.reps, s.lapses
               FROM cards c JOIN decks d ON d.id=c.deck_id JOIN state s ON s.card_id=c.id
               WHERE {where}"""

    def q(extra, extra_args=(), limit=1):
        return con.execute(f"{base} {extra} LIMIT {limit}", (*args, *extra_args)).fetchall()

    due = q("AND s.reps>0 AND s.due<=? ORDER BY s.due ASC", (now,), 12)
    new = q("AND s.reps=0 ORDER BY c.level ASC, RANDOM()", (), 8)

    pool = []
    if due and new:
        pool = new if random.random() < new_ratio else due
    elif due:
        pool = due
    elif new:
        pool = new
    else:
        # Todo al día: repaso de refuerzo, priorizando lo que vence antes
        pool = q("ORDER BY s.due ASC", (), 20)
    if not pool:
        return None
    if pool is new:
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
