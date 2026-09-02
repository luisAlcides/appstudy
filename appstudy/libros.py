"""Tu estantería: leer los libros que ya tienes y sacar tarjetas de ellos.

Trabaja con lo que hay en el sistema, sin dependencias nuevas: `pdftotext` de
poppler para los PDF (rápido y fiable con libros que llevan texto de verdad) y
`zipfile` para los EPUB, que por dentro son HTML comprimido.

Los libros **no se copian ni se tocan**: se leen donde están. De un libro solo
acaba en la base de datos lo que tú decidas guardar — un capítulo para leer o
las tarjetas que apruebes.
"""
import html
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from . import db

EXTENSIONES = (".pdf", ".epub", ".txt", ".md")
ESPERA = 90                      # segundos para extraer texto de un libro gordo
PAGINAS_POR_TRAMO = 12           # cuando el libro no dice dónde empiezan sus partes


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


def texto(ruta: str, desde: int = 0, hasta: int = 0) -> str:
    """El texto del libro, o el de un tramo de páginas si se pide (solo PDF)."""
    p = Path(ruta)
    if not p.exists():
        raise LibroError(f"No encuentro el archivo:\n{ruta}")
    ext = p.suffix.lower()
    if ext == ".pdf":
        return _texto_pdf(p, desde, hasta)
    if ext == ".epub":
        return _texto_epub(p)
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise LibroError(f"No pude leerlo: {e}") from e


def _texto_pdf(p: Path, desde: int, hasta: int) -> str:
    if not shutil.which("pdftotext"):
        raise LibroError("Falta pdftotext. Instálalo con: sudo apt install poppler-utils")
    orden = ["pdftotext", "-layout", "-nopgbrk"]
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


# ---------------------------------------------------------------- secciones

# Un encabezado de capítulo: corto, solo, y empezando por una de estas fórmulas
_CABECERA = re.compile(
    r"^\s{0,20}((?:cap[ií]tulo|chapter|parte|part|unidad|tema|lecci[óo]n|secci[óo]n)"
    r"\s+(?:\d{1,2}|[ivxlc]{1,6})\b.{0,70}|\d{1,2}[.)]\s+[A-ZÁÉÍÓÚÑ][^.]{3,60})\s*$",
    re.I | re.M)


def secciones(texto_libro: str, paginas_total: int = 0) -> list:
    """Trocea el libro en partes manejables: por sus capítulos si los declara.

    Si no hay encabezados reconocibles —y en muchos libros no los hay— se corta
    en tramos de páginas, que para estudiar funciona igual de bien.
    """
    paginas_texto = texto_libro.split("\f")
    encontrados = []
    for i, pagina in enumerate(paginas_texto, start=1):
        for m in _CABECERA.finditer(pagina):
            titulo = re.sub(r"\s{2,}", " ", m.group(1)).strip()
            if len(titulo) > 4 and (not encontrados or encontrados[-1]["desde"] < i):
                encontrados.append({"titulo": titulo[:80], "desde": i})
                break

    total = paginas_total or len(paginas_texto)
    arranque = primera_util(texto_libro)
    if len(encontrados) >= 3:
        for a, b in zip(encontrados, encontrados[1:]):
            a["hasta"] = max(a["desde"], b["desde"] - 1)
        encontrados[-1]["hasta"] = total
        # Un «capítulo» de una página suele ser el índice: se descarta
        return [s for s in encontrados if s["hasta"] - s["desde"] >= 1][:60]

    tramos = []
    for inicio in range(arranque, max(total, arranque) + 1, PAGINAS_POR_TRAMO):
        fin = min(inicio + PAGINAS_POR_TRAMO - 1, total)
        tramos.append({"titulo": f"Páginas {inicio}–{fin}", "desde": inicio, "hasta": fin})
    return tramos[:60]


# Una línea de índice: «El motor diésel ......... 23» o «3.2 Inyección      45»
_LINEA_INDICE = re.compile(r"(\.{4,}\s*\d{1,4}|\s{4,}\d{1,4})\s*$")


def _parece_indice(pagina: str) -> bool:
    """¿Esta página es sumario? Muchas líneas cortas acabadas en número de página."""
    lineas = [l for l in pagina.splitlines() if l.strip()]
    if len(lineas) < 6:
        return False
    con_numero = sum(1 for l in lineas if _LINEA_INDICE.search(l))
    return con_numero / len(lineas) > 0.35


def primera_util(texto_libro: str) -> int:
    """La primera página con prosa de verdad: se salta portada, créditos e índice.

    Sin esto, las primeras tarjetas de un libro salen del sumario — preguntas
    sobre en qué página empieza cada capítulo, que no es estudiar nada.
    """
    paginas_texto = texto_libro.split("\f")
    for i, pagina in enumerate(paginas_texto, start=1):
        letras = sum(c.isalpha() for c in pagina)
        if letras > 700 and not _parece_indice(pagina):
            return i
        if i > 40:                       # no buscar eternamente en un libro raro
            break
    return 1


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


def guardar_lectura(con, libro: dict, seccion: dict, cuerpo: str) -> int:
    """Guarda una sección como capítulo de lectura, dentro del mazo del libro."""
    mazo = mazo_para(con, libro)
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", cuerpo) if len(p.strip()) > 40]
    bloques = [{"p": p[:1800]} for p in parrafos[:60]] or [{"p": cuerpo[:1800]}]
    pos = con.execute("SELECT COUNT(*) FROM chapters WHERE deck_id=?",
                      (mazo["id"],)).fetchone()[0] + 1
    minutos = max(3, min(30, len(cuerpo) // 1100))
    cid, _ = db.upsert_chapter(con, mazo["id"], mazo["key"], {
        "level": 2, "pos": pos, "title": f"{libro['nombre']} · {seccion['titulo']}",
        "subtitle": f"De tu biblioteca · {seccion['titulo']}",
        "minutes": minutos, "tags": "libro", "body": bloques})
    con.commit()
    return cid
