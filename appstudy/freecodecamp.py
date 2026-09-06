"""Integración con la plataforma freeCodeCamp (https://www.freecodecamp.org/).

Permite descargar lecciones, desafíos y cursos de freeCodeCamp a través de
Internet y generar automáticamente tarjetas de estudio (flashcards, retos quiz
y ejercicios cloze) mediante modelos de lenguaje (IA).
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import ia, util

TIMEOUT_HTTP = 15
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"

# Mapeo rápido de certificaciones a sus primeras lecciones o desafíos clave
# para evitar descargar archivos gigantes de índice (~15 MB).
SUPERBLOCK_PRIMERA_LECCION = {
    "scientific-computing-with-python": "https://www.freecodecamp.org/learn/scientific-computing-with-python/learn-string-manipulation-by-building-a-cipher/step-1",
    "data-analysis-with-python": "https://www.freecodecamp.org/learn/data-analysis-with-python/data-analysis-with-python-course/data-analysis-example-a",
    "machine-learning-with-python": "https://www.freecodecamp.org/learn/machine-learning-with-python/tensorflow/core-learning-algorithms",
    "responsive-web-design-v9": "https://www.freecodecamp.org/learn/2022/responsive-web-design/learn-basic-css-by-building-a-cafe-menu/step-1",
    "responsive-web-design": "https://www.freecodecamp.org/learn/2022/responsive-web-design/learn-basic-css-by-building-a-cafe-menu/step-1",
    "javascript-algorithms-and-data-structures-v8": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures-v8/learn-introductory-javascript-by-building-a-pyramid-generator/step-1",
    "javascript-algorithms-and-data-structures": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures-v8/learn-introductory-javascript-by-building-a-pyramid-generator/step-1",
    "front-end-development-libraries": "https://www.freecodecamp.org/learn/front-end-development-libraries/bootstrap/use-responsive-design-with-bootstrap-fluid-containers",
    "relational-database-v8": "https://www.freecodecamp.org/espanol/news/aprende-sql-curso-desde-cero-en-espanol/",
    "back-end-development-and-apis": "https://www.freecodecamp.org/learn/back-end-development-and-apis/managing-packages-with-npm/how-to-use-package-json-the-core-of-any-node-js-project-or-npm-package",
    "quality-assurance-v7": "https://www.freecodecamp.org/learn/quality-assurance/quality-assurance-and-testing-with-chai/learn-how-javascript-assertions-work",
    "information-security-v7": "https://www.freecodecamp.org/learn/information-security/information-security-with-helmetjs/install-and-require-helmet",
}

# Certificaciones y módulos principales del currículo de freeCodeCamp
CERTIFICACIONES = [
    {
        "id": "scientific-computing-with-python",
        "nombre": "Python: Cifrado y Cadenas (Scientific Computing)",
        "icono": "🐍",
        "slug": "scientific-computing-with-python",
        "url": "https://www.freecodecamp.org/learn/scientific-computing-with-python/learn-string-manipulation-by-building-a-cipher/step-1",
        "deck_sugerido": "python",
    },
    {
        "id": "scientific-computing-expense-tracker",
        "nombre": "Python: Funciones Lambda y Listas (Expense Tracker)",
        "icono": "🐍",
        "slug": "scientific-computing-with-python",
        "url": "https://www.freecodecamp.org/learn/scientific-computing-with-python/learn-lambda-functions-by-building-an-expense-tracker/step-1",
        "deck_sugerido": "python",
    },
    {
        "id": "data-analysis-with-python",
        "nombre": "Python: Análisis de Datos (Data Analysis Course)",
        "icono": "📊",
        "slug": "data-analysis-with-python",
        "url": "https://www.freecodecamp.org/learn/data-analysis-with-python/data-analysis-with-python-course/data-analysis-example-a",
        "deck_sugerido": "python",
    },
    {
        "id": "machine-learning-with-python",
        "nombre": "Machine Learning: TensorFlow y Redes Neuronales",
        "icono": "🤖",
        "slug": "machine-learning-with-python",
        "url": "https://www.freecodecamp.org/learn/machine-learning-with-python/tensorflow/core-learning-algorithms",
        "deck_sugerido": "ia",
    },
    {
        "id": "responsive-web-design-v9",
        "nombre": "Desarrollo Web: HTML y CSS (Responsive Design)",
        "icono": "🌐",
        "slug": "responsive-web-design-v9",
        "url": "https://www.freecodecamp.org/learn/2022/responsive-web-design/learn-basic-css-by-building-a-cafe-menu/step-1",
        "deck_sugerido": "datos",
    },
    {
        "id": "javascript-algorithms-and-data-structures-v8",
        "nombre": "JavaScript: Algoritmos y Estructuras de Datos",
        "icono": "⚡",
        "slug": "javascript-algorithms-and-data-structures-v8",
        "url": "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures-v8/learn-introductory-javascript-by-building-a-pyramid-generator/step-1",
        "deck_sugerido": "datos",
    },
    {
        "id": "front-end-development-libraries",
        "nombre": "Front End: Librerías y Componentes UI",
        "icono": "⚛️",
        "slug": "front-end-development-libraries",
        "url": "https://www.freecodecamp.org/learn/front-end-development-libraries/bootstrap/use-responsive-design-with-bootstrap-fluid-containers",
        "deck_sugerido": "datos",
    },
    {
        "id": "relational-database-v8",
        "nombre": "Bases de Datos Relacionales (SQL y Bash)",
        "icono": "🗄️",
        "slug": "relational-database-v8",
        "url": "https://www.freecodecamp.org/espanol/news/aprende-sql-curso-desde-cero-en-espanol/",
        "deck_sugerido": "linux",
    },
    {
        "id": "back-end-development-and-apis",
        "nombre": "Back End Development y APIs (Node & Express)",
        "icono": "🛠️",
        "slug": "back-end-development-and-apis",
        "url": "https://www.freecodecamp.org/learn/back-end-development-and-apis/managing-packages-with-npm/how-to-use-package-json-the-core-of-any-node-js-project-or-npm-package",
        "deck_sugerido": "linux",
    },
    {
        "id": "quality-assurance-v7",
        "nombre": "Quality Assurance y Pruebas Unitarias (Chai)",
        "icono": "🧪",
        "slug": "quality-assurance-v7",
        "url": "https://www.freecodecamp.org/learn/quality-assurance/quality-assurance-and-testing-with-chai/learn-how-javascript-assertions-work",
        "deck_sugerido": "datos",
    },
    {
        "id": "information-security-v7",
        "nombre": "Seguridad Informática (HelmetJS & PenTesting)",
        "icono": "🔒",
        "slug": "information-security-v7",
        "url": "https://www.freecodecamp.org/learn/information-security/information-security-with-helmetjs/install-and-require-helmet",
        "deck_sugerido": "linux",
    },
]


class FCCError(RuntimeError):
    """Error al conectar o procesar material de freeCodeCamp."""


def normalizar_url(url_o_slug: str) -> str:
    """Normaliza un slug o URL hacia una URL canónica de freeCodeCamp."""
    texto = url_o_slug.strip()
    if not texto:
        raise FCCError("La URL o slug de freeCodeCamp no puede estar vacío.")
    if texto.startswith("http://") or texto.startswith("https://"):
        return texto
    if texto.startswith("/"):
        return f"https://www.freecodecamp.org{texto}"
    # Si es solo el identificador de una certificación o bloque
    return f"https://www.freecodecamp.org/learn/{texto}/"


def _limpiar_html_fcc(texto_html: str) -> str:
    """Convierte el HTML de lecciones de freeCodeCamp en texto limpio con código."""
    if not texto_html:
        return ""
    # Preservar bloques de código con marcas claras
    t = re.sub(r"<pre><code[^>]*>(.*?)</code></pre>", r"\n```\n\1\n```\n", texto_html, flags=re.S)
    t = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", t, flags=re.S)
    # Convertir listas
    t = re.sub(r"<li[^>]*>(.*?)</li>", r"• \1\n", t, flags=re.S)
    # Convertir títulos y párrafos
    t = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n### \1\n", t, flags=re.S)
    t = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", t, flags=re.S)
    t = re.sub(r"<br\s*/?>", r"\n", t)
    # Eliminar cualquier etiqueta restante
    t = re.sub(r"<[^>]+>", "", t)
    # Decodificar entidades HTML y normalizar espacios
    t = html.unescape(t)
    lineas = [l.rstrip() for l in t.splitlines()]
    res = "\n".join(lineas)
    return re.sub(r"\n{3,}", "\n\n", res).strip()


def _peticion_http(url: str) -> str | bytes:
    """Realiza una petición GET segura con User-Agent y timeout."""
    peticion = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_HTTP) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise FCCError(f"freeCodeCamp respondió con error {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise FCCError(f"No se pudo conectar con freeCodeCamp ({e.reason}). ¿Hay conexión a Internet?") from e
    except TimeoutError as e:
        raise FCCError(f"Tiempo de espera agotado conectando con freeCodeCamp ({TIMEOUT_HTTP} s).") from e


def obtener_leccion(url_o_slug: str) -> dict:
    """Descarga y extrae la información de una lección o página de freeCodeCamp.

    Devuelve un diccionario estructurado:
    - 'titulo': nombre del desafío o lección
    - 'bloque': nombre del módulo/sección
    - 'super_bloque': certificación
    - 'descripcion': explicación didáctica en texto claro
    - 'instrucciones': instrucciones del reto
    - 'fuente': URL original
    - 'texto_para_ia': bloque completo preparado para el generador
    """
    url = normalizar_url(url_o_slug)
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")

    # Portada general o selector de idioma -> lección introductoria de Python
    if path in ("", "/", "/espanol", "/espanol/"):
        return obtener_leccion(SUPERBLOCK_PRIMERA_LECCION["scientific-computing-with-python"])

    # Caso 1: Ruta dentro del currículo /learn/ (usa API page-data de Gatsby)
    match_learn = re.search(r"(?:^|/)(?:[a-z]{2,8}/)?learn(?:/(.*))?$", path)
    if match_learn:
        sub = (match_learn.group(1) or "").strip("/")
        partes = [p for p in sub.split("/") if p]

        # Si apunta a la raíz del currículo o a un superBlock completo,
        # resolver directamente a su lección/desafío clave para evitar
        # descargar el índice de 15 MB.
        if len(partes) <= 1:
            sb = partes[0] if partes else "scientific-computing-with-python"
            url_leccion = SUPERBLOCK_PRIMERA_LECCION.get(
                sb, SUPERBLOCK_PRIMERA_LECCION["scientific-computing-with-python"])
            if url_leccion != url:
                return obtener_leccion(url_leccion)

        # Es una lección o paso específico: descargar el page-data ligero (~4 KB)
        ruta_api = f"https://www.freecodecamp.org/page-data/learn/{'/'.join(partes)}/page-data.json"
        try:
            datos_raw = _peticion_http(ruta_api)
            data = json.loads(datos_raw.decode("utf-8"))
            result = data.get("result", {}).get("data", {})
            challenge_node = result.get("challengeNode", {})
            challenge = challenge_node.get("challenge", {})

            if challenge:
                titulo = challenge.get("title") or "Lección de freeCodeCamp"
                bloque = challenge.get("block") or "general"
                super_bloque = challenge.get("superBlock") or "freecodecamp"
                desc_html = challenge.get("description", "")
                inst_html = challenge.get("instructions", "")

                desc = _limpiar_html_fcc(desc_html)
                inst = _limpiar_html_fcc(inst_html)

                # Extraer posibles criterios de pruebas/tests
                tests = challenge.get("tests", [])
                textos_tests = []
                for test in tests:
                    t_text = test.get("text", "")
                    if t_text:
                        textos_tests.append(f"- {_limpiar_html_fcc(t_text)}")

                cuerpo_ia = [f"Título: {titulo}", f"Módulo: {bloque}"]
                if desc:
                    cuerpo_ia.append(f"Explicación:\n{desc}")
                if inst:
                    cuerpo_ia.append(f"Instrucciones prácticas:\n{inst}")
                if textos_tests:
                    cuerpo_ia.append("Criterios de verificación y comportamiento:\n" + "\n".join(textos_tests[:5]))

                return {
                    "titulo": titulo,
                    "bloque": bloque,
                    "super_bloque": super_bloque,
                    "descripcion": desc,
                    "instrucciones": inst,
                    "fuente": url,
                    "texto_para_ia": "\n\n".join(cuerpo_ia),
                }
        except (FCCError, json.JSONDecodeError):
            pass

    # Caso 2: Páginas de artículos, noticias o tutoriales HTML directo
    raw_html = _peticion_http(url).decode("utf-8", errors="ignore")
    titulo_match = re.search(r"<h1[^>]*class=[\"\x27][^\"]*post-full-title[^\"]*[\"\x27][^>]*>(.*?)</h1>", raw_html, re.I | re.S)
    if not titulo_match:
        titulo_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_html, re.I | re.S)
    if not titulo_match:
        titulo_match = re.search(r"<title>(.*?)(?:\s*[-|–]\s*freeCodeCamp)?</title>", raw_html, re.I | re.S)
    titulo = html.unescape(re.sub(r"<[^>]+>", "", titulo_match.group(1)).strip()) if titulo_match else "freeCodeCamp"

    # Buscar cuerpo principal del artículo o contenido
    cuerpo_match = re.search(r"<div[^>]*class=[\"\x27][^\"]*post-content[^\"]*[\"\x27][^>]*>(.*?)</div>\s*<(?:footer|section|div)", raw_html, re.I | re.S)
    if not cuerpo_match:
        cuerpo_match = re.search(r"<section[^>]*class=[\"\x27][^\"]*post-full-content[^\"]*[\"\x27][^>]*>(.*?)</section>", raw_html, re.I | re.S)
    if not cuerpo_match:
        cuerpo_match = re.search(r"<article[^>]*>(.*?)</article>", raw_html, re.I | re.S)
    if not cuerpo_match:
        cuerpo_match = re.search(r"<main[^>]*>(.*?)</main>", raw_html, re.I | re.S)
    cuerpo_html = cuerpo_match.group(1) if cuerpo_match else raw_html

    desc = _limpiar_html_fcc(cuerpo_html)
    if len(desc) > 6000:
        desc = desc[:6000] + "\n\n[...contenido resumido para estudio...]"

    return {
        "titulo": titulo,
        "bloque": "tutorial",
        "super_bloque": "freecodecamp",
        "descripcion": desc,
        "instrucciones": "",
        "fuente": url,
        "texto_para_ia": f"Título: {titulo}\n\n{desc}",
    }


def listar_certificaciones() -> list[dict]:
    """Devuelve el catálogo de certificaciones disponibles con sus metadatos."""
    return CERTIFICACIONES


def generar_tarjetas_fcc(cfg: dict, leccion: dict, cuantas: int = 5,
                         nivel: str = "Intermedio") -> list[dict]:
    """Genera tarjetas de estudio a partir del material descargado de freeCodeCamp.

    Produce una combinación didáctica de preguntas directas, retos quiz con
    opciones múltiples y ejercicios cloze (rellenar huecos) de sintaxis.
    """
    if not cfg.get("activa"):
        raise FCCError("La IA está desactivada. Actívala en Ajustes de AppStudy para generar tarjetas.")

    titulo = leccion.get("titulo", "freeCodeCamp")
    bloque = leccion.get("bloque", "fcc")
    texto = leccion.get("texto_para_ia", "")

    if not texto.strip():
        raise FCCError("El material extraído de freeCodeCamp no contiene texto suficiente.")

    usuario = (
        f"Eres un tutor experto creando tarjetas de estudio sobre este contenido de freeCodeCamp:\n"
        f"«{titulo}» ({bloque})\n\n"
        f"---\n{texto}\n---\n\n"
        f"Genera exactamente {cuantas} tarjetas de estudio de nivel {nivel} "
        f"**basándote estrictamente en este material de freeCodeCamp**.\n"
        "Reglas:\n"
        "1. Pregunta por conceptos clave, sintaxis de código, métodos y reglas prácticas.\n"
        "2. Usa etiquetas HTML permitidas para dar formato claro al código: <code>...</code> y <b>...</b>.\n"
        "3. En 'front' formula una pregunta directa y clara.\n"
        "4. En 'back' proporciona una respuesta concisa, pedagógica y precisa (dos a tres frases con ejemplo si aplica).\n"
        "5. Responde exclusivamente con un objeto JSON en el formato requerido."
    )

    crudo = ia._mensaje(
        cfg,
        [{"role": "system", "content": ia.SISTEMA}, {"role": "user", "content": usuario}],
        formato=ia.ESQUEMA_TARJETAS,
        temperatura=0.5,
        keep_alive=ia.KEEP_ALIVE_ONESHOT
    )

    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        trozo = re.search(r"\{.*\}", crudo, re.S)
        if not trozo:
            raise FCCError("La IA no devolvió un formato JSON reconocible.") from None
        datos = json.loads(trozo.group(0))

    salida = []
    tag_modulo = re.sub(r"[^a-z0-9_]+", "-", bloque.lower()).strip("-")
    etiquetas = f"freecodecamp, {tag_modulo}" if tag_modulo else "freecodecamp"

    for t in datos.get("tarjetas", []):
        frente = str(t.get("front", "")).strip()
        dorso = str(t.get("back", "")).strip()
        if frente and dorso:
            salida.append({
                "kind": "card",
                "front": ia._limpiar(frente),
                "back": ia._limpiar(dorso),
                "tags": etiquetas,
                "level": 2,
            })

    if not salida:
        raise FCCError("La IA no pudo extraer ninguna tarjeta válida de esta lección.")

    return salida


def leccion_a_markdown(leccion: dict, deck_key: str = "python", nivel: int = 1) -> str:
    """Genera un archivo Markdown con cabecera y cuerpo formateado para el lector."""
    titulo = leccion.get("titulo", "Lección de freeCodeCamp")
    bloque = leccion.get("bloque", "general")
    tag_modulo = re.sub(r"[^a-z0-9_]+", "-", bloque.lower()).strip("-")
    etiquetas = f"freecodecamp, {tag_modulo}" if tag_modulo else "freecodecamp"
    subtitulo = f"freeCodeCamp · {bloque}"

    lineas = [
        "---",
        f"mazo: {deck_key}",
        f"nivel: {nivel}",
        f"subtitulo: {subtitulo}",
        f"etiquetas: {etiquetas}",
        "---",
        "",
        f"# {titulo}",
        "",
        leccion.get("descripcion", "").strip(),
    ]

    instrucciones = leccion.get("instrucciones", "").strip()
    if instrucciones:
        lineas.extend([
            "",
            "## Instrucciones y Desafío",
            "",
            instrucciones,
        ])

    return "\n".join(lineas).strip() + "\n"


def guardar_como_lectura(con, leccion: dict, deck_id: int, deck_key: str, nivel: int = 1) -> dict:
    """Guarda la lección de freeCodeCamp como un capítulo propio para leerlo en AppStudy."""
    from . import db, lecturas
    md = leccion_a_markdown(leccion, deck_key=deck_key, nivel=nivel)
    cap = lecturas.analizar(md)
    cap["fuente"] = leccion.get("fuente", "")
    cap["propio"] = True

    cid, uid = db.upsert_chapter(con, deck_id, deck_key, cap)
    lecturas.guardar(cap["title"], md)
    con.commit()

    cap_db = db.chapter_by_id(con, cid)
    return cap_db if cap_db else cap
