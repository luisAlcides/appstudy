"""Conectores de contenido. Buscar/previsualizar no modifica la base de datos."""
from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request

from . import db, lecturas

MAX_TEXTO = 4 * 1024 * 1024
MAX_DESCARGA = 100 * 1024 * 1024
MAX_DOCUMENTOS = 1000
VERSION = "1.0.0"

CATALOGOS = {
    "openstax": [
        ("Cálculo volumen 1 · español", "https://openstax.org/books/cálculo-volumen-1/pages/prefacio"),
        ("Calculus Volume 1 · inglés", "https://openstax.org/books/calculus-volume-1/pages/preface"),
        ("Calculus Volume 1 · PDF", "https://assets.openstax.org/oscms-prodcms/media/documents/calculus-volume-1_-_WEB.pdf"),
        ("Introductory Statistics 2e", "https://openstax.org/books/introductory-statistics-2e/pages/preface"),
        ("University Physics Volume 2 · electricidad", "https://openstax.org/books/university-physics-volume-2/pages/preface"),
        ("College Physics 2e", "https://openstax.org/books/college-physics-2e/pages/preface"),
    ],
    "mit": [
        ("Python · Introducción a la programación", "https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/download/"),
        ("Cálculo de una variable", "https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/download/"),
        ("Álgebra lineal", "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/download/"),
        ("Circuitos y electrónica", "https://ocw.mit.edu/courses/6-002-circuits-and-electronics-spring-2007/download/"),
    ],
}
DOMINIOS = {"wikipedia": {"es.wikipedia.org", "en.wikipedia.org"},
            "openstax": {"openstax.org", "assets.openstax.org"},
            "mit": {"ocw.mit.edu", "live.ocw.mit.edu"}}


def _registrar_catalogo():
    """Cada fuente del catálogo es también un proveedor con su lista blanca.

    Se hace aquí y no en `catalogo.py` para no invertir la dependencia: el
    catálogo son datos y no tiene por qué saber nada de descargas.
    """
    from . import catalogo
    for f in catalogo.FUENTES:
        DOMINIOS.setdefault(f["id"], set()).update(f["hosts"])


_registrar_catalogo()


class FuenteError(ValueError):
    pass


def clave(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold())
                   if unicodedata.category(c) != "Mn")


def validar_url(url, dominios):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != "https" or p.hostname not in dominios or p.username or
            p.password or p.port not in (None, 443)):
        raise FuenteError("La dirección debe ser HTTPS y pertenecer a la fuente seleccionada")
    return urllib.parse.quote(url, safe=":/?=&%#@+;,~-._")


def descargar(url, dominios, limite=MAX_TEXTO):
    """Límite también sobre el cuerpo, y comprobación de cada redirección."""
    class Redireccion(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return super().redirect_request(req, fp, code, msg, headers,
                                            validar_url(newurl, dominios))
    url = validar_url(url, dominios)
    req = urllib.request.Request(url, headers={
        "User-Agent": "AppStudy/1.0 (educational desktop reader)",
        "Accept": "application/json,text/html,application/pdf;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.build_opener(Redireccion()).open(req, timeout=25) as r:
            datos = r.read(limite + 1)
            if len(datos) > limite:
                raise FuenteError("El recurso supera el tamaño permitido")
            return datos, r.headers.get_content_type()
    except (OSError, TimeoutError) as e:
        raise FuenteError(f"No se pudo consultar la fuente: {e}") from e


class Pagina(HTMLParser):
    """Texto y enlaces sin scripts, navegación ni contenido ejecutable."""
    def __init__(self, texto):
        super().__init__(convert_charrefs=True)
        self.partes, self.principal, self.enlaces = [], [], []
        self.omitir = 0
        self.main = 0
        self.titulo = []
        self.en_titulo = False
        self.enlace = None
        self.autores = []
        self.licencias = []
        self.feed(texto)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "citation_author" and a.get("content"):
            self.autores.append(a["content"])
        if tag == "a" and "creativecommons.org/licenses/" in a.get("href", ""):
            self.licencias.append(a["href"])
        if tag in ("script", "style", "nav", "header", "footer"):
            self.omitir += 1
        if tag in ("main", "article"):
            self.main += 1
        if tag == "title":
            self.en_titulo = True
        if not self.omitir:
            if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "section"):
                self.handle_data("\n")
            if tag == "a":
                self.enlace = [a.get("href", ""), []]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "header", "footer"):
            self.omitir = max(0, self.omitir - 1)
        if tag in ("main", "article"):
            self.main = max(0, self.main - 1)
        if tag == "title":
            self.en_titulo = False
        if tag == "a" and self.enlace:
            self.enlaces.append((self.enlace[0], "".join(self.enlace[1]).strip()))
            self.enlace = None
        if tag in ("p", "li", "h1", "h2", "h3"):
            self.handle_data("\n")

    def handle_data(self, data):
        if self.en_titulo:
            self.titulo.append(data)
        if not self.omitir:
            self.partes.append(data)
            if self.main:
                self.principal.append(data)
            if self.enlace:
                self.enlace[1].append(data)

    @property
    def texto(self):
        texto = "".join(self.principal or self.partes)
        return "\n".join(re.sub(r"[ \t]+", " ", l).strip()
                         for l in texto.splitlines() if l.strip())


def documento(provider, origin, title, text="", **extra):
    return {"provider": provider, "origin": origin, "title": title,
            "text": text, "author": "", "license": "No indicada; consultar la fuente",
            "retrieved": time.time(), **extra}


CADUCIDAD_INDICE = 30 * 86400
MAX_INDICE = 20 * 1024 * 1024          # el sitemap de LibreTexts pasa de 3 MB
MAX_POR_INDICE = 200

# Páginas de servicio: existen en todo wiki y en todo manual, y no son material
# de estudio en ninguno
_RUIDO = ("Special:", "Talk:", "Template:", "Category:", "Help:", "Sandbox",
          "/index", "/search", "/login", "/genindex", "/_sources/")


def _indice_paginas(f, raw):
    """Convierte un sitemap XML o una página índice en pares (título, URL)."""
    if f["buscar"] == "sitemap":
        import xml.etree.ElementTree as ET
        try:
            raiz = ET.fromstring(raw.decode("utf-8", errors="replace"))
        except ET.ParseError as e:
            raise FuenteError(f"{f['nombre']} devolvió un sitemap ilegible") from e
        urls = [n.text.strip() for n in raiz.iter()
                if n.tag.endswith("}loc") and n.text and n.text.strip()]
        pares = [(urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1]).replace("_", " "), u)
                 for u in urls]
    else:
        pagina = Pagina(raw.decode("utf-8", errors="replace"))
        pares = [(" ".join(titulo.split()),
                  urllib.parse.urljoin(f["base"], href).split("#")[0])
                 for href, titulo in pagina.enlaces if titulo and titulo.strip()]
    salida, vistos = [], set()
    for titulo, url in pares:
        if not titulo or url in vistos or any(r in url for r in _RUIDO):
            continue
        try:
            validar_url(url, DOMINIOS[f["id"]])
        except ValueError:
            continue                       # otro dominio: fuera de la lista blanca
        vistos.add(url)
        salida.append([titulo, url])
    return salida


def indice(f, consulta="", refrescar=False):
    """Las páginas de una fuente sin buscador, desde su índice y con caché.

    El índice se guarda un mes. Si la descarga falla pero hay copia, se usa la
    copia: quedarse sin sugerencias por estar sin red sería peor que servir un
    índice de hace tres semanas.
    """
    carpeta = db.DATA_DIR / "fuentes" / "indices"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / (f["id"] + ".json")
    guardado = None
    if ruta.exists():
        try:
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
        except ValueError:
            guardado = None
    vigente = bool(guardado) and time.time() - guardado.get("ts", 0) < CADUCIDAD_INDICE
    if vigente and not refrescar:
        pares = guardado["items"]
    else:
        url = f["base"] + "/sitemap.xml" if f["buscar"] == "sitemap" else f["base"]
        try:
            raw, _ = descargar(url, DOMINIOS[f["id"]], MAX_INDICE)
            pares = _indice_paginas(f, raw)
            ruta.write_text(json.dumps({"ts": time.time(), "items": pares},
                                       ensure_ascii=False), encoding="utf-8")
        except (FuenteError, OSError, ValueError):
            if not guardado:
                raise
            pares = guardado["items"]
    terminos = clave(consulta).split()
    return [documento(f["id"], url, titulo, summary=f["nombre"])
            for titulo, url in pares
            if all(t in clave(titulo) for t in terminos)][:MAX_POR_INDICE]


def _mediawiki(f, consulta, corto=False):
    """Wikipedia, Wikilibros, Wikiversidad, Wiktionary, ArchWiki y Gentoo.

    ArchWiki y Gentoo montan la API en la raíz y los artículos en /title/; los
    proyectos de Wikimedia usan /w y /wiki. Por lo demás es la misma API, así
    que siete fuentes salen de un conector.
    """
    prefijo, articulo = ("", "/title/") if corto else ("/w", "/wiki/")
    url = (f["base"] + prefijo + "/rest.php/v1/search/page?" +
           urllib.parse.urlencode({"q": consulta, "limit": 15}))
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        paginas = json.loads(raw)["pages"]
    except (KeyError, TypeError, ValueError) as e:
        raise FuenteError(f"{f['nombre']} devolvió una respuesta no reconocible") from e
    return [documento(f["id"], f["base"] + articulo + urllib.parse.quote(p["key"]),
                      p["title"], summary=Pagina(p.get("excerpt", "")).texto)
            for p in paginas if p.get("key")]


def _arxiv(f, consulta):
    """Resúmenes, nunca el PDF: la licencia de arXiv cambia con cada artículo."""
    import xml.etree.ElementTree as ET
    url = f["base"] + "/api/query?" + urllib.parse.urlencode(
        {"search_query": "all:" + consulta, "max_results": 10})
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        raiz = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except ET.ParseError as e:
        raise FuenteError("arXiv devolvió una respuesta no reconocible") from e
    ns = {"a": "http://www.w3.org/2005/Atom"}
    salida = []
    for e in raiz.findall("a:entry", ns):
        ident = (e.findtext("a:id", "", ns) or "").strip()
        titulo = " ".join((e.findtext("a:title", "", ns) or "").split())
        resumen = " ".join((e.findtext("a:summary", "", ns) or "").split())
        autores = [a.findtext("a:name", "", ns) or "" for a in e.findall("a:author", ns)]
        if ident and titulo:
            salida.append(documento(f["id"], ident, titulo, summary=resumen,
                                    author=", ".join(filter(None, autores)),
                                    license="Licencia propia de cada artículo · véase arXiv"))
    return salida


def _mdn(f, consulta):
    url = f["base"] + "/api/v1/search?" + urllib.parse.urlencode(
        {"q": consulta, "locale": "es"})
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        docs = json.loads(raw)["documents"]
    except (KeyError, TypeError, ValueError) as e:
        raise FuenteError("MDN devolvió una respuesta no reconocible") from e
    return [documento(f["id"], f["base"] + d["mdn_url"], d.get("title", d["mdn_url"]),
                      summary=d.get("summary", ""),
                      author="Colaboradores de MDN", license="CC BY-SA 2.5 · MDN")
            for d in docs if d.get("mdn_url")]


def _gutendex(f, consulta):
    """Solo los libros con texto plano: un EPUB no se lee en un capítulo."""
    url = f["base"] + "/books/?" + urllib.parse.urlencode({"search": consulta})
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        libros = json.loads(raw)["results"]
    except (KeyError, TypeError, ValueError) as e:
        raise FuenteError("Project Gutenberg devolvió una respuesta no reconocible") from e
    salida = []
    for libro in libros:
        texto = next((v for k, v in (libro.get("formats") or {}).items()
                      if k.startswith("text/plain")), "")
        if texto and libro.get("title"):
            salida.append(documento(
                f["id"], texto, libro["title"],
                author=", ".join(a.get("name", "") for a in libro.get("authors", [])),
                license="Dominio público · Project Gutenberg",
                summary="Libro completo en texto plano"))
    return salida


def buscar(provider, consulta="", config=None):
    config = config or {}
    from . import catalogo
    f = catalogo._POR_ID.get(provider)
    # Las de tipo «catalogo» —OpenStax y MIT— ya tenían su rama más abajo, con
    # su lista escrita a mano. No se toca: la ventana de Fuentes depende de ella.
    if f is not None and f["buscar"] != "catalogo":
        if not consulta.strip():
            return []
        if consulta.startswith("https://"):
            validar_url(consulta, DOMINIOS[provider])
            return [documento(provider, consulta,
                              urllib.parse.unquote(consulta.rsplit("/", 1)[-1]) or f["nombre"])]
        modo = f["buscar"]
        if modo == "mediawiki":
            return _mediawiki(f, consulta)
        if modo == "mediawiki_corto":
            return _mediawiki(f, consulta, corto=True)
        if modo == "arxiv":
            return _arxiv(f, consulta)
        if modo == "mdn":
            return _mdn(f, consulta)
        if modo == "gutendex":
            return _gutendex(f, consulta)
        return indice(f, consulta)
    if provider == "wikipedia":
        idioma = config.get("idioma", "es")
        if idioma not in ("es", "en"):
            raise FuenteError("Elige español o inglés")
        if not consulta.strip():
            return []
        base = f"https://{idioma}.wikipedia.org"
        url = base + "/w/rest.php/v1/search/page?" + urllib.parse.urlencode({"q": consulta, "limit": 15})
        raw, _ = descargar(url, DOMINIOS[provider])
        try:
            pages = json.loads(raw)["pages"]
            return [documento(provider, base + "/wiki/" + urllib.parse.quote(p["key"]),
                              p["title"], summary=Pagina(p.get("excerpt", "")).texto)
                    for p in pages]
        except (KeyError, TypeError, ValueError) as e:
            raise FuenteError("Wikipedia devolvió una respuesta no reconocible") from e
    if provider in CATALOGOS:
        if consulta.startswith("https://"):
            validar_url(consulta, DOMINIOS[provider])
            return [documento(provider, consulta, urllib.parse.unquote(consulta.rsplit("/", 1)[-1]) or provider)]
        terminos = clave(consulta).split()
        return [documento(provider, url, title, summary="Catálogo seleccionado · abre para explorar sus materiales")
                for title, url in CATALOGOS[provider]
                if all(p in clave(title) for p in terminos)]
    if provider == "markdown":
        return explorar_carpeta(config.get("carpeta", ""), consulta)
    raise FuenteError("Fuente no reconocida")


def previsualizar(item):
    provider, url = item["provider"], item["origin"]
    if provider == "markdown":
        p = Path(url)
        if p.stat().st_size > MAX_TEXTO:
            raise FuenteError("El documento supera 4 MB")
        texto = p.read_text(encoding="utf-8-sig")
        titulo, _ = lecturas.a_bloques(lecturas.cabecera(texto)[1])
        return {**item, "text": texto, "title": titulo or p.stem, "retrieved": time.time()}
    if provider not in DOMINIOS:
        return validar_documento(item)
    if urllib.parse.urlsplit(url).path.lower().endswith(".pdf"):
        return {**item, "format": "pdf", "text": "", "links": []}
    raw, _ = descargar(url, DOMINIOS[provider])
    page = Pagina(raw.decode("utf-8", errors="replace"))
    links, seen = [], set()
    for href, title in page.enlaces:
        target = urllib.parse.urljoin(url, href).split("#")[0]
        try:
            validar_url(target, DOMINIOS[provider])
        except ValueError:
            continue
        path = urllib.parse.urlsplit(target).path
        if (not title or target in seen or target == url or
                not (path.endswith(".pdf") or (provider == "mit" and "/courses/" in path)
                     or (provider == "openstax" and "/books/" in path))):
            continue
        seen.add(target)
        links.append(documento(provider, target, title))
    licencias = {"wikipedia": "CC BY-SA 4.0 · véase el historial y la licencia del artículo",
                 "mit": "Consultar licencia MIT OCW y excepciones de cada material",
                 "openstax": "Consultar licencia de esta edición en la fuente"}
    autores = {"wikipedia": "Colaboradores de Wikipedia", "mit": "MIT OpenCourseWare",
               "openstax": "OpenStax · autores indicados en el libro"}
    if page.licencias:
        licencias[provider] = page.licencias[0]
    for link in links:
        link["author"] = ", ".join(page.autores) or autores[provider]
        link["license"] = licencias[provider] + " · comprobar excepciones del material"
    if not page.texto.strip():
        raise FuenteError("Esta página no ofrece texto descargable. Usa un PDF o una página de capítulo.")
    return {**item, "title": "".join(page.titulo).strip() or item["title"],
            "text": page.texto, "author": ", ".join(page.autores) or autores[provider], "license": licencias[provider],
            "links": links[:150], "retrieved": time.time()}


def descargar_pdf(item):
    datos, _ = descargar(item["origin"], DOMINIOS[item["provider"]], MAX_DESCARGA)
    if not datos.startswith(b"%PDF-"):
        raise FuenteError("La fuente no devolvió un PDF válido")
    carpeta = db.DATA_DIR / "fuentes" / "libros"
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / (hashlib.sha256(datos).hexdigest() + ".pdf")
    if not destino.exists():
        with tempfile.NamedTemporaryFile(dir=carpeta, delete=False) as f:
            temporal = Path(f.name)
            f.write(datos)
        try:
            temporal.replace(destino)
        finally:
            temporal.unlink(missing_ok=True)
    # La atribución acompaña al archivo incluso fuera de la base de datos.
    metadata = {k: item.get(k, "") for k in ("provider", "origin", "title", "author", "license")}
    metadata["downloaded"] = time.time()
    destino.with_suffix(".source.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(destino)


def explorar_carpeta(ruta, consulta=""):
    if not ruta or not Path(ruta).is_dir():
        raise FuenteError("Configura una carpeta de apuntes Markdown")
    raiz = Path(ruta).resolve()
    salida = []
    for base, dirs, archivos in os.walk(raiz, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (Path(base) / d).is_symlink())
        for nombre in sorted(archivos):
            p = Path(base) / nombre
            if p.suffix.lower() not in (".md", ".markdown") or p.is_symlink():
                continue
            if not p.resolve().is_relative_to(raiz) or p.stat().st_size > MAX_TEXTO:
                continue
            if not all(t in clave(str(p.relative_to(raiz))) for t in clave(consulta).split()):
                continue
            salida.append(documento("markdown", str(p.resolve()), p.stem,
                                     summary=str(p.relative_to(raiz))))
            if len(salida) >= MAX_DOCUMENTOS:
                return salida
    return salida


def validar_documento(item):
    if not isinstance(item, dict):
        raise FuenteError("Documento no válido")
    for k in ("provider", "origin", "title", "text"):
        if not isinstance(item.get(k), str) or (k != "text" and not item[k].strip()):
            raise FuenteError(f"Falta el campo {k} del documento")
    if len(item["text"].encode()) > MAX_TEXTO:
        raise FuenteError("El documento supera 4 MB")
    if len(item["title"]) > 1000 or len(item["origin"]) > 4000:
        raise FuenteError("Título o dirección demasiado largos")
    for k in ("author", "license"):
        if not isinstance(item.get(k, ""), str):
            raise FuenteError(f"Metadato {k} no válido")
    return item


def huella(item):
    return hashlib.sha256(item["text"].encode()).hexdigest()


def estado(con, item, deck_id):
    row = con.execute("SELECT fingerprint,chapter_id FROM source_imports WHERE provider=? AND origin=? AND deck_id=?",
                      (item["provider"], item["origin"], deck_id)).fetchone()
    if not row or not row["chapter_id"]:
        return "nuevo"
    return "sin cambios" if row["fingerprint"] == huella(item) else "actualizado"


def importar(con, item, deck, commit=True):
    """Actualiza por origen y mazo; conserva la identidad y el progreso."""
    validar_documento(item)
    if not item["text"].strip():
        raise FuenteError("Selecciona un capítulo con texto o descarga el PDF")
    anterior = con.execute("SELECT chapter_id FROM source_imports WHERE provider=? AND origin=? AND deck_id=?",
                           (item["provider"], item["origin"], deck["id"])).fetchone()
    previa = db.chapter_by_id(con, anterior["chapter_id"]) if anterior and anterior["chapter_id"] else None
    if previa and estado(con, item, deck["id"]) == "sin cambios":
        return previa
    ident = hashlib.sha256((item["provider"] + item["origin"]).encode()).hexdigest()[:8]
    title = previa["title"] if previa else f"{item['title']} · {ident}"
    cuerpo = lecturas.cabecera(item["text"])[1] if item["provider"] == "markdown" else item["text"]
    _, bloques = lecturas.a_bloques(cuerpo)
    atribucion = (f"Fuente: {item['origin']}\nAutor: {item.get('author') or 'No indicado'}\n"
                  f"Licencia: {item.get('license') or 'Consultar la fuente'}\n"
                  f"Importado: {time.strftime('%Y-%m-%d')}")
    bloques.append({"note": html.escape(atribucion)})
    cid, _ = db.upsert_chapter(con, deck["id"], deck["key"], {
        "title": title, "body": bloques, "propio": True, "tags": f"fuente-{ident}",
        "minutes": max(1, len(cuerpo.split()) // 190), "level": previa["level"] if previa else 1,
        "pos": previa["pos"] if previa else 0, "subtitle": item.get("author", ""),
    })
    metadata = {k: item.get(k, "") for k in ("title", "author", "license", "origin", "retrieved")}
    con.execute("""INSERT INTO source_imports VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(provider,origin,deck_id) DO UPDATE SET chapter_id=excluded.chapter_id,
        fingerprint=excluded.fingerprint,metadata=excluded.metadata,imported=excluded.imported""",
        (item["provider"], item["origin"], deck["id"], cid, huella(item),
         json.dumps(metadata, ensure_ascii=False), time.time()))
    from . import documentos
    documentos.indexar(con, item["origin"], item["title"], item.get("pages") or [("Texto importado", cuerpo)],
                        parcial=bool(item.get("pages")) and item["origin"].lower().endswith(".pdf"))
    if commit:
        con.commit()
    return db.chapter_by_id(con, cid)


def cambios_carpeta(ruta, anteriores, consulta=""):
    """Hash del contenido, no solo del mtime; nunca modifica los apuntes originales."""
    salida, total = [], 0
    for item in explorar_carpeta(ruta, consulta):
        total += Path(item["origin"]).stat().st_size
        if total > 100 * 1024 * 1024:
            break
        doc = previsualizar(item)
        hashes = anteriores.get(item["origin"], [])
        status = "Sin cambios" if huella(doc) in hashes else "Actualizado" if hashes else "Nuevo"
        salida.append({**item, "summary": status + " · " + item["summary"]})
    return salida
