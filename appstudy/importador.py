"""Importación segura de tarjetas desde CSV/TSV y paquetes de Anki.

No toca la base de AppStudy: devuelve datos normalizados para que la interfaz
los enseñe y el usuario decida dónde guardarlos. Los archivos grandes tienen
límites explícitos y de un ``.apkg`` solo se lee la colección SQLite.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path

MAX_TARJETAS = 5000
MAX_ARCHIVO = 200 * 1024 * 1024
_SEP = "\x1f"
_SOUND = re.compile(r"\[sound:[^\]]+\]", re.I)
_IMG = re.compile(r"<img\b[^>]*>", re.I)
_BR = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"</?([a-z0-9]+)\b[^>]*>", re.I)
_CLOZE = re.compile(r"\{\{c\d+::(.*?)(?:::(.*?))?\}\}", re.I | re.S)
_PERMITIDAS = {"b", "strong", "i", "em", "u", "sub", "sup", "s", "code", "tt"}


class ImportarError(ValueError):
    pass


def _limpiar_html(texto: str) -> str:
    """Reduce el HTML de Anki al pequeño subconjunto que entiende AppStudy."""
    texto = _SOUND.sub("", texto or "")
    texto = _IMG.sub("[imagen]", texto)
    texto = _BR.sub("\n", texto)

    def tag(m):
        nombre = m.group(1).lower()
        if nombre not in _PERMITIDAS:
            return ""
        nombre = {"strong": "b", "em": "i", "code": "tt"}.get(nombre, nombre)
        return f"</{nombre}>" if m.group(0).startswith("</") else f"<{nombre}>"

    return html.unescape(_TAG.sub(tag, texto)).strip()


def _cloze_appstudy(texto: str) -> tuple[str, bool]:
    hubo = False

    def cambia(m):
        nonlocal hubo
        hubo = True
        pista = f"::{m.group(2)}" if m.group(2) else ""
        return "{{" + m.group(1) + pista + "}}"

    res = _CLOZE.sub(cambia, texto)
    if not hubo and re.search(r"\{\{.+?\}\}", res):
        hubo = True
    return res, hubo


def _tarjeta(front="", back="", tags="", deck="", hint="") -> dict | None:
    front, back = _limpiar_html(front), _limpiar_html(back)
    front, es_cloze = _cloze_appstudy(front)
    if not front.strip():
        return None
    return {"front": front, "back": back, "tags": (tags or "").strip(),
            "deck": (deck or "").strip(), "hint": (hint or "").strip(),
            "kind": "cloze" if es_cloze else "card"}


def _separador(meta: list[str], muestra: str) -> str:
    declarado = next((x.split(":", 1)[1].strip().lower() for x in meta
                      if x.lower().startswith("#separator:")), "")
    if declarado in ("tab", "\\t"):
        return "\t"
    if declarado in ("semicolon", "punto y coma"):
        return ";"
    if declarado and len(declarado) == 1:
        return declarado
    try:
        return csv.Sniffer().sniff(muestra[:8192], delimiters=",;\t").delimiter
    except csv.Error:
        return "\t" if "\t" in muestra else ","


def leer_texto(ruta: str | Path) -> list[dict]:
    path = Path(ruta)
    if path.stat().st_size > MAX_ARCHIVO:
        raise ImportarError("El archivo supera el límite de 200 MB")
    try:
        texto = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texto = path.read_text(encoding="latin-1")
    lineas = texto.splitlines()
    meta = []
    while lineas and lineas[0].startswith("#"):
        meta.append(lineas.pop(0))
    cuerpo = "\n".join(lineas)
    if not cuerpo.strip():
        return []
    lector = iter(csv.reader(io.StringIO(cuerpo), delimiter=_separador(meta, cuerpo)))
    try:
        primera = next(lector)
    except StopIteration:
        return []

    columnas_meta = next((x.split(":", 1)[1].split("\t") for x in meta
                          if x.lower().startswith("#columns:")), None)
    cabecera = [c.strip().casefold() for c in (columnas_meta or primera)]
    alias = {
        "front": {"front", "anverso", "pregunta", "question"},
        "back": {"back", "reverso", "respuesta", "answer"},
        "tags": {"tags", "etiquetas", "tag"},
        "deck": {"deck", "mazo", "deck name"},
        "hint": {"hint", "pista"},
    }
    indices = {nombre: next((i for i, c in enumerate(cabecera) if c in nombres), None)
               for nombre, nombres in alias.items()}
    tiene_cabecera = columnas_meta is not None or indices["front"] is not None
    if not tiene_cabecera:
        indices = {"front": 0, "back": 1, "tags": 2, "deck": None, "hint": None}
    # No materializar todo el CSV: se conserva como iterador y se corta al llegar
    # al límite, incluso si el archivo contiene millones de filas.
    if columnas_meta is not None or not tiene_cabecera:
        def datos():
            yield primera
            yield from lector
        filas_datos = datos()
    else:
        filas_datos = lector

    def celda(fila, nombre):
        i = indices.get(nombre)
        return fila[i] if i is not None and i < len(fila) else ""

    salida = []
    for fila in filas_datos:
        tarjeta = _tarjeta(*(celda(fila, n) for n in
                             ("front", "back", "tags", "deck", "hint")))
        if tarjeta:
            salida.append(tarjeta)
        if len(salida) >= MAX_TARJETAS:
            break
    return salida


def _coleccion_apkg(z: zipfile.ZipFile) -> tuple[bytes, str]:
    candidatos = ("collection.anki21", "collection.anki2", "collection.anki21b")
    nombre = next((n for n in candidatos if n in z.namelist()), None)
    if not nombre:
        raise ImportarError("El paquete no contiene una colección de Anki compatible")
    info = z.getinfo(nombre)
    if info.file_size > MAX_ARCHIVO:
        raise ImportarError("La colección de Anki supera el límite de 200 MB")
    datos = z.read(nombre)
    if nombre.endswith("21b"):
        zstd = shutil.which("zstd")
        if not zstd:
            raise ImportarError("Este Anki moderno requiere zstd; exporta como texto TSV")
        with tempfile.TemporaryDirectory(prefix="appstudy-anki-") as tmp:
            entrada, salida = Path(tmp) / "in.zst", Path(tmp) / "collection.db"
            entrada.write_bytes(datos)
            r = subprocess.run([zstd, "-q", "-d", "-f", str(entrada), "-o", str(salida)],
                               capture_output=True, timeout=30)
            if r.returncode:
                raise ImportarError("No se pudo descomprimir la colección de Anki")
            if salida.stat().st_size > MAX_ARCHIVO:
                raise ImportarError("La colección descomprimida supera el límite de 200 MB")
            datos = salida.read_bytes()
    return datos, nombre


def leer_apkg(ruta: str | Path) -> list[dict]:
    path = Path(ruta)
    if path.stat().st_size > MAX_ARCHIVO:
        raise ImportarError("El paquete supera el límite de 200 MB")
    try:
        with zipfile.ZipFile(path) as z:
            datos, _ = _coleccion_apkg(z)
    except zipfile.BadZipFile as e:
        raise ImportarError("El archivo no es un paquete de Anki válido") from e

    with tempfile.NamedTemporaryFile(prefix="appstudy-anki-", suffix=".db") as tmp:
        tmp.write(datos)
        tmp.flush()
        try:
            con = sqlite3.connect(f"file:{tmp.name}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            filas = con.execute(
                """SELECT n.flds, n.tags, MIN(c.did) AS did
                   FROM notes n JOIN cards c ON c.nid=n.id
                   GROUP BY n.id LIMIT ?""", (MAX_TARJETAS,)).fetchall()
            try:
                decks = {str(r["id"]): r["name"] for r in
                         con.execute("SELECT id, name FROM decks")}
            except sqlite3.Error:
                raw = con.execute("SELECT decks FROM col LIMIT 1").fetchone()
                decks = {str(k): v.get("name", "")
                         for k, v in json.loads(raw[0] if raw else "{}").items()}
            con.close()
        except sqlite3.Error as e:
            raise ImportarError("La colección de Anki no tiene un formato compatible") from e

    salida = []
    for f in filas:
        campos = (f["flds"] or "").split(_SEP)
        tarjeta = _tarjeta(
            campos[0] if campos else "", campos[1] if len(campos) > 1 else "",
            (f["tags"] or "").strip().replace(" ", ", "),
            decks.get(str(f["did"]), "Anki"))
        if tarjeta:
            salida.append(tarjeta)
    return salida


def leer(ruta: str | Path) -> list[dict]:
    path = Path(ruta)
    if not path.is_file():
        raise ImportarError("No se encontró el archivo")
    return leer_apkg(path) if path.suffix.casefold() == ".apkg" else leer_texto(path)
