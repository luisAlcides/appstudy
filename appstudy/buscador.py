"""Buscar a la vez en tarjetas, capítulos, libros y subrayados.

Es lo que hay detrás de Ctrl+K. Combina coincidencia literal con un índice
conceptual pequeño y raíces morfológicas: «administrar demonios» puede encontrar
«controla los servicios» sin descargar un modelo ni enviar texto fuera.

Sin GTK: la búsqueda se puede probar sin abrir ninguna ventana. Quien enseña los
resultados es la ventana principal.
"""
import re
import time
import unicodedata
from functools import lru_cache

from . import db, util

LIMITE_POR_TIPO = 8
LIMITE_TOTAL = 24

# Cada tipo lleva su icono y el peso con el que compite por salir arriba. Las
# tarjetas pesan más porque son lo que más se busca; los subrayados menos,
# porque suelen ser muchos y muy parecidos entre sí.
TIPOS = {
    "tarjeta":   {"icono": "🗂️", "nombre": "Tarjeta", "peso": 1.00},
    "capitulo":  {"icono": "📖", "nombre": "Capítulo", "peso": 0.95},
    "libro":     {"icono": "📚", "nombre": "Libro", "peso": 0.85},
    "nota":      {"icono": "🖍️", "nombre": "Subrayado", "peso": 0.70},
}


@lru_cache(maxsize=8192)
def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos: buscar «ingles» tiene que encontrar «inglés»."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _palabras(consulta: str) -> list[str]:
    return [p for p in re.split(r"\s+", normalizar(consulta).strip()) if p]


# Familias pequeñas y deliberadas: cubren intenciones habituales sin descargar
# un modelo ni convertir «cosa» en media biblioteca. Se complementan con raíces
# morfológicas, de modo que «eliminación» también entiende «eliminar».
CONCEPTOS = (
    ("estudiar", "repasar", "practicar", "aprender", "memorizar", "study", "learn"),
    ("borrar", "eliminar", "quitar", "suprimir", "delete", "remove"),
    ("crear", "agregar", "anadir", "insertar", "generar", "create", "add"),
    ("cambiar", "modificar", "editar", "actualizar", "change", "edit", "update"),
    ("gestionar", "administrar", "controlar", "manejar", "manage", "control"),
    ("error", "fallo", "problema", "bug", "failure"),
    ("respuesta", "solucion", "resultado", "answer", "solution"),
    ("pregunta", "duda", "consulta", "enunciado", "question", "query"),
    ("tarjeta", "ficha", "flashcard", "card"),
    ("libro", "texto", "manual", "documento", "book", "document"),
    ("permiso", "autorizacion", "acceso", "privilegio", "permission"),
    ("red", "conexion", "internet", "network"),
    ("servicio", "demonio", "daemon", "proceso", "service"),
    ("guardar", "almacenar", "persistir", "save", "store"),
    ("buscar", "encontrar", "localizar", "search", "find"),
    ("rapido", "veloz", "inmediato", "quick", "fast"),
    ("seguridad", "proteger", "cifrar", "privacidad", "secure", "encrypt"),
    ("archivo", "fichero", "file"),
    ("carpeta", "directorio", "folder", "directory"),
    ("computadora", "ordenador", "equipo", "pc", "computer", "machine"),
)

_SUFIJOS = ("amientos", "imientos", "aciones", "iciones", "amiento", "imiento",
             "acion", "icion", "mente", "adores", "adoras", "ador", "adora",
             "iendo", "ando", "ados", "adas", "idos", "idas", "es", "s",
             "ar", "er", "ir", "ed", "ing")


@lru_cache(maxsize=4096)
def _raiz(palabra: str) -> str:
    for sufijo in _SUFIJOS:
        if palabra.endswith(sufijo) and len(palabra) - len(sufijo) >= 4:
            return palabra[:-len(sufijo)]
    return palabra


@lru_cache(maxsize=4096)
def _alternativas(palabra: str) -> frozenset[str]:
    raiz = _raiz(palabra)
    salida = {palabra}
    for familia in CONCEPTOS:
        if any(_raiz(x) == raiz for x in familia):
            salida.update(familia)
    return frozenset(salida)


def _grupos_semanticos(palabras) -> list[frozenset[str]]:
    """Una consulta como «inteligencia artificial» no duplica el mismo concepto."""
    salida = []
    for palabra in palabras:
        grupo = _alternativas(palabra)
        if grupo not in salida:
            salida.append(grupo)
    return salida


def _puntuar(palabras, *campos) -> float:
    """Cuánto encaja un resultado. Cero si le falta alguna palabra.

    Se exigen **todas** las palabras, que es como espera todo el mundo que
    funcione un buscador; después se premia el título sobre el cuerpo y que la
    palabra empiece el campo en vez de aparecer por el medio.
    """
    textos = [normalizar(c) for c in campos]
    total = 0.0
    for palabra in palabras:
        mejor = 0.0
        for i, texto in enumerate(textos):
            if palabra not in texto:
                continue
            # El primer campo es el título: vale más que el cuerpo
            valor = 1.0 / (i + 1)
            if texto.startswith(palabra):
                valor += 0.6
            elif re.search(rf"\b{re.escape(palabra)}", texto):
                valor += 0.3
            mejor = max(mejor, valor)
        if mejor == 0.0:
            return 0.0
        total += mejor
    return total


def _puntuar_amplio(palabras, *campos) -> tuple[float, bool]:
    """Coincidencia literal primero; conceptos y flexiones solo como respaldo."""
    exacto = _puntuar(palabras, *campos)
    if exacto:
        return exacto, False
    textos = [normalizar(c) for c in campos]
    tokens = [re.findall(r"[a-z0-9]+", t) for t in textos]
    total = 0.0
    for grupo in _grupos_semanticos(palabras):
        mejor = 0.0
        raices = {_raiz(x) for x in grupo}
        for i, (texto, suyos) in enumerate(zip(textos, tokens)):
            peso = 1.0 / (i + 1)
            if any(alt in texto for alt in grupo):
                mejor = max(mejor, peso)
                continue
            for token in suyos:
                rt = _raiz(token)
                if any(rt == r or (len(rt) >= 5 and (rt.startswith(r) or r.startswith(rt)))
                       for r in raices):
                    mejor = max(mejor, peso * 0.82)
                    break
        if not mejor:
            return 0.0, False
        total += mejor
    # Una relación nunca debe desplazar a una coincidencia literal equivalente.
    return total * 0.58, True


def _terminos_recorte(palabras) -> list[str]:
    return list(dict.fromkeys(x for p in palabras for x in _alternativas(p)))


def _recorte(texto: str, palabras, largo: int = 90) -> str:
    """Un trozo del texto alrededor de la primera palabra que encaje."""
    plano = util.plain(texto or "")
    if not plano:
        return ""
    plano_norm = normalizar(plano)
    terminos = _terminos_recorte(palabras)
    posicion = min((plano_norm.find(p) for p in terminos if p in plano_norm),
                   default=-1)
    if posicion < 0 or len(plano) <= largo:
        return plano[:largo] + ("…" if len(plano) > largo else "")
    inicio = max(0, posicion - largo // 3)
    trozo = plano[inicio:inicio + largo]
    return ("…" if inicio else "") + trozo + ("…" if inicio + largo < len(plano) else "")


# ------------------------------------------------------------- cada almacén

def _tarjetas(con, palabras, limite):
    filas = con.execute(
        """SELECT c.id, c.front, c.back, c.tags, c.level, c.kind,
                  d.name AS deck_name, d.icon AS deck_icon, d.levels AS deck_levels,
                  s.reps, s.leech
           FROM cards c JOIN decks d ON d.id = c.deck_id
           LEFT JOIN state s ON s.card_id = c.id""").fetchall()
    salida = []
    for f in filas:
        # El mazo va el último: buscar «inglés» saca sus tarjetas, pero pesa
        # menos que encontrar la palabra en el enunciado.
        puntos, relacionado = _puntuar_amplio(
            palabras, f["front"], f["back"], f["tags"], f["deck_name"])
        if not puntos:
            continue
        nivel = db.level_name(f["deck_levels"], f["level"])
        salida.append({
            "tipo": "tarjeta", "id": f["id"], "puntos": puntos,
            "titulo": util.plain(f["front"]),
            "detalle": _recorte(f["back"], palabras) or "sin respuesta",
            "contexto": f"{f['deck_icon']} {f['deck_name']} · {nivel}",
            "relacionado": relacionado,
        })
    return sorted(salida, key=lambda x: -x["puntos"])[:limite]


def _capitulos(con, palabras, limite):
    filas = con.execute(
        """SELECT c.id, c.title, c.subtitle, c.tags, c.level, c.body, c.propio,
                  d.name AS deck_name, d.icon AS deck_icon, d.levels AS deck_levels,
                  r.leido
           FROM chapters c JOIN decks d ON d.id = c.deck_id
           LEFT JOIN reading r ON r.chapter_id = c.id""").fetchall()
    salida = []
    for f in filas:
        cuerpo = db._texto_body(f["body"])
        puntos, relacionado = _puntuar_amplio(
            palabras, f["title"], f["subtitle"], f["tags"], cuerpo, f["deck_name"])
        if not puntos:
            continue
        nivel = db.level_name(f["deck_levels"], f["level"])
        marca = " · tuyo" if f["propio"] else ""
        salida.append({
            "tipo": "capitulo", "id": f["id"], "puntos": puntos,
            "titulo": f["title"],
            "detalle": _recorte(cuerpo, palabras),
            "contexto": f"{f['deck_icon']} {f['deck_name']} · {nivel}"
                        f"{' · leído' if f['leido'] else ''}{marca}",
            "relacionado": relacionado,
        })
    return sorted(salida, key=lambda x: -x["puntos"])[:limite]


def _libros(con, palabras, limite, catalogo=None):
    """Los libros que has abierto, más el catálogo del estante si lo hay.

    El catálogo se pasa desde fuera porque recorrer la carpeta cuesta segundos
    con mil libros, y la pestaña Biblioteca ya lo tiene cargado.
    """
    vistos, salida = set(), []
    for f in con.execute("SELECT * FROM books"):
        puntos, relacionado = _puntuar_amplio(palabras, f["titulo"], f["tema"])
        if not puntos:
            continue
        vistos.add(f["ruta"])
        avance = (f"pág. {f['pagina']} de {f['paginas']}" if f["paginas"]
                  else "sin abrir")
        salida.append({
            "tipo": "libro", "id": f["ruta"], "puntos": puntos + 0.4,
            "titulo": f["titulo"], "detalle": avance,
            "contexto": f["tema"] or "—",
            "relacionado": relacionado,
            "libro": {"ruta": f["ruta"], "nombre": f["titulo"], "tema": f["tema"],
                      "ext": f["ruta"].rsplit(".", 1)[-1].lower()},
        })
    for libro in (catalogo or []):
        if libro["ruta"] in vistos:
            continue
        puntos, relacionado = _puntuar_amplio(palabras, libro["nombre"], libro["tema"])
        if not puntos:
            continue
        salida.append({
            "tipo": "libro", "id": libro["ruta"], "puntos": puntos,
            "titulo": libro["nombre"], "detalle": "en el estante",
            "contexto": libro["tema"] or "—", "libro": libro,
            "relacionado": relacionado,
        })
    return sorted(salida, key=lambda x: -x["puntos"])[:limite]


def _notas(con, palabras, limite):
    filas = con.execute(
        """SELECT n.*, b.titulo FROM notas n
           LEFT JOIN books b ON b.ruta = n.ruta""").fetchall()
    salida = []
    for f in filas:
        puntos, relacionado = _puntuar_amplio(palabras, f["nota"], f["texto"])
        if not puntos:
            continue
        titulo = f["nota"] or util.plain(f["texto"])
        salida.append({
            "tipo": "nota", "id": f["id"], "puntos": puntos,
            "titulo": titulo[:110],
            "detalle": _recorte(f["texto"], palabras) if f["nota"] else "",
            "contexto": f"{f['titulo'] or f['ruta'].rsplit('/', 1)[-1]} · pág. {f['pagina']}",
            "libro": {"ruta": f["ruta"], "nombre": f["titulo"] or "",
                      "tema": "", "ext": f["ruta"].rsplit(".", 1)[-1].lower()},
            "pagina": f["pagina"],
            "relacionado": relacionado,
        })
    return sorted(salida, key=lambda x: -x["puntos"])[:limite]


# ------------------------------------------------------------------- la mezcla

def buscar(con, consulta: str, catalogo=None, limite: int = LIMITE_TOTAL) -> list[dict]:
    """Todo lo que encaja, de más a menos, mezclando los cuatro almacenes."""
    palabras = _palabras(consulta)
    if not palabras or len("".join(palabras)) < 2:
        return []
    resultados = (_tarjetas(con, palabras, LIMITE_POR_TIPO)
                  + _capitulos(con, palabras, LIMITE_POR_TIPO)
                  + _libros(con, palabras, LIMITE_POR_TIPO, catalogo)
                  + _notas(con, palabras, LIMITE_POR_TIPO))
    for r in resultados:
        r["puntos"] *= TIPOS[r["tipo"]]["peso"]
        r["icono"] = TIPOS[r["tipo"]]["icono"]
        r["etiqueta"] = (("Relacionado · " if r.get("relacionado") else "")
                         + TIPOS[r["tipo"]]["nombre"])
        if r.get("relacionado"):
            r["contexto"] = "Relacionado · " + r["contexto"]
    return sorted(resultados, key=lambda x: -x["puntos"])[:limite]


def recientes(con, cuantos: int = 6) -> list[dict]:
    """Qué ofrecer con el buscador recién abierto y todavía vacío.

    Lo último que estudiaste y lo último que leíste: casi siempre es a donde
    querías volver.
    """
    salida = []
    for f in con.execute(
            """SELECT c.id, c.front, d.name AS deck_name, d.icon AS deck_icon,
                      MAX(l.ts) AS cuando
               FROM log l JOIN cards c ON c.id = l.card_id
               JOIN decks d ON d.id = c.deck_id
               GROUP BY c.id ORDER BY cuando DESC LIMIT ?""", (cuantos,)):
        salida.append({"tipo": "tarjeta", "id": f["id"], "puntos": f["cuando"] or 0,
                       "titulo": util.plain(f["front"]), "detalle": "",
                       "contexto": f"{f['deck_icon']} {f['deck_name']}",
                       "icono": TIPOS["tarjeta"]["icono"],
                       "etiqueta": "Lo último que estudiaste"})
    for f in con.execute(
            "SELECT * FROM books WHERE abierto > 0 ORDER BY abierto DESC LIMIT ?",
            (max(1, cuantos // 2),)):
        salida.append({"tipo": "libro", "id": f["ruta"], "puntos": f["abierto"],
                       "titulo": f["titulo"],
                       "detalle": f"pág. {f['pagina']} de {f['paginas']}"
                                  if f["paginas"] else "",
                       "contexto": f["tema"] or "—",
                       "icono": TIPOS["libro"]["icono"],
                       "etiqueta": "Seguir leyendo",
                       "libro": {"ruta": f["ruta"], "nombre": f["titulo"],
                                 "tema": f["tema"],
                                 "ext": f["ruta"].rsplit(".", 1)[-1].lower()}})
    return sorted(salida, key=lambda x: -x["puntos"])[:cuantos]


def cuando(ts: float) -> str:
    if not ts:
        return ""
    pasado = time.time() - ts
    if pasado < 3600:
        return "hace un rato"
    if pasado < 86400:
        return f"hace {int(pasado / 3600)} h"
    return f"hace {int(pasado / 86400)} d"
