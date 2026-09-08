"""Adjuntos de tarjetas: datos locales, sin descargar URLs ni ejecutar HTML."""
import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

MAX_RECURSO = 12 * 1024 * 1024
MAX_TOTAL = 100 * 1024 * 1024


def mime(datos):
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if datos[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if datos.startswith(b"RIFF") and datos[8:12] == b"WEBP":
        return "image/webp"
    if datos.startswith(b"RIFF") and datos[8:12] == b"WAVE":
        return "audio/wav"
    if datos.startswith(b"OggS"):
        return "audio/ogg"
    if datos.startswith(b"ID3") or (len(datos) > 1 and datos[0] == 255 and datos[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if datos.startswith(b"fLaC"):
        return "audio/flac"
    raise ValueError("Adjunto no compatible: usa PNG, JPEG, GIF, WebP, MP3, Ogg, FLAC o WAV")


def validar(item):
    datos = item.get("data")
    if not isinstance(datos, bytes) or len(datos) > MAX_RECURSO:
        raise ValueError("Un adjunto supera 12 MB o no contiene bytes válidos")
    tipo = mime(datos)
    side = item.get("side", "back")
    name = item.get("name", "adjunto")
    if side not in ("front", "back") or not isinstance(name, str) or len(name) > 255:
        raise ValueError("Metadatos del adjunto no válidos")
    return {"side": side, "name": name, "mime": tipo, "data": datos}


def guardar(con, card_id, adjuntos, touch=True):
    validados = [validar(a) for a in adjuntos]
    if sum(len(a["data"]) for a in validados) > MAX_TOTAL or len(validados) > 40:
        raise ValueError("Demasiados adjuntos en una tarjeta")
    anteriores = leer(con, card_id)
    if sorted(anteriores, key=lambda a: (a["side"], a["name"])) == sorted(validados, key=lambda a: (a["side"], a["name"])):
        return
    con.execute("DELETE FROM card_media WHERE card_id=?", (card_id,))
    for a in validados:
        con.execute("INSERT OR REPLACE INTO card_media VALUES(?,?,?,?,?)",
                    (card_id, a["side"], a["name"], a["mime"], a["data"]))
    if touch:
        from . import db
        card = con.execute("SELECT uid,builtin FROM cards WHERE id=?", (card_id,)).fetchone()
        if card and not card["builtin"]:
            db.touch_sync(con, "card", card["uid"])


def leer(con, card_id, side=None):
    sql, args = "SELECT side,name,mime,data FROM card_media WHERE card_id=?", [card_id]
    if side:
        sql += " AND side=?"
        args.append(side)
    return [dict(r) for r in con.execute(sql + " ORDER BY side,name", args)]


def indice_anki(z):
    if "media" not in z.namelist():
        return {}
    if z.getinfo("media").file_size > 2 * 1024 * 1024:
        raise ValueError("El índice multimedia de Anki es demasiado grande")
    try:
        mapa = json.loads(z.read("media"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("Exporta el APKG con compatibilidad para versiones anteriores de Anki") from e
    if not isinstance(mapa, dict):
        raise ValueError("Índice multimedia de Anki no compatible")
    return {v: k for k, v in mapa.items() if isinstance(v, str) and isinstance(k, str)}


def de_anki(z, campos, inverso=None):
    inverso = indice_anki(z) if inverso is None else inverso
    salida = []
    class Imagenes(HTMLParser):
        def __init__(self, texto):
            super().__init__()
            self.names = []
            self.feed(texto)

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                src = dict(attrs).get("src")
                if src:
                    self.names.append(src)
    for side, texto in zip(("front", "back"), campos):
        names = Imagenes(texto).names + re.findall(r"\[sound:([^\]]+)\]", texto, re.I)
        for name in dict.fromkeys(names):
            member = inverso.get(name)
            if not member or member not in z.namelist():
                continue
            if not member.isdecimal():
                raise ValueError("Nombre de recurso Anki no válido")
            if z.getinfo(member).file_size > MAX_RECURSO:
                raise ValueError("Un adjunto de Anki supera 12 MB")
            datos = z.read(member)
            salida.append(validar({"side": side, "name": name, "data": datos}))
    return salida


def serializar(items):
    return [{**a, "data": base64.b64encode(a["data"]).decode("ascii")} for a in items]


def deserializar(items):
    if not isinstance(items, list) or len(items) > 40:
        raise ValueError("Lista multimedia no válida")
    salida = []
    for a in items:
        if not isinstance(a, dict) or not isinstance(a.get("data"), str) or len(a["data"]) > MAX_RECURSO * 4 // 3 + 8:
            raise ValueError("Adjunto codificado no válido")
        salida.append(validar({**a, "data": base64.b64decode(a["data"], validate=True)}))
    return salida


def widget(con, card_id, side):
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gio, GLib, Gtk
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for a in leer(con, card_id, side):
        try:
            if a["mime"].startswith("image/"):
                texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(a["data"]))
                picture = Gtk.Picture.new_for_paintable(texture)
                picture.set_can_shrink(True)
                picture.set_size_request(-1, 160)
                picture.set_tooltip_text(a["name"])
                box.append(picture)
            else:
                # Gtk.MediaFile necesita un archivo local; caché derivada de los bytes.
                from . import db
                carpeta = db.DATA_DIR / "media-cache"
                carpeta.mkdir(parents=True, exist_ok=True)
                path = carpeta / hashlib.sha256(a["data"]).hexdigest()
                if not path.exists():
                    path.write_bytes(a["data"])
                media = Gtk.MediaFile.new_for_file(Gio.File.new_for_path(str(path)))
                controls = Gtk.MediaControls.new(media)
                controls.set_tooltip_text(a["name"])
                controls.connect("unmap", lambda _w, m=media: m.pause())
                box.append(controls)
        except (GLib.Error, OSError) as e:
            box.append(Gtk.Label(label=f"No se pudo abrir {a['name']}: {e}", wrap=True))
    return box
