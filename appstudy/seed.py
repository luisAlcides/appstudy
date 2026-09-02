"""Carga los mazos incluidos en la base de datos (idempotente)."""
import json
from pathlib import Path

from . import db

CONTENT_DIR = Path(__file__).parent / "content"
READINGS_DIR = CONTENT_DIR / "readings"

# Se sube cuando cambia el contenido incluido. Así una instalación que ya
# existía recibe las correcciones al arrancar, sin tener que recargar a mano:
# reimportar respeta el progreso porque las tarjetas se identifican por su
# enunciado y los capítulos por su título.
CONTENT_VERSION = "10"


def load_builtin(con) -> tuple[int, int, int]:
    """Importa los mazos de fábrica. Devuelve (mazos, tarjetas nuevas, retiradas).

    Las tarjetas se identifican por su enunciado, así que reimportar actualiza el texto
    sin tocar el progreso. Una tarjeta de fábrica que ya no está en el JSON se retira.
    """
    nuevas = retiradas = 0
    files = sorted(CONTENT_DIR.glob("*.json"))
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        niveles = data.get("levels", ["Básico", "Intermedio", "Avanzado"])
        deck_id = db.upsert_deck(con, data["key"], data["name"], data.get("icon", "📘"),
                                 data.get("color", "#3584e4"), data.get("pos", 99), niveles)
        vigentes = set()
        for c in data["cards"]:
            nivel = min(max(int(c.get("level", 1)), 1), len(niveles))
            _, inserted = db.add_card(
                con, deck_id, data["key"], c.get("kind", "card"), c["front"],
                c.get("back", ""), c.get("hint", ""), c.get("choices"),
                c.get("answer", -1), c.get("tags", ""), builtin=1, level=nivel)
            vigentes.add(db.uid_for(data["key"], c["front"]))
            nuevas += 1 if inserted else 0

        obsoletas = [r["id"] for r in con.execute(
            "SELECT id, uid FROM cards WHERE deck_id=? AND builtin=1", (deck_id,))
            if r["uid"] not in vigentes]
        for cid in obsoletas:
            con.execute("DELETE FROM cards WHERE id=?", (cid,))
        retiradas += len(obsoletas)
    con.commit()
    return len(files), nuevas, retiradas


def load_readings(con) -> tuple[int, int]:
    """Importa los capítulos de lectura. Devuelve (capítulos, retirados)."""
    total = retirados = 0
    for f in sorted(READINGS_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        fila = con.execute("SELECT id FROM decks WHERE key=?", (data["deck"],)).fetchone()
        if not fila:                      # el mazo aún no existe: se importa después
            continue
        deck_id = fila["id"]
        vigentes = set()
        for pos, ch in enumerate(data["chapters"], start=1):
            ch.setdefault("pos", pos)
            _, uid = db.upsert_chapter(con, deck_id, data["deck"], ch)
            vigentes.add(uid)
            total += 1
        obsoletos = [r["id"] for r in con.execute(
            "SELECT id, uid FROM chapters WHERE deck_id=?", (deck_id,))
            if r["uid"] not in vigentes]
        for cid in obsoletos:
            con.execute("DELETE FROM chapters WHERE id=?", (cid,))
        retirados += len(obsoletos)
    con.commit()
    return total, retirados


def load_all(con):
    """Mazos y lecturas: el orden importa, los capítulos cuelgan de un mazo."""
    mazos, nuevas, retiradas = load_builtin(con)
    capitulos, _ = load_readings(con)
    return mazos, nuevas, retiradas, capitulos


def ensure_seeded(con):
    if not db.get_meta(con, "seeded"):
        load_all(con)
        db.set_meta(con, "seeded", "1")
    elif db.get_meta(con, "content_version") != CONTENT_VERSION:
        load_all(con)                        # contenido nuevo o corregido
    elif not db.get_meta(con, "readings"):   # bases anteriores al modo lectura
        load_readings(con)
    db.set_meta(con, "readings", "1")
    db.set_meta(con, "content_version", CONTENT_VERSION)
