"""Tu estantería: leer los libros que ya tienes y sacar tarjetas de ellos.

Trabaja con lo que hay en el sistema, sin dependencias nuevas: `pdftotext` de
poppler para los PDF (rápido y fiable con libros que llevan texto de verdad) y
`zipfile` para los EPUB, que por dentro son HTML comprimido.

Los libros **no se copian ni se tocan**: se leen donde están. De un libro solo
acaba en la base de datos lo que tú decidas guardar — un capítulo para leer o
las tarjetas que apruebes.
"""
import hashlib
import html
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from . import db

EXTENSIONES = (".pdf", ".epub", ".txt", ".md")
ESPERA = 90                      # segundos para extraer texto de un libro gordo


def carpeta(con) -> Path:
    return Path(db.get_meta(con, "libros_dir", str(Path.home() / "Libros")))


def set_carpeta(con, ruta: str):
    db.set_meta(con, "libros_dir", str(ruta))


class LibroError(RuntimeError):
    """No se pudo leer el libro; el mensaje está pensado para enseñarlo."""


# ------------------------------------------------------------------ estante

def listar(raiz: Path, filtro: str = "", limite: int = 4000) -> list:
    """Todos los libros bajo `raiz`, con su carpeta como «tema»."""
    raiz = Path(raiz)
    if not raiz.is_dir():
        return []
    palabras = [p for p in filtro.lower().split() if p]
    salida = []
    for base, _dirs, archivos in os.walk(raiz):
        for nombre in archivos:
            if not nombre.lower().endswith(EXTENSIONES):
                continue
            ruta = Path(base) / nombre
            tema = str(ruta.parent.relative_to(raiz)) if ruta.parent != raiz else "—"
            if palabras:
                heno = f"{nombre} {tema}".lower()
                if not all(p in heno for p in palabras):
                    continue
            try:
                tam = ruta.stat().st_size
            except OSError:
                continue
            salida.append({"ruta": str(ruta), "nombre": titulo_limpio(nombre),
                           "archivo": nombre, "tema": tema, "tam": tam,
                           "ext": ruta.suffix.lower().lstrip(".")})
            if len(salida) >= limite:
                return sorted(salida, key=lambda x: (x["tema"].lower(), x["nombre"].lower()))
    return sorted(salida, key=lambda x: (x["tema"].lower(), x["nombre"].lower()))


_RUIDO = re.compile(
    r"\s*--\s*[0-9a-f]{16,}\s*--.*$|\s*--\s*Anna.s Archive.*$|\s*\(Z-Library\).*$"
    r"|\s*-- \d{9,13}\s*--.*$", re.I)


def titulo_limpio(nombre: str) -> str:
    """«Practical Vim -- Drew Neil -- 2015 -- a5a2… -- Anna's Archive.pdf» → «Practical Vim»."""
    t = Path(nombre).stem
    t = _RUIDO.sub("", t)
    t = re.sub(r"\s*--\s*", " · ", t).strip(" ·-_")
    t = re.sub(r"[_]+", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip() or Path(nombre).stem


# ------------------------------------------------------------------- texto

def paginas(ruta: str) -> int:
    """Cuántas páginas tiene un PDF (0 si no se sabe)."""
    if not str(ruta).lower().endswith(".pdf") or not shutil.which("pdfinfo"):
        return 0
    try:
        salida = subprocess.run(["pdfinfo", str(ruta)], capture_output=True, text=True,
                                timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    m = re.search(r"^Pages:\s*(\d+)", salida, re.M)
    return int(m.group(1)) if m else 0


def tamano_pagina(ruta: str) -> tuple:
    """El tamaño de la página en puntos, (ancho, alto). A4 si no se sabe."""
    if not str(ruta).lower().endswith(".pdf") or not shutil.which("pdfinfo"):
        return (595.0, 842.0)
    try:
        salida = subprocess.run(["pdfinfo", str(ruta)], capture_output=True, text=True,
                                timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return (595.0, 842.0)
    m = re.search(r"^Page size:\s*([\d.]+)\s*x\s*([\d.]+)", salida, re.M)
    if not m:
        return (595.0, 842.0)
    ancho, alto = float(m.group(1)), float(m.group(2))
    if "rotated 90" in salida or "rotated 270" in salida:
        ancho, alto = alto, ancho
    return (ancho or 595.0, alto or 842.0)


def texto(ruta: str, desde: int = 0, hasta: int = 0, saltos: bool = False) -> str:
    """El texto del libro, o el de un tramo de páginas si se pide (solo PDF).

    Con `saltos=True` se conservan los saltos de página (\f), que es como se
    sabe en qué página está cada cosa — lo necesita la búsqueda del lector.
    """
    p = Path(ruta)
    if not p.exists():
        raise LibroError(f"No encuentro el archivo:\n{ruta}")
    ext = p.suffix.lower()
    if ext == ".pdf":
        return _texto_pdf(p, desde, hasta, saltos)
    if ext == ".epub":
        return _texto_epub(p)
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise LibroError(f"No pude leerlo: {e}") from e


def _texto_pdf(p: Path, desde: int, hasta: int, saltos: bool = False) -> str:
    if not shutil.which("pdftotext"):
        raise LibroError("Falta pdftotext. Instálalo con: sudo apt install poppler-utils")
    orden = ["pdftotext", "-layout"] + ([] if saltos else ["-nopgbrk"])
    if desde:
        orden += ["-f", str(desde)]
    if hasta:
        orden += ["-l", str(hasta)]
    orden += [str(p), "-"]
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=ESPERA)
    except subprocess.TimeoutExpired as e:
        raise LibroError("El libro tardó demasiado en abrirse.") from e
    except OSError as e:
        raise LibroError(f"No pude abrirlo: {e}") from e
    if not r.stdout.strip():
        raise LibroError("Este PDF no tiene texto: parece escaneado, y para eso "
                         "haría falta OCR (tesseract).")
    return r.stdout


def _texto_epub(p: Path) -> str:
    """Un EPUB es un ZIP con XHTML dentro: se saca el texto en el orden del libro."""
    try:
        with zipfile.ZipFile(p) as z:
            nombres = [n for n in z.namelist()
                       if n.lower().endswith((".xhtml", ".html", ".htm"))]
            nombres.sort()
            trozos = []
            for n in nombres[:400]:
                try:
                    trozos.append(_html_a_texto(z.read(n).decode("utf-8", "replace")))
                except (KeyError, OSError):
                    continue
    except (zipfile.BadZipFile, OSError) as e:
        raise LibroError(f"El EPUB no se deja abrir: {e}") from e
    junto = "\n\n".join(t for t in trozos if t.strip())
    if not junto.strip():
        raise LibroError("No encontré texto dentro del EPUB.")
    return junto


def _html_a_texto(crudo: str) -> str:
    try:
        from bs4 import BeautifulSoup
        sopa = BeautifulSoup(crudo, "html.parser")
        for basura in sopa(["script", "style"]):
            basura.decompose()
        return sopa.get_text("\n")
    except ImportError:                       # sin bs4, a mano y tan tranquilos
        limpio = re.sub(r"(?is)<(script|style).*?</\1>", " ", crudo)
        return html.unescape(re.sub(r"<[^>]+>", " ", limpio))


# ------------------------------------------------------------ para la IA

# Una línea de índice: «El motor diésel ......... 23» o «3.2 Inyección      45»
_LINEA_INDICE = re.compile(r"(\.{4,}\s*\d{1,4}|\s{4,}\d{1,4})\s*$")


def limpiar_texto(crudo: str, maximo: int = 14000) -> str:
    """Deja el texto listo para el modelo: sin sumarios, numeritos ni sopa de espacios."""
    lineas = []
    for linea in crudo.replace("\f", "\n").splitlines():
        l = re.sub(r"\s{3,}", "  ", linea.rstrip())
        if not l.strip():
            continue
        if re.fullmatch(r"\s*\d{1,4}\s*", l):          # número de página suelto
            continue
        if _LINEA_INDICE.search(l):                     # renglón de índice
            continue
        lineas.append(l.strip())
    texto_limpio = "\n".join(lineas)
    return texto_limpio[:maximo]


# ----------------------------------------------------------- ver las páginas

def cache() -> Path:
    d = db.DATA_DIR / "paginas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clave(ruta: str) -> str:
    return hashlib.sha1(str(ruta).encode()).hexdigest()[:16]


def render(ruta: str, pagina: int, ancho: int = 900) -> str:
    """Dibuja una página del PDF a PNG y devuelve su ruta, con caché.

    Se usa `pdftocairo`, que viene con poppler igual que `pdftotext` y suaviza
    mucho mejor que `pdftoppm`. Cada página renderizada se guarda, así que
    volver atrás es instantáneo.
    """
    ancho = max(200, min(2600, int(ancho)))
    destino = cache() / f"{_clave(ruta)}-{int(pagina)}-{ancho}.png"
    if destino.exists() and destino.stat().st_size > 0:
        return str(destino)
    if not shutil.which("pdftocairo"):
        raise LibroError("Falta pdftocairo. Instálalo con: sudo apt install poppler-utils")
    base = str(destino)[:-4]              # pdftocairo le pone la extensión él
    orden = ["pdftocairo", "-png", "-r", "0", "-scale-to-x", str(ancho),
             "-scale-to-y", "-1", "-f", str(int(pagina)), "-l", str(int(pagina)),
             "-singlefile", str(ruta), base]
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError) as e:
        raise LibroError(f"No pude dibujar la página: {e}") from e
    if not destino.exists():
        raise LibroError(f"No pude dibujar la página {pagina}: "
                         f"{(r.stderr or 'error desconocido').strip()[:120]}")
    return str(destino)


def render_varias(ruta: str, desde: int, hasta: int, ancho: int = 900) -> list:
    """Dibuja un tramo de páginas en **una sola** llamada a pdftocairo.

    Abrir y analizar el PDF es lo caro (en un libro de 64 MB son ~250 ms), y se
    paga una vez por proceso. Pedir cuatro páginas de golpe cuesta poco más que
    pedir una, y es lo que hace que pasar hoja salga instantáneo.
    """
    ancho = max(200, min(2600, int(ancho)))
    faltan = [n for n in range(int(desde), int(hasta) + 1)
              if not (cache() / f"{_clave(ruta)}-{n}-{ancho}.png").exists()]
    if not faltan or not shutil.which("pdftocairo"):
        return []
    desde, hasta = min(faltan), max(faltan)
    with tempfile.TemporaryDirectory(dir=cache()) as tmp:
        orden = ["pdftocairo", "-png", "-r", "0", "-scale-to-x", str(ancho),
                 "-scale-to-y", "-1", "-f", str(desde), "-l", str(hasta),
                 str(ruta), str(Path(tmp) / "p")]
        try:
            subprocess.run(orden, capture_output=True, timeout=ESPERA)
        except (OSError, subprocess.SubprocessError):
            return []
        hechas = []
        for f in Path(tmp).glob("p-*.png"):
            try:                       # pdftocairo numera con ceros a la izquierda
                n = int(f.stem.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                continue
            destino = cache() / f"{_clave(ruta)}-{n}-{ancho}.png"
            if not destino.exists():
                f.replace(destino)
            hechas.append(str(destino))
    return hechas


def portada(ruta: str, ancho: int = 150) -> str | None:
    """La primera página en pequeño, para el estante. None si no se puede."""
    try:
        return render(ruta, 1, ancho)
    except LibroError:
        return None


def limpiar_cache(dias: int = 30) -> int:
    """Borra páginas dibujadas hace tiempo; se vuelven a dibujar si hacen falta."""
    corte = time.time() - dias * 86400
    n = 0
    for f in cache().glob("*.png"):
        try:
            if f.stat().st_mtime < corte:
                f.unlink()
                n += 1
        except OSError:
            continue
    return n


# ------------------------------------------------------- guardar en la base

def mazo_para(con, libro: dict) -> dict:
    """El mazo del libro: uno por carpeta («Mecanica», «Python»…), creado si hace falta."""
    tema = libro["tema"] if libro["tema"] != "—" else "Biblioteca"
    clave = "libro_" + re.sub(r"[^a-z0-9]+", "_", tema.lower()).strip("_")[:24]
    fila = con.execute("SELECT * FROM decks WHERE key=?", (clave,)).fetchone()
    if fila:
        return dict(fila)
    db.upsert_deck(con, clave, f"📚 {tema}", "📚", "#7A5C9E", 20,
                   ["Básico", "Intermedio", "Avanzado"])
    return dict(con.execute("SELECT * FROM decks WHERE key=?", (clave,)).fetchone())
