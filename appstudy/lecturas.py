"""Capítulos escritos por ti, en Markdown.

Los capítulos de fábrica viven en JSON porque es lo que come la base, pero
escribir JSON a mano es un castigo: hay que escapar comillas, contar corchetes y
no equivocarse con las comas. Aquí se acepta **Markdown**, que se escribe en
cualquier editor, y se traduce a los mismos bloques que ya sabe pintar el lector.

Los archivos van en `~/.local/share/appstudy/lecturas/*.md` y se reimportan con
Ctrl+R, igual que el contenido incluido. Un capítulo tuyo nunca se retira solo:
lo borras tú.

La cabecera dice de qué mazo es y cuánto se tarda en leerlo:

    ---
    mazo: linux
    nivel: 2
    minutos: 8
    etiquetas: permisos, procesos
    ---

    # Lo que aprendí de los permisos

    ## Los tres tríos

    Un párrafo normal, con **negrita**, *cursiva* y `código`.

    - una lista
    - con dos cosas

    ```bash
    chmod 755 script.sh
    ```

    > [!CLAVE] Lo que hay que recordar.

Sin GTK: la traducción se puede probar sin abrir ninguna ventana.
"""
import re
import unicodedata
from pathlib import Path

from . import db

CARPETA = db.DATA_DIR / "lecturas"

# Palabras por minuto de lectura tranquila, para estimar la duración
PALABRAS_POR_MINUTO = 190

AVISOS = {"NOTA": "note", "AVISO": "warn", "CLAVE": "key",
          "NOTE": "note", "WARNING": "warn", "TIP": "key"}


def carpeta() -> Path:
    CARPETA.mkdir(parents=True, exist_ok=True)
    return CARPETA


# --------------------------------------------------------------- la cabecera

_CABECERA = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

ALIAS = {"mazo": "deck", "deck": "deck", "nivel": "level", "level": "level",
         "minutos": "minutes", "minutes": "minutes", "etiquetas": "tags",
         "tags": "tags", "subtitulo": "subtitle", "subtítulo": "subtitle",
         "subtitle": "subtitle", "titulo": "title", "título": "title",
         "title": "title"}


def cabecera(texto: str) -> tuple[dict, str]:
    """Separa la cabecera del cuerpo. Devuelve (datos, resto)."""
    m = _CABECERA.match(texto or "")
    if not m:
        return {}, texto or ""
    datos = {}
    for linea in m.group(1).splitlines():
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        nombre = ALIAS.get(clave.strip().lower())
        if nombre:
            datos[nombre] = valor.strip()
    return datos, texto[m.end():]


# ------------------------------------------------------- el cuerpo, en bloques

_ENFASIS = (
    (re.compile(r"(?<!\*)\*\*(?!\s)(.+?)(?<!\s)\*\*(?!\*)", re.S), r"<b>\1</b>"),
    (re.compile(r"(?<![*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![*\w])"), r"<i>\1</i>"),
    (re.compile(r"`([^`\n]+)`"), r"<code>\1</code>"),
)

_VINETA = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMERADA = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TITULO = re.compile(r"^(#{1,6})\s+(.*)$")
_CITA = re.compile(r"^>\s?(.*)$")
_AVISO = re.compile(r"^\[!([A-Za-zÁÉÍÓÚÑ]+)\]\s*(.*)$")
_VALLA = re.compile(r"^\s*```\s*([A-Za-z0-9_+-]*)\s*$")
_MATE = re.compile(r"^\s*\$\$(.*?)\$\$\s*$", re.S)


def _linea(texto: str) -> str:
    """Negrita, cursiva y código: lo que entiende el lector de tarjetas."""
    salida = texto.strip()
    for patron, cambio in _ENFASIS:
        salida = patron.sub(cambio, salida)
    return salida


def a_bloques(cuerpo: str) -> tuple[str, list]:
    """Traduce el Markdown a (título, bloques). El título es el primer `#`."""
    lineas = (cuerpo or "").replace("\r\n", "\n").split("\n")
    titulo, bloques = "", []
    parrafo: list[str] = []
    lista: list[str] = []
    tipo_lista = None

    def cerrar_parrafo():
        nonlocal parrafo
        if parrafo:
            bloques.append({"p": _linea(" ".join(parrafo))})
            parrafo = []

    def cerrar_lista():
        nonlocal lista, tipo_lista
        if lista:
            bloques.append({tipo_lista: [_linea(x) for x in lista]})
            lista, tipo_lista = [], None

    def cerrar():
        cerrar_parrafo()
        cerrar_lista()

    i = 0
    while i < len(lineas):
        linea = lineas[i]

        valla = _VALLA.match(linea)
        if valla:
            cerrar()
            lenguaje = valla.group(1)
            i += 1
            dentro = []
            while i < len(lineas) and not _VALLA.match(lineas[i]):
                dentro.append(lineas[i])
                i += 1
            i += 1                              # la valla de cierre
            crudo = "\n".join(dentro).rstrip()
            if crudo:
                bloques.append({"code": {"lang": lenguaje, "text": crudo}}
                               if lenguaje else {"code": {"text": crudo}})
            continue

        if not linea.strip():
            cerrar()
            i += 1
            continue

        mate = _MATE.match(linea)
        if mate and mate.group(1).strip():
            cerrar()
            bloques.append({"math": mate.group(1).strip()})
            i += 1
            continue

        cab = _TITULO.match(linea)
        if cab:
            cerrar()
            nivel, texto = len(cab.group(1)), cab.group(2).strip()
            if nivel == 1 and not titulo:
                titulo = texto
            else:
                bloques.append({"h": _linea(texto)})
            i += 1
            continue

        cita = _CITA.match(linea)
        if cita:
            cerrar()
            juntas = []
            while i < len(lineas) and _CITA.match(lineas[i]):
                juntas.append(_CITA.match(lineas[i]).group(1).strip())
                i += 1
            texto = " ".join(x for x in juntas if x).strip()
            aviso = _AVISO.match(texto)
            if aviso:
                clase = AVISOS.get(aviso.group(1).upper())
                cuerpo_aviso = _linea(aviso.group(2))
                bloques.append({clase or "note": cuerpo_aviso})
            elif texto:
                bloques.append({"quote": _linea(texto)})
            continue

        vineta = _VINETA.match(linea)
        numerada = _NUMERADA.match(linea)
        if vineta or numerada:
            cerrar_parrafo()
            nuevo = "list" if vineta else "steps"
            if tipo_lista and tipo_lista != nuevo:
                cerrar_lista()
            tipo_lista = nuevo
            lista.append((vineta or numerada).group(1).strip())
            i += 1
            continue

        cerrar_lista()
        parrafo.append(linea.strip())
        i += 1

    cerrar()
    return titulo, bloques


def minutos_de(bloques: list) -> int:
    """Cuánto se tarda en leerlo, contando las palabras que hay de verdad."""
    palabras = 0
    pila = list(bloques)
    while pila:
        actual = pila.pop()
        if isinstance(actual, str):
            palabras += len(actual.split())
        elif isinstance(actual, dict):
            pila.extend(actual.values())
        elif isinstance(actual, list):
            pila.extend(actual)
    return max(1, round(palabras / PALABRAS_POR_MINUTO))


# ------------------------------------------------------------- leer y guardar

def analizar(texto: str, nombre: str = "") -> dict:
    """Convierte un Markdown entero en un capítulo listo para la base."""
    datos, cuerpo = cabecera(texto)
    titulo, bloques = a_bloques(cuerpo)
    titulo = datos.get("title") or titulo or (Path(nombre).stem if nombre else "Sin título")
    try:
        nivel = max(1, int(datos.get("level", 1)))
    except (TypeError, ValueError):
        nivel = 1
    try:
        minutos = int(datos.get("minutes", 0)) or minutos_de(bloques)
    except (TypeError, ValueError):
        minutos = minutos_de(bloques)
    return {"deck": (datos.get("deck") or "").strip().lower(),
            "title": titulo, "subtitle": datos.get("subtitle", ""),
            "level": nivel, "minutes": minutos,
            "tags": datos.get("tags", ""), "body": bloques, "propio": True}


def _slug(titulo: str) -> str:
    limpio = unicodedata.normalize("NFD", titulo.lower())
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    limpio = re.sub(r"[^a-z0-9]+", "-", limpio).strip("-")
    return limpio[:60] or "capitulo"


def a_markdown(capitulo: dict) -> str:
    """El camino de vuelta: de capítulo a Markdown, para poder editarlo."""
    cabecera_lineas = ["---", f"mazo: {capitulo.get('deck', '')}",
                       f"nivel: {capitulo.get('level', 1)}",
                       f"minutos: {capitulo.get('minutes', 5)}"]
    if capitulo.get("tags"):
        cabecera_lineas.append(f"etiquetas: {capitulo['tags']}")
    if capitulo.get("subtitle"):
        cabecera_lineas.append(f"subtítulo: {capitulo['subtitle']}")
    cabecera_lineas += ["---", "", f"# {capitulo.get('title', '')}", ""]

    partes = list(cabecera_lineas)
    for bloque in capitulo.get("body", []):
        for clave, valor in bloque.items():
            if clave == "h":
                partes += [f"## {_a_md(valor)}", ""]
            elif clave == "p":
                partes += [_a_md(valor), ""]
            elif clave in ("list", "steps"):
                marca = "-" if clave == "list" else None
                for n, x in enumerate(valor, 1):
                    partes.append(f"{marca or f'{n}.'} {_a_md(x)}")
                partes.append("")
            elif clave == "code":
                texto = valor.get("text", "") if isinstance(valor, dict) else str(valor)
                lang = valor.get("lang", "") if isinstance(valor, dict) else ""
                partes += [f"```{lang}", texto, "```", ""]
            elif clave == "math":
                partes += [f"$${valor}$$", ""]
            elif clave == "quote":
                partes += [f"> {_a_md(valor)}", ""]
            elif clave in ("note", "warn", "key"):
                etiqueta = {"note": "NOTA", "warn": "AVISO", "key": "CLAVE"}[clave]
                partes += [f"> [!{etiqueta}] {_a_md(valor)}", ""]
    return "\n".join(partes).rstrip() + "\n"


_DESMARCAR = ((re.compile(r"</?b>"), "**"), (re.compile(r"</?i>"), "*"),
              (re.compile(r"</?(?:code|tt)>"), "`"))


def _a_md(texto: str) -> str:
    salida = texto or ""
    for patron, cambio in _DESMARCAR:
        salida = patron.sub(cambio, salida)
    return salida


def guardar(titulo: str, contenido: str, fuente: str = "") -> Path:
    """Escribe el Markdown en la carpeta de lecturas. Devuelve el archivo."""
    destino = Path(fuente) if fuente else carpeta() / f"{_slug(titulo)}.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    return destino


def archivos() -> list[Path]:
    if not CARPETA.exists():
        return []
    return sorted(CARPETA.glob("*.md"))


def importar(con) -> tuple[int, int]:
    """Mete tus capítulos en la base. Devuelve (importados, con problemas).

    Un archivo sin mazo, o con un mazo que no existe, se salta sin ruido: no es
    motivo para dejar de arrancar.
    """
    hechos = fallos = 0
    for archivo in archivos():
        try:
            capitulo = analizar(archivo.read_text(encoding="utf-8"), archivo.name)
        except (OSError, UnicodeDecodeError):
            fallos += 1
            continue
        fila = con.execute("SELECT id FROM decks WHERE key=?",
                           (capitulo["deck"],)).fetchone()
        if not fila or not capitulo["body"]:
            fallos += 1
            continue
        capitulo["fuente"] = str(archivo)
        # Detrás de los de fábrica de su nivel, para no colarse en medio
        capitulo["pos"] = 500
        db.upsert_chapter(con, fila["id"], capitulo["deck"], capitulo)
        hechos += 1
    con.commit()
    return hechos, fallos


def limpiar_huerfanos(con) -> int:
    """Quita de la base los capítulos tuyos cuyo archivo ya no existe."""
    fuera = []
    for f in con.execute("SELECT id, fuente FROM chapters WHERE propio=1"):
        if f["fuente"] and not Path(f["fuente"]).exists():
            fuera.append(f["id"])
    for cid in fuera:
        con.execute("DELETE FROM chapters WHERE id=?", (cid,))
    if fuera:
        con.commit()
    return len(fuera)
