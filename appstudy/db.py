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
    card_id    INTEGER PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
    due        REAL NOT NULL DEFAULT 0,
    interval   REAL NOT NULL DEFAULT 0,      -- en días
    ease       REAL NOT NULL DEFAULT 2.5,    -- equivalente del SM-2, solo informativo
    reps       INTEGER NOT NULL DEFAULT 0,
    lapses     INTEGER NOT NULL DEFAULT 0,
    last       REAL NOT NULL DEFAULT 0,
    stability  REAL NOT NULL DEFAULT 0,      -- FSRS: días que aguanta el recuerdo
    difficulty REAL NOT NULL DEFAULT 0,      -- FSRS: de 1 (fácil) a 10 (difícil)
    leech      INTEGER NOT NULL DEFAULT 0    -- apartada por fallarla demasiado
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
    body     TEXT NOT NULL DEFAULT '[]', -- JSON: lista de bloques
    propio   INTEGER NOT NULL DEFAULT 0, -- escrito por ti, no viene de fábrica
    fuente   TEXT NOT NULL DEFAULT ''    -- el archivo Markdown del que salió
);

-- Lo que subrayas y anotas en un libro. Las coordenadas van de 0 a 1, relativas
-- a la página: así el subrayado sigue en su sitio con cualquier zoom y en
-- cualquier pantalla.
CREATE TABLE IF NOT EXISTS notas (
    id      INTEGER PRIMARY KEY,
    ruta    TEXT NOT NULL,
    pagina  INTEGER NOT NULL DEFAULT 1,
    x0      REAL NOT NULL DEFAULT 0,
    y0      REAL NOT NULL DEFAULT 0,
    x1      REAL NOT NULL DEFAULT 0,
    y1      REAL NOT NULL DEFAULT 0,
    color   TEXT NOT NULL DEFAULT 'amarillo',
    texto   TEXT NOT NULL DEFAULT '',   -- lo que hay debajo del subrayado
    nota    TEXT NOT NULL DEFAULT '',   -- lo que tú escribes al lado
    card_id INTEGER,                    -- la tarjeta que salió de aquí, si la hubo
    ts      REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reading (
    chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
    leido      INTEGER NOT NULL DEFAULT 0,
    avance     REAL NOT NULL DEFAULT 0,   -- 0..1, hasta dónde llegó al hacer scroll
    ts         REAL NOT NULL DEFAULT 0
);

-- Los libros de tu biblioteca: solo la ruta y por dónde vas. El PDF se queda
-- donde está; aquí no se copia nada.
CREATE TABLE IF NOT EXISTS books (
    id       INTEGER PRIMARY KEY,
    ruta     TEXT UNIQUE NOT NULL,
    titulo   TEXT NOT NULL,
    tema     TEXT NOT NULL DEFAULT '',
    paginas  INTEGER NOT NULL DEFAULT 0,
    pagina   INTEGER NOT NULL DEFAULT 1,   -- por dónde ibas
    abierto  REAL NOT NULL DEFAULT 0,      -- cuándo lo abriste por última vez
    minutos  REAL NOT NULL DEFAULT 0,      -- tiempo leído, acumulado
    favorito INTEGER NOT NULL DEFAULT 0,
    marcas   TEXT NOT NULL DEFAULT '[]',   -- JSON: páginas marcadas
    zoom     TEXT NOT NULL DEFAULT ''      -- cómo lo estabas leyendo
);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);

-- Reloj por elemento para fusionar cambios entre equipos sin depender de los
-- identificadores numéricos locales. Una fila borrada conserva aquí su lápida.
CREATE TABLE IF NOT EXISTS sync_changes (
    entity   TEXT NOT NULL,
    uid      TEXT NOT NULL,
    modified REAL NOT NULL,
    deleted  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(entity, uid)
);

"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_cards_deck  ON cards(deck_id);
CREATE INDEX IF NOT EXISTS idx_cards_level ON cards(level);
CREATE INDEX IF NOT EXISTS idx_state_due   ON state(due);
CREATE INDEX IF NOT EXISTS idx_state_leech ON state(leech);
CREATE INDEX IF NOT EXISTS idx_log_ts      ON log(ts);
CREATE INDEX IF NOT EXISTS idx_chap_deck   ON chapters(deck_id, level, pos);
CREATE INDEX IF NOT EXISTS idx_books_abierto ON books(abierto DESC);
CREATE INDEX IF NOT EXISTS idx_notas_libro  ON notas(ruta, pagina);
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
            ("decks", "levels", "TEXT NOT NULL DEFAULT ''"),
            ("books", "marcas", "TEXT NOT NULL DEFAULT '[]'"),
            ("books", "zoom", "TEXT NOT NULL DEFAULT ''"),
            ("state", "stability", "REAL NOT NULL DEFAULT 0"),
            ("state", "difficulty", "REAL NOT NULL DEFAULT 0"),
            ("state", "leech", "INTEGER NOT NULL DEFAULT 0"),
            ("chapters", "propio", "INTEGER NOT NULL DEFAULT 0"),
            ("chapters", "fuente", "TEXT NOT NULL DEFAULT ''")):
        existentes = {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}
        # Sin columnas es que la tabla no existe: pasa al restaurar el respaldo
        # de una versión anterior, y no es motivo para dejar de arrancar.
        if not existentes:
            continue
        if columna not in existentes:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
    con.commit()
    convertir_a_fsrs(con)


def convertir_a_fsrs(con) -> int:
    """Traduce el estado SM-2 de una base anterior al de FSRS, sin perder nada.

    La equivalencia es directa donde importa: a la retención de fábrica el
    intervalo *es* la estabilidad, así que una tarjeta que volvía cada 30 días
    entra con 30 días de estabilidad y sigue apareciendo cuando le tocaba. La
    dificultad se deduce del factor de facilidad, que es lo más parecido que
    guardaba SM-2: 2.5 (el de fábrica) cae en mitad de la escala.

    Devuelve cuántas tarjetas se convirtieron. Solo toca las que ya se
    estudiaron y aún no tienen estabilidad, así que repetirla no hace nada.
    """
    filas = con.execute(
        "SELECT card_id, interval, ease FROM state WHERE reps > 0 AND stability <= 0"
    ).fetchall()
    for f in filas:
        estabilidad = max(float(f["interval"] or 0.0), 0.1)
        facilidad = min(max(float(f["ease"] or 2.5), 1.3), 3.0)
        dificultad = 1.0 + 9.0 * (3.0 - facilidad) / (3.0 - 1.3)
        con.execute("UPDATE state SET stability=?, difficulty=? WHERE card_id=?",
                    (estabilidad, round(dificultad, 4), f["card_id"]))
    if filas:
        con.commit()
    return len(filas)


def get_meta(con, key, default=None):
    row = con.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return row["v"] if row else default


def set_meta(con, key, value):
    con.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, str(value)))
    con.commit()


def touch_sync(con, entity: str, uid: str, deleted: bool = False,
               modified: float | None = None):
    """Marca un contenido propio como cambiado, sin hacer commit por separado."""
    con.execute(
        """INSERT INTO sync_changes(entity,uid,modified,deleted) VALUES(?,?,?,?)
           ON CONFLICT(entity,uid) DO UPDATE SET
               modified=excluded.modified, deleted=excluded.deleted""",
        (entity, uid, time.time() if modified is None else float(modified), int(deleted)))


def upsert_deck(con, key, name, icon, color, pos, levels=None):
    con.execute(
        """INSERT INTO decks(key,name,icon,color,pos,levels) VALUES(?,?,?,?,?,?)
           ON CONFLICT(key) DO UPDATE SET name=excluded.name, icon=excluded.icon,
                                          color=excluded.color, pos=excluded.pos,
                                          levels=excluded.levels""",
        (key, name, icon, color, pos, json.dumps(levels or [], ensure_ascii=False)))
    return con.execute("SELECT id FROM decks WHERE key=?", (key,)).fetchone()["id"]


def add_card(con, deck_id, deck_key, kind, front, back="", hint="", choices=None,
             answer=-1, tags="", builtin=0, level=1, uid=None):
    """Crea o actualiza una tarjeta. `uid` propio para las que no se identifican
    por su enunciado, como la cara inversa de una tarjeta de doble sentido."""
    uid = uid or uid_for(deck_key, front)
    ch = json.dumps(choices, ensure_ascii=False) if choices else ""
    # SQLite informa el mismo rowcount al insertar y al actualizar, así que se
    # comprueba antes para poder distinguir una tarjeta realmente nueva.
    anterior = con.execute("SELECT * FROM cards WHERE uid=?", (uid,)).fetchone()
    ya_existia = anterior is not None
    valores = (deck_id, kind, front.strip(), back.strip(), hint.strip(), ch, answer,
               tags, level, builtin)
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
    previo = ((anterior["deck_id"], anterior["kind"], anterior["front"],
               anterior["back"], anterior["hint"], anterior["choices"],
               anterior["answer"], anterior["tags"], anterior["level"],
               anterior["builtin"]) if anterior else None)
    if not builtin and previo != valores:
        touch_sync(con, "card", uid)
    return cid, 0 if ya_existia else 1


def uid_capitulo(deck_key: str, titulo: str, propio: bool = False) -> str:
    """La identidad de un capítulo: su título dentro de su mazo.

    Los tuyos llevan su propia semilla para que no puedan chocar con uno de
    fábrica que se llame igual.
    """
    marca = "cap-propio" if propio else "cap"
    return hashlib.sha1(
        f"{deck_key}\x00{marca}\x00{titulo}".encode()).hexdigest()[:16]


def upsert_chapter(con, deck_id, deck_key, ch):
    propio = 1 if ch.get("propio") else 0
    uid = uid_capitulo(deck_key, ch["title"], bool(propio))
    datos = (deck_id, uid, ch.get("level", 1), ch.get("pos", 0), ch["title"],
             ch.get("subtitle", ""), ch.get("minutes", 5), ch.get("tags", ""),
             json.dumps(ch.get("body", []), ensure_ascii=False),
             propio, ch.get("fuente", ""))
    anterior = con.execute("SELECT * FROM chapters WHERE uid=?", (uid,)).fetchone()
    con.execute(
        """INSERT INTO chapters(deck_id,uid,level,pos,title,subtitle,minutes,tags,
                                body,propio,fuente)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(uid) DO UPDATE SET
               deck_id=excluded.deck_id, level=excluded.level, pos=excluded.pos,
               subtitle=excluded.subtitle, minutes=excluded.minutes,
               tags=excluded.tags, body=excluded.body, propio=excluded.propio,
               fuente=excluded.fuente""", datos)
    cid = con.execute("SELECT id FROM chapters WHERE uid=?", (uid,)).fetchone()["id"]
    con.execute("INSERT OR IGNORE INTO reading(chapter_id) VALUES(?)", (cid,))
    previo = ((anterior["deck_id"], anterior["uid"], anterior["level"],
               anterior["pos"], anterior["title"], anterior["subtitle"],
               anterior["minutes"], anterior["tags"], anterior["body"],
               anterior["propio"], anterior["fuente"]) if anterior else None)
    if propio and previo != datos:
        touch_sync(con, "chapter", uid)
    return cid, uid


def borrar_capitulo(con, chapter_id: int):
    fila = con.execute("SELECT uid, propio FROM chapters WHERE id=?", (chapter_id,)).fetchone()
    con.execute("DELETE FROM chapters WHERE id=?", (chapter_id,))
    if fila and fila["propio"]:
        touch_sync(con, "chapter", fila["uid"], deleted=True)
    con.commit()


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
    """Una tarjeta con su mazo y su estado de repaso, lista para enseñarla."""
    row = con.execute(
        """SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon,
                  d.color AS deck_color, d.levels AS deck_levels,
                  s.due, s.interval, s.ease, s.reps, s.lapses, s.last,
                  s.stability, s.difficulty, s.leech
           FROM cards c JOIN decks d ON d.id = c.deck_id
           LEFT JOIN state s ON s.card_id = c.id WHERE c.id=?""",
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


# ------------------------------------------------------------------- libros

def book(con, ruta: str) -> dict | None:
    fila = con.execute("SELECT * FROM books WHERE ruta=?", (str(ruta),)).fetchone()
    return dict(fila) if fila else None


def book_abrir(con, ruta: str, titulo: str, tema: str, paginas: int) -> dict:
    """Registra el libro (si es la primera vez) y anota que lo acabas de abrir."""
    con.execute(
        """INSERT INTO books(ruta, titulo, tema, paginas, pagina, abierto)
           VALUES(?,?,?,?,1,?)
           ON CONFLICT(ruta) DO UPDATE SET titulo=excluded.titulo, tema=excluded.tema,
                                           paginas=excluded.paginas, abierto=excluded.abierto""",
        (str(ruta), titulo, tema, paginas, time.time()))
    con.commit()
    return book(con, ruta)


def book_progreso(con, ruta: str, pagina: int, minutos: float = 0.0):
    """Guarda por dónde vas. Es lo que hace que retomes donde lo dejaste."""
    con.execute(
        """UPDATE books SET pagina=?, abierto=?, minutos=minutos+? WHERE ruta=?""",
        (max(1, int(pagina)), time.time(), max(0.0, minutos), str(ruta)))
    con.commit()


def book_favorito(con, ruta: str, favorito: bool):
    con.execute("UPDATE books SET favorito=? WHERE ruta=?", (int(favorito), str(ruta)))
    con.commit()


def book_marcas(con, ruta: str) -> list:
    fila = con.execute("SELECT marcas FROM books WHERE ruta=?", (str(ruta),)).fetchone()
    try:
        return sorted(json.loads(fila["marcas"])) if fila else []
    except (ValueError, TypeError):
        return []


def book_marcar(con, ruta: str, pagina: int) -> list:
    """Pone o quita el marcador de una página. Devuelve cómo quedan."""
    marcas = book_marcas(con, ruta)
    marcas.remove(pagina) if pagina in marcas else marcas.append(pagina)
    con.execute("UPDATE books SET marcas=? WHERE ruta=?",
                (json.dumps(sorted(marcas)), str(ruta)))
    con.commit()
    return sorted(marcas)


def book_zoom(con, ruta: str, ajuste: str = None):
    """Guarda o lee cómo estabas leyendo el libro (ajuste y escala)."""
    if ajuste is None:
        fila = con.execute("SELECT zoom FROM books WHERE ruta=?", (str(ruta),)).fetchone()
        return fila["zoom"] if fila else ""
    con.execute("UPDATE books SET zoom=? WHERE ruta=?", (ajuste, str(ruta)))
    con.commit()
    return ajuste


def books_leyendo(con, cuantos: int = 12) -> list:
    """Los últimos que abriste y aún no terminaste: para «seguir leyendo»."""
    filas = con.execute(
        """SELECT * FROM books WHERE abierto > 0 ORDER BY abierto DESC LIMIT ?""",
        (cuantos,)).fetchall()
    return [dict(f) for f in filas]


# ------------------------------------------------------- subrayados y notas

COLORES_NOTA = {
    "amarillo": (0.98, 0.85, 0.20),
    "verde":    (0.35, 0.80, 0.45),
    "azul":     (0.35, 0.62, 0.92),
    "rosa":     (0.95, 0.45, 0.65),
}


def nota_add(con, ruta: str, pagina: int, rect, texto: str = "",
             nota: str = "", color: str = "amarillo") -> int:
    """Guarda un subrayado. `rect` va de 0 a 1, relativo a la página."""
    x0, y0, x1, y1 = rect
    cur = con.execute(
        """INSERT INTO notas(ruta,pagina,x0,y0,x1,y1,color,texto,nota,ts)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (str(ruta), int(pagina), min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
         color if color in COLORES_NOTA else "amarillo", texto.strip(), nota.strip(),
         time.time()))
    con.commit()
    return cur.lastrowid


def notas_de(con, ruta: str, pagina: int | None = None) -> list[dict]:
    """Los subrayados de un libro, o solo los de una página."""
    sql = "SELECT * FROM notas WHERE ruta=?"
    args: tuple = (str(ruta),)
    if pagina is not None:
        sql += " AND pagina=?"
        args += (int(pagina),)
    sql += " ORDER BY pagina, y0, x0"
    return [dict(f) for f in con.execute(sql, args)]


def nota_editar(con, nota_id: int, **campos):
    """Cambia el comentario, el color o la tarjeta asociada de un subrayado."""
    permitidos = {"nota", "color", "texto", "card_id"}
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return
    asignaciones = ", ".join(f"{k}=?" for k in cambios)
    con.execute(f"UPDATE notas SET {asignaciones} WHERE id=?",
                (*cambios.values(), nota_id))
    con.commit()


def nota_borrar(con, nota_id: int):
    con.execute("DELETE FROM notas WHERE id=?", (nota_id,))
    con.commit()


def notas_totales(con) -> dict:
    """Cuántos subrayados hay y en cuántos libros, para enseñarlo de un vistazo."""
    fila = con.execute(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT ruta) AS libros FROM notas").fetchone()
    return {"n": fila["n"] or 0, "libros": fila["libros"] or 0}


def books_todos(con) -> dict:
    """Todo lo que se sabe de tus libros, indexado por ruta."""
    return {f["ruta"]: dict(f) for f in con.execute("SELECT * FROM books")}


def delete_card(con, card_id):
    fila = con.execute("SELECT uid, builtin FROM cards WHERE id=?", (card_id,)).fetchone()
    con.execute("DELETE FROM cards WHERE id=?", (card_id,))
    if fila and not fila["builtin"]:
        touch_sync(con, "card", fila["uid"], deleted=True)
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
    d["sanguijuelas"] = con.execute(
        """SELECT COUNT(*) FROM state s JOIN cards c ON c.id=s.card_id
           JOIN decks d ON d.id=c.deck_id
           WHERE d.enabled=1 AND s.leech=1""").fetchone()[0]
    d["objetivo"] = objetivo_diario(con)
    d["restan"] = max(0, d["objetivo"] - d["hoy"]) if d["objetivo"] else 0
    return d


# ------------------------------------------------------------ objetivo diario

OBJETIVO_POR_DEFECTO = 0        # 0 = sin objetivo


def objetivo_diario(con) -> int:
    try:
        return max(0, int(get_meta(con, "objetivo_diario", OBJETIVO_POR_DEFECTO)))
    except (TypeError, ValueError):
        return OBJETIVO_POR_DEFECTO


def set_objetivo_diario(con, tarjetas: int):
    set_meta(con, "objetivo_diario", max(0, int(tarjetas)))


def repasos_por_dia(con, dias: int = 7) -> list[dict]:
    """Cuántas tarjetas por día en los últimos `dias`, de más antiguo a hoy.

    Sirve para la barra de la extensión y para saber si cumpliste el objetivo.
    """
    objetivo = objetivo_diario(con)
    desde = time.time() - dias * 86400
    cuenta: dict[str, int] = {}
    for (ts,) in con.execute("SELECT ts FROM log WHERE ts>=?", (desde,)):
        dia = time.strftime("%Y-%m-%d", time.localtime(ts))
        cuenta[dia] = cuenta.get(dia, 0) + 1
    salida = []
    for atras in range(dias - 1, -1, -1):
        dia = time.strftime("%Y-%m-%d", time.localtime(time.time() - atras * 86400))
        n = cuenta.get(dia, 0)
        salida.append({"dia": dia, "n": n,
                       "cumplido": bool(objetivo and n >= objetivo)})
    return salida


# --------------------------------------------------------------- sanguijuelas

def leeches(con) -> list[dict]:
    """Las tarjetas apartadas por fallarlas demasiadas veces, la peor primero."""
    filas = con.execute(
        """SELECT c.*, d.key AS deck_key, d.name AS deck_name, d.icon AS deck_icon,
                  d.color AS deck_color, d.levels AS deck_levels,
                  s.lapses, s.reps, s.due, s.interval, s.difficulty
           FROM state s JOIN cards c ON c.id=s.card_id JOIN decks d ON d.id=c.deck_id
           WHERE s.leech=1 ORDER BY s.lapses DESC, c.id""").fetchall()
    return [dict(f) for f in filas]


def reset_streak(con):
    """Pone la racha a cero: los repasos anteriores a este momento dejan de contar."""
    set_meta(con, "racha_desde", time.time())


def streak(con):
    """Días consecutivos (hasta hoy) con al menos un repaso.

    Solo cuentan los repasos posteriores a `racha_desde`, que es lo que fija
    «Reiniciar la racha»; sin él, todo el historial.

    Los días los agrupa SQLite con `localtime`, que sabe de horario de verano.
    Contarlos en Python dividiendo por 86400 desplazaba el corte del día una
    hora media parte del año, y con ello alguna racha.
    """
    desde = float(get_meta(con, "racha_desde", 0) or 0)
    dias = [f[0] for f in con.execute(
        """SELECT DISTINCT date(ts, 'unixepoch', 'localtime') AS d FROM log
           WHERE ts >= ? ORDER BY d DESC LIMIT 4000""", (desde,))]
    if not dias:
        return 0
    hoy = time.strftime("%Y-%m-%d", time.localtime())
    ayer = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    # La racha sigue viva si estudiaste hoy o, aún sin estrenar el día, ayer
    if dias[0] not in (hoy, ayer):
        return 0
    tiene = set(dias)
    n, cuando = 0, time.time() if dias[0] == hoy else time.time() - 86400
    while time.strftime("%Y-%m-%d", time.localtime(cuando)) in tiene:
        n += 1
        cuando -= 86400
    return n
