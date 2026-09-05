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
CONTENT_VERSION = "23"


# Etiqueta con la que se marca la cara inversa, para poder filtrarla después
ETIQUETA_INVERSA = "inversa"


def uid_de(deck_key: str, tarjeta: dict) -> str:
    """La identidad de una tarjeta en la base.

    Normalmente es su enunciado. La cara inversa lleva su propia semilla: su
    enunciado es la respuesta de la directa, y sin esto dos tarjetas del mismo
    mazo podrían acabar peleándose por el mismo identificador.
    """
    if tarjeta.get("_inversa"):
        return db.uid_for(deck_key, "inversa\x00" + tarjeta["_origen"])
    return db.uid_for(deck_key, tarjeta["front"])


def variantes(c: dict) -> list[dict]:
    """Las tarjetas que salen de una entrada del JSON.

    Casi siempre una. Dos si lleva `"reverse": true`, que además de preguntar
    «¿qué hace chmod?» pregunta «¿qué comando cambia los permisos?». Es el doble
    de práctica con el mismo contenido escrito una sola vez.
    """
    base = {"kind": c.get("kind", "card"), "front": c["front"],
            "back": c.get("back", ""), "hint": c.get("hint", ""),
            "choices": c.get("choices"), "answer": c.get("answer", -1),
            "tags": c.get("tags", "")}
    salida = [base]
    if c.get("reverse") and base["back"].strip() and base["kind"] == "card":
        etiquetas = ", ".join(filter(None, [base["tags"], ETIQUETA_INVERSA]))
        salida.append({**base, "front": base["back"], "back": base["front"],
                       "hint": c.get("reverse_hint", ""), "tags": etiquetas,
                       "_inversa": True, "_origen": base["front"]})
    return salida


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
            for tarjeta in variantes(c):
                _, inserted = db.add_card(
                    con, deck_id, data["key"], tarjeta["kind"], tarjeta["front"],
                    tarjeta.get("back", ""), tarjeta.get("hint", ""),
                    tarjeta.get("choices"), tarjeta.get("answer", -1),
                    tarjeta.get("tags", ""), builtin=1, level=nivel,
                    uid=uid_de(data["key"], tarjeta))
                vigentes.add(uid_de(data["key"], tarjeta))
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
        # Solo se retiran capítulos de fábrica: los que has escrito tú no están
        # en el JSON y desaparecerían en la primera recarga.
        obsoletos = [r["id"] for r in con.execute(
            "SELECT id, uid FROM chapters WHERE deck_id=? AND propio=0", (deck_id,))
            if r["uid"] not in vigentes]
        for cid in obsoletos:
            con.execute("DELETE FROM chapters WHERE id=?", (cid,))
        retirados += len(obsoletos)
    con.commit()
    return total, retirados


def load_all(con):
    """Mazos y lecturas: el orden importa, los capítulos cuelgan de un mazo."""
    from . import lecturas
    mazos, nuevas, retiradas = load_builtin(con)
    capitulos, _ = load_readings(con)
    # Y después los tuyos, que cuelgan de los mismos mazos
    lecturas.limpiar_huerfanos(con)
    propios, _ = lecturas.importar(con)
    return mazos, nuevas, retiradas, capitulos + propios


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
