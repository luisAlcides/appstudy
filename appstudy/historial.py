"""Últimas tarjetas mostradas en este equipo; consultarlas no cuenta como repaso."""
import json
import time
import unicodedata

from . import cloze, util

LIMITE = 100


def _preparar(con):
    # También funciona inmediatamente después de restaurar una copia antigua.
    existe = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                         "AND name='card_history'").fetchone()
    if existe:
        return
    con.execute("""CREATE TABLE IF NOT EXISTS card_history (
        seq INTEGER PRIMARY KEY,
        card_id INTEGER UNIQUE NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
        seen_at REAL NOT NULL
    )""")
    # En la primera apertura recuperamos lo que ya consta en los repasos.
    # Las tarjetas antiguas cerradas sin responder no tenían ningún registro.
    with con:
        con.execute("""INSERT OR IGNORE INTO card_history(card_id, seen_at)
                       SELECT card_id, ts FROM (
                           SELECT l.card_id, MAX(l.ts) AS ts FROM log l
                           JOIN cards c ON c.id = l.card_id
                           GROUP BY l.card_id ORDER BY ts DESC, l.card_id DESC LIMIT ?
                       ) ORDER BY ts, card_id""", (LIMITE,))


def registrar(con, card_id):
    """Recuerda una tarjeta al mostrarla, aunque se cierre sin responder."""
    if card_id is None:
        return
    _preparar(con)
    with con:
        con.execute("""INSERT OR REPLACE INTO card_history(card_id, seen_at)
                       SELECT id, ? FROM cards WHERE id = ?""", (time.time(), card_id))
        con.execute("""DELETE FROM card_history WHERE seq NOT IN
                       (SELECT seq FROM card_history ORDER BY seq DESC LIMIT ?)""",
                    (LIMITE,))


def _normalizar(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold())
                   if not unicodedata.combining(c))


def recientes(con, consulta=""):
    _preparar(con)
    filas = con.execute("""SELECT c.*, d.name AS deck_name, d.icon AS deck_icon,
                                  h.seen_at
                           FROM card_history h JOIN cards c ON c.id = h.card_id
                           JOIN decks d ON d.id = c.deck_id
                           ORDER BY h.seq DESC LIMIT ?""", (LIMITE,)).fetchall()
    palabras = _normalizar(consulta).split()
    return [dict(c) for c in filas if all(p in _normalizar(util.plain(
        f"{c['front']} {c['back']} {c['deck_name']} {c['tags']} {c['choices']}"))
        for p in palabras)]


def contenido(card):
    """Pregunta completa y respuesta legible, también en quizzes y huecos."""
    frente = cloze.completo(card["front"]) if card["kind"] == "cloze" else card["front"]
    respuesta = card["back"] or ""
    if card["kind"] == "quiz":
        try:
            opciones = json.loads(card["choices"] or "[]")
            if isinstance(opciones, list) and 0 <= card["answer"] < len(opciones):
                respuesta = f"Respuesta correcta: {opciones[card['answer']]}\n\n{respuesta}".strip()
        except (ValueError, TypeError):
            pass
    return frente, respuesta


def subtitulo(card):
    """Mazo y fecha, ya escapados: ActionRow lee el subtítulo como markup."""
    from gi.repository import GLib
    fecha = time.strftime("%d/%m/%Y · %H:%M", time.localtime(card["seen_at"]))
    return GLib.markup_escape_text(f"{card['deck_icon']} {card['deck_name']} · {fecha}")


def abrir(parent, con):
    """Una sola ventana por origen; cada apertura lee el historial compartido."""
    anterior = getattr(parent, "_ventana_historial", None)
    if anterior is not None:
        anterior.actualizar()
        anterior.present()
        return anterior
    from .historial_window import HistorialWindow
    ventana = HistorialWindow(parent, con)
    parent._ventana_historial = ventana
    ventana.connect("close-request", lambda *_: setattr(parent, "_ventana_historial", None))
    ventana.present()
    return ventana
