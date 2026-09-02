"""Almacenamiento SQLite: mazos, tarjetas y estado de repaso."""
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "appstudy"
DB_PATH = DATA_DIR / "appstudy.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id      INTEGER PRIMARY KEY,
    key     TEXT UNIQUE NOT NULL,
    name    TEXT NOT NULL,
    icon    TEXT NOT NULL DEFAULT '',
    color   TEXT NOT NULL DEFAULT '#3584e4',
    enabled INTEGER NOT NULL DEFAULT 1,
    pos     INTEGER NOT NULL DEFAULT 0,
    levels  TEXT NOT NULL DEFAULT ''        -- JSON: nombres de los niveles, de básico a avanzado
);

CREATE TABLE IF NOT EXISTS cards (
    id       INTEGER PRIMARY KEY,
    deck_id  INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    uid      TEXT UNIQUE NOT NULL,
    kind     TEXT NOT NULL DEFAULT 'card',   -- card | quiz | lesson
    front    TEXT NOT NULL,
    back     TEXT NOT NULL DEFAULT '',
    hint     TEXT NOT NULL DEFAULT '',
    choices  TEXT NOT NULL DEFAULT '',       -- JSON lista para kind=quiz
    answer   INTEGER NOT NULL DEFAULT -1,    -- índice correcto para kind=quiz
    tags     TEXT NOT NULL DEFAULT '',
    level    INTEGER NOT NULL DEFAULT 1,    -- 1 = el más básico del mazo
    builtin  INTEGER NOT NULL DEFAULT 0,
    created  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS state (
    card_id  INTEGER PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    due      REAL NOT NULL DEFAULT 0,
    interval REAL NOT NULL DEFAULT 0,        -- en días
    ease     REAL NOT NULL DEFAULT 2.5,
    reps     INTEGER NOT NULL DEFAULT 0,
    lapses   INTEGER NOT NULL DEFAULT 0,
    last     REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS log (
    id      INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL,
    rating  INTEGER NOT NULL,
    ts      REAL NOT NULL,
    ms      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chapters (
    id       INTEGER PRIMARY KEY,
    deck_id  INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    uid      TEXT UNIQUE NOT NULL,
    level    INTEGER NOT NULL DEFAULT 1,
    pos      INTEGER NOT NULL DEFAULT 0,
    title    TEXT NOT NULL,
    subtitle TEXT NOT NULL DEFAULT '',
    minutes  INTEGER NOT NULL DEFAULT 5,
    tags     TEXT NOT NULL DEFAULT '',   -- para practicar solo estas tarjetas
    body     TEXT NOT NULL DEFAULT '[]'  -- JSON: lista de bloques
);

CREATE TABLE IF NOT EXISTS reading (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
    leido      INTEGER NOT NULL DEFAULT 0,
    avance     REAL NOT NULL DEFAULT 0,   -- 0..1, hasta dónde llegó al hacer scroll
    ts         REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);

"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_cards_deck  ON cards(deck_id);
CREATE INDEX IF NOT EXISTS idx_cards_level ON cards(level);
CREATE INDEX IF NOT EXISTS idx_state_due   ON state(due);
CREATE INDEX IF NOT EXISTS idx_log_ts      ON log(ts);
CREATE INDEX IF NOT EXISTS idx_chap_deck   ON chapters(deck_id, level, pos);
"""


def uid_for(deck_key: str, front: str) -> str:
    return hashlib.sha1(f"{deck_key}\x00{front.strip()}".encode()).hexdigest()[:16]


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    migrate(con)
    con.executescript(INDEXES)
    return con


def migrate(con):
    """Añade a una base anterior las columnas que hayan aparecido después."""
    for tabla, columna, definicion in (
            ("cards", "level", "INTEGER NOT NULL DEFAULT 1"),
            ("decks", "levels", "TEXT NOT NULL DEFAULT ''")):
        existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}
        if columna not in existentes:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    con.commit()


def get_meta(con, key, default=None):
    row = con.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return row["v"] if row else default


def set_meta(con, key, value):
    con.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, str(value)))
    con.commit()


def upsert_deck(con, key, name, icon, color, pos, levels=None):
    con.execute(
        """INSERT INTO decks(key,name,icon,color,pos,levels) VALUES(?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET name=excluded.name, icon=excluded.icon,
                                          color=excluded.color, pos=excluded.pos,
                                          levels=excluded.levels""",
        (key, name, icon, color, pos, json.dumps(levels or [], ensure_ascii=False)))
    return con.execute("SELECT id FROM decks WHERE key=?", (key,)).fetchone()["id"]


def add_card(con, deck_id, deck_key, kind, front, back="", hint="", choices=None,
             answer=-1, tags="", builtin=0, level=1):
    uid = uid_for(deck_key, front)
    ch = json.dumps(choices, ensure_ascii=False) if choices else ""
    # SQLite informa el mismo rowcount al insertar y al actualizar, así que se
    # comprueba antes para poder distinguir una tarjeta realmente nueva.
    ya_existia = con.execute("SELECT 1 FROM cards WHERE uid=?", (uid,)).fetchone() is not None
    con.execute(
        """INSERT INTO cards(deck_id,uid,kind,front,back,hint,choices,answer,tags,
                               level,builtin,created)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(uid) DO UPDATE SET
               back=excluded.back, hint=excluded.hint, choices=excluded.choices,
               answer=excluded.answer, tags=excluded.tags, kind=excluded.kind,
               level=excluded.level, deck_id=excluded.deck_id""",
        (deck_id, uid, kind, front.strip(), back.strip(), hint.strip(), ch, answer, tags,
         level, builtin, time.time()))
    cid = con.execute("SELECT id FROM cards WHERE uid=?", (uid,)).fetchone()["id"]
    con.execute("INSERT OR IGNORE INTO state(card_id, due) VALUES(?, ?)", (cid, 0.0))
    return cid, 0 if ya_existia else 1


def upsert_chapter(con, deck_id, deck_key, ch):
    uid = hashlib.sha1(f"{deck_key}\x00cap\x00{ch['title']}".encode()).hexdigest()[:16]
    datos = (deck_id, uid, ch.get("level", 1), ch.get("pos", 0), ch["title"],
             ch.get("subtitle", ""), ch.get("minutes", 5), ch.get("tags", ""),
             json.dumps(ch.get("body", []), ensure_ascii=False))
    con.execute(
        """INSERT INTO chapters(deck_id,uid,level,pos,title,subtitle,minutes,tags,body)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(uid) DO UPDATE SET
               deck_id=excluded.deck_id, level=excluded.level, pos=excluded.pos,
               subtitle=excluded.subtitle, minutes=excluded.minutes,
               tags=excluded.tags, body=excluded.body""", datos)
    cid = con.execute("SELECT id FROM chapters WHERE uid=?", (uid,)).fetchone()["id"]
    con.execute("INSERT OR IGNORE INTO reading(chapter_id) VALUES(?)", (cid,))
    return cid, uid


def chapters(con, deck_id=None):
    """Capítulos con su estado de lectura, ordenados de básico a avanzado."""
    sql = """SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon,
                    d.color AS deck_color, d.levels AS deck_levels,
                    r.leido, r.avance
             FROM chapters c JOIN decks d ON d.id = c.deck_id
             LEFT JOIN reading r ON r.chapter_id = c.id"""
    args = ()
    if deck_id:
        sql += " WHERE c.deck_id = ?"
        args = (deck_id,)
    sql += " ORDER BY d.pos, c.level, c.pos"
    return [dict(r) for r in con.execute(sql, args)]


# Para emparejar una tarjeta con el capítulo que la explica: se comparan
# palabras de cuatro letras o más, que son las que llevan el significado.
_ETIQUETA = re.compile(r"<[^>]+>")
_PALABRA = re.compile(r"[a-z0-9áéíóúüñ]{4,}")


def _palabras(texto: str) -> set:
    return set(_PALABRA.findall(_ETIQUETA.sub(" ", (texto or "").lower())))


def _texto_body(body: str) -> str:
    """Todo el texto suelto de los bloques de un capítulo, sin la estructura JSON."""
    try:
        datos = json.loads(body or "[]")
    except ValueError:
        return body or ""
    trozos = []
    pila = [datos]
    while pila:
        actual = pila.pop()
        if isinstance(actual, str):
            trozos.append(actual)
        elif isinstance(actual, dict):
            pila.extend(actual.values())
        elif isinstance(actual, list):
            pila.extend(actual)
    return " ".join(trozos)


def card_by_id(con, card_id):
    row = con.execute(
        """SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon,
                  d.color AS deck_color, d.levels AS deck_levels
           FROM cards c JOIN decks d ON d.id = c.deck_id WHERE c.id=?""",
        (card_id,)).fetchone()
    return dict(row) if row else None


def chapter_for_card(con, card):
    """El capítulo que explica esa tarjeta, o None si no hay ninguno que encaje.

    Se puntúa por este orden: etiquetas en común (que es el vínculo explícito
    entre capítulo y tarjetas), estar en el mismo nivel y cuántas palabras de la
    tarjeta aparecen en el texto del capítulo.
    """
    if not card:
        return None
    etiquetas = {t.strip().lower() for t in (card["tags"] or "").split(",") if t.strip()}
    busca = _palabras(f"{card['front']} {card['back']}")
    mejor, mejor_puntos = None, 0.0
    for cap in chapters(con, card["deck_id"]):
        suyas = {t.strip().lower() for t in (cap["tags"] or "").split(",") if t.strip()}
        puntos = 3.0 * len(etiquetas & suyas)
        if cap["level"] == card["level"]:
            puntos += 1.5
        if busca:
            texto = _palabras(f"{cap['title']} {cap['subtitle']} {_texto_body(cap['body'])}")
            puntos += 4.0 * len(busca & texto) / len(busca)
        if puntos > mejor_puntos:
            mejor, mejor_puntos = cap, puntos
    # Por debajo de esto el parecido es casualidad y más vale no prometer nada
    return mejor if mejor_puntos >= 1.5 else None


def mark_read(con, chapter_id, leido=True):
    con.execute(
        """INSERT INTO reading(chapter_id, leido, avance, ts) VALUES(?,?,?,?)
           ON CONFLICT(chapter_id) DO UPDATE SET leido=excluded.leido, ts=excluded.ts""",
        (chapter_id, int(leido), 1.0 if leido else 0.0, time.time()))
    con.commit()


def reading_totals(con):
    r = con.execute(
        """SELECT COUNT(*) AS total, SUM(COALESCE(rd.leido, 0)) AS leidos,
                  SUM(c.minutes) AS minutos
           FROM chapters c JOIN decks d ON d.id = c.deck_id
           LEFT JOIN reading rd ON rd.chapter_id = c.id
           WHERE d.enabled = 1""").fetchone()
    return {"total": r["total"] or 0, "leidos": r["leidos"] or 0,
            "minutos": r["minutos"] or 0}


def delete_card(con, card_id):
    con.execute("DELETE FROM cards WHERE id=?", (card_id,))
    con.commit()


def deck_stats(con):
    now = time.time()
    rows = con.execute(
        """SELECT d.id, d.key, d.name, d.icon, d.color, d.enabled, d.pos, d.levels,
                  COUNT(c.id) AS total,
                  SUM(CASE WHEN s.reps = 0 THEN 1 ELSE 0 END) AS nuevas,
                  SUM(CASE WHEN s.reps > 0 AND s.due <= ? THEN 1 ELSE 0 END) AS pendientes,
                  SUM(CASE WHEN s.interval >= 21 THEN 1 ELSE 0 END) AS dominadas
           FROM decks d
           LEFT JOIN cards c ON c.deck_id = d.id
           LEFT JOIN state s ON s.card_id = c.id
           GROUP BY d.id ORDER BY d.pos, d.name""", (now,)).fetchall()
    return [dict(r) for r in rows]


def level_progress(con):
    """Avance por nivel: {deck_id: [{'name','total','vistas','pendientes'}, ...]}."""
    filas = con.execute(
        """SELECT c.deck_id, c.level,
                  COUNT(*) AS total,
                  SUM(CASE WHEN s.reps > 0 THEN 1 ELSE 0 END) AS vistas
           FROM cards c JOIN state s ON s.card_id = c.id
           GROUP BY c.deck_id, c.level ORDER BY c.deck_id, c.level""").fetchall()
    nombres = {r["id"]: json.loads(r["levels"] or "[]")
               for r in con.execute("SELECT id, levels FROM decks")}
    salida: dict[int, list] = {}
    for r in filas:
        etiquetas = nombres.get(r["deck_id"], [])
        nombre = (etiquetas[r["level"] - 1] if r["level"] - 1 < len(etiquetas)
                  else f"Nivel {r['level']}")
        salida.setdefault(r["deck_id"], []).append(
            {"level": r["level"], "name": nombre, "total": r["total"],
             "vistas": r["vistas"] or 0})
    return salida


def level_name(deck_levels: str, level: int) -> str:
    try:
        etiquetas = json.loads(deck_levels or "[]")
        return etiquetas[level - 1]
    except (ValueError, IndexError):
        return f"Nivel {level}"


def totals(con):
    now = time.time()
    r = con.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN s.reps=0 THEN 1 ELSE 0 END) AS nuevas,
                  SUM(CASE WHEN s.reps>0 AND s.due<=? THEN 1 ELSE 0 END) AS pendientes,
                  SUM(CASE WHEN s.interval>=21 THEN 1 ELSE 0 END) AS dominadas
           FROM cards c JOIN state s ON s.card_id=c.id
           JOIN decks d ON d.id=c.deck_id WHERE d.enabled=1""", (now,)).fetchone()
    d = {k: (r[k] or 0) for k in ("total", "nuevas", "pendientes", "dominadas")}
    day = time.time() - 86400
    d["hoy"] = con.execute("SELECT COUNT(*) FROM log WHERE ts>=?", (day,)).fetchone()[0]
    d["racha"] = streak(con)
    return d


def reset_streak(con):
    """Pone la racha a cero: los repasos anteriores a este momento dejan de contar."""
    set_meta(con, "racha_desde", time.time())


def streak(con):
    """Días consecutivos (hasta hoy) con al menos un repaso.

    Solo cuentan los repasos posteriores a `racha_desde`, que es lo que fija
    «Reiniciar la racha»; sin él, todo el historial.
    """
    desde = float(get_meta(con, "racha_desde", 0) or 0)
    days = {int((ts - time.timezone) // 86400)
            for (ts,) in con.execute("SELECT ts FROM log WHERE ts>=? ORDER BY ts DESC LIMIT 5000",
                                     (desde,))}
    if not days:
        return 0
    today = int((time.time() - time.timezone) // 86400)
    if today not in days and (today - 1) not in days:
        return 0
    n, d = 0, today if today in days else today - 1
    while d in days:
        n += 1
        d -= 1
    return n
