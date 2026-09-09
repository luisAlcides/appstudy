# Autoalimentación de contenido — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que AppStudy traiga sola, una vez al día, una lectura y unas seis tarjetas de fuentes abiertas comprobadas, y las deje en una bandeja esperando el visto bueno del usuario.

**Architecture:** Cuatro módulos nuevos con una responsabilidad cada uno: `catalogo.py` declara qué fuentes existen (sin red, sin estado), `selector.py` decide qué toca hoy (sin red, puro cálculo sobre la base), `cosecha.py` es el único que toca la red y aplica los filtros de calidad, y `bandeja.py` guarda la cola del visto bueno. El arranque llama a `cosecha.auto_si_toca()` en un hilo, calcado de `respaldo.auto_si_toca` y de `sincronizar_nube_en_silencio`.

**Tech Stack:** Python 3, GTK4/libadwaita (PyGObject), SQLite, `urllib.request`, `unittest`. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-09-autoalimentacion-fuentes-design.md`

## Global Constraints

- **Sin dependencias nuevas.** Solo biblioteca estándar y lo que ya usa el proyecto.
- **Toda la red pasa por `fuentes.descargar()`**, que valida HTTPS, dominio en lista blanca, redirecciones y tamaño. Ninguna llamada a `urllib` fuera de ahí.
- **Ninguna prueba toca la red.** Se sustituye `fuentes.descargar` por respuestas grabadas.
- **Claves de mazo válidas:** `ingles`, `linux`, `datos`, `ia`, `matematicas`, `electricidad`, `python`, `automotriz`, `maquinaria`.
- **Niveles:** `ingles` usa `A2 B1 B2 C1`; los ocho restantes, `Básico Intermedio Avanzado`. En la base son enteros de 1 en adelante.
- **Idioma del código y los comentarios: español**, como el resto del proyecto. Comentarios que expliquen el porqué, no el qué.
- **Un fallo de cosecha nunca llega a la pantalla.** Se anota en `meta` y se ve en Ajustes.
- **Las pruebas heredan de `tests.apoyo.BaseTemporal`.**
- Ejecutar la suite con `python3 -m pytest tests/ -q` (o `./pruebas.sh`).

---

### Task 1: La tabla `inbox`

**Files:**
- Modify: `appstudy/db.py` (constante `SCHEMA`, alrededor de la línea 123, junto a `source_imports`)
- Test: `tests/test_bandeja.py`

**Interfaces:**
- Produces: tabla `inbox` disponible en toda conexión de `db.connect()`.

- [ ] **Step 1: Write the failing test**

```python
import unittest
from appstudy import db
from tests.apoyo import BaseTemporal


class InboxEsquemaTest(BaseTemporal):
    def test_la_tabla_inbox_existe_con_sus_columnas(self):
        columnas = {r["name"] for r in self.con.execute("PRAGMA table_info(inbox)")}
        self.assertEqual(columnas, {
            "id", "provider", "origin", "deck_id", "title", "summary", "text",
            "author", "license", "score", "motivo", "cards", "estado", "created"})

    def test_no_se_repite_el_mismo_origen_en_el_mismo_mazo(self):
        did = self.mazo()
        for _ in range(2):
            self.con.execute(
                "INSERT OR IGNORE INTO inbox(provider,origin,deck_id,title,created)"
                " VALUES('wikipedia','https://es.wikipedia.org/wiki/Ohm',?,'Ohm',1.0)", (did,))
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM inbox").fetchone()["c"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bandeja.py -q`
Expected: FAIL — `PRAGMA table_info(inbox)` devuelve un conjunto vacío.

- [ ] **Step 3: Write minimal implementation**

En `appstudy/db.py`, dentro de `SCHEMA`, justo después del bloque de `source_imports`:

```sql
CREATE TABLE IF NOT EXISTS inbox (
    id       INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    origin   TEXT NOT NULL,
    deck_id  INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    title    TEXT NOT NULL,
    summary  TEXT NOT NULL DEFAULT '',
    text     TEXT NOT NULL DEFAULT '',
    author   TEXT NOT NULL DEFAULT '',
    license  TEXT NOT NULL DEFAULT '',
    score    REAL NOT NULL DEFAULT 0,
    motivo   TEXT NOT NULL DEFAULT '',
    cards    TEXT NOT NULL DEFAULT '[]',
    estado   TEXT NOT NULL DEFAULT 'pendiente',
    created  REAL NOT NULL,
    UNIQUE(provider, origin, deck_id)
);
```

`migrate()` ya ejecuta `SCHEMA` entero en cada arranque, así que las bases que ya existen reciben la tabla sin más trabajo.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_bandeja.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/db.py tests/test_bandeja.py
git commit -m "Bandeja: tabla inbox para el contenido que espera visto bueno"
```

---

### Task 2: `catalogo.py` — el registro de fuentes

**Files:**
- Create: `appstudy/catalogo.py`
- Test: `tests/test_catalogo.py`

**Interfaces:**
- Produces:
  - `FUENTES: list[dict]` con claves `id, nombre, hosts, tipo, licencia, idioma, mazos, buscar, base`
  - `por_id(ident) -> dict` (lanza `KeyError`)
  - `fuentes_de(deck_key, nivel=None) -> list[dict]`
  - `hosts() -> set[str]`
  - `abierta(ident) -> bool`

`tipo` ∈ `{"buscador", "indice", "catalogo"}`. `licencia` ∈ `{"abierta", "solo-enlace"}`.
`mazos` es `{deck_key: [niveles]}` con `[]` para «todos los niveles».

- [ ] **Step 1: Write the failing test**

```python
import unittest

from appstudy import catalogo, fuentes

MAZOS = {"ingles", "linux", "datos", "ia", "matematicas",
         "electricidad", "python", "automotriz", "maquinaria"}


class CatalogoTest(unittest.TestCase):
    def test_cada_fuente_esta_bien_declarada(self):
        for f in catalogo.FUENTES:
            with self.subTest(f["id"]):
                self.assertTrue(f["hosts"], "sin hosts")
                self.assertIn(f["tipo"], ("buscador", "indice", "catalogo"))
                self.assertIn(f["licencia"], ("abierta", "solo-enlace"))
                self.assertTrue(f["mazos"], "no sirve a ningún mazo")
                self.assertLessEqual(set(f["mazos"]), MAZOS)

    def test_los_identificadores_no_se_repiten(self):
        ids = [f["id"] for f in catalogo.FUENTES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_todos_los_hosts_estan_en_la_lista_blanca_de_fuentes(self):
        permitidos = set().union(*fuentes.DOMINIOS.values())
        self.assertLessEqual(catalogo.hosts(), permitidos)

    def test_cada_mazo_tiene_al_menos_una_fuente(self):
        for mazo in MAZOS:
            with self.subTest(mazo):
                self.assertTrue(catalogo.fuentes_de(mazo))

    def test_arxiv_es_solo_enlace(self):
        self.assertFalse(catalogo.abierta("arxiv"))
        self.assertTrue(catalogo.abierta("wikipedia_es"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_catalogo.py -q`
Expected: FAIL — `ModuleNotFoundError: appstudy.catalogo`

- [ ] **Step 3: Write minimal implementation**

`appstudy/catalogo.py`, con la cabecera y una entrada por fuente. Las URL salen de las comprobaciones del spec:

```python
"""Qué fuentes existen y a qué mazo sirve cada una.

Datos, no comportamiento: aquí no se toca la red ni la base. Así el resto del
subsistema se puede probar sin salir a internet, y añadir una fuente es añadir
una fila.

`licencia` decide qué se puede importar entero. `abierta` es dominio público o
licencia libre con atribución, que es lo que `fuentes.importar()` ya añade;
`solo-enlace` es todo lo demás, y de eso solo se guarda título, resumen y enlace
—la app sincroniza y publica mazos, así que el texto ajeno puede salir del
equipo—.
"""
from __future__ import annotations

TODOS = []          # una lista de niveles vacía significa «todos»

FUENTES = [
    # --------------------------------------------------------- buscadores
    {"id": "wikipedia_es", "nombre": "Wikipedia en español", "tipo": "buscador",
     "licencia": "abierta", "idioma": "es", "hosts": {"es.wikipedia.org"},
     "base": "https://es.wikipedia.org", "buscar": "mediawiki",
     "mazos": {"linux": TODOS, "datos": TODOS, "ia": TODOS, "matematicas": TODOS,
               "electricidad": TODOS, "automotriz": TODOS, "maquinaria": TODOS}},
    {"id": "wikipedia_en", "nombre": "Wikipedia en inglés", "tipo": "buscador",
     "licencia": "abierta", "idioma": "en", "hosts": {"en.wikipedia.org"},
     "base": "https://en.wikipedia.org", "buscar": "mediawiki",
     "mazos": {"ingles": ["B2", "C1"], "ia": TODOS, "datos": TODOS}},
    {"id": "wikipedia_simple", "nombre": "Simple English Wikipedia", "tipo": "buscador",
     "licencia": "abierta", "idioma": "en", "hosts": {"simple.wikipedia.org"},
     "base": "https://simple.wikipedia.org", "buscar": "mediawiki",
     "mazos": {"ingles": ["A2", "B1"]}},
    {"id": "wiktionary_en", "nombre": "Wiktionary", "tipo": "buscador",
     "licencia": "abierta", "idioma": "en", "hosts": {"en.wiktionary.org"},
     "base": "https://en.wiktionary.org", "buscar": "mediawiki",
     "mazos": {"ingles": TODOS}},
    {"id": "wikibooks_es", "nombre": "Wikilibros", "tipo": "buscador",
     "licencia": "abierta", "idioma": "es", "hosts": {"es.wikibooks.org"},
     "base": "https://es.wikibooks.org", "buscar": "mediawiki",
     "mazos": {"python": TODOS, "matematicas": TODOS, "electricidad": TODOS,
               "automotriz": TODOS, "maquinaria": TODOS}},
    {"id": "wikiversity_es", "nombre": "Wikiversidad", "tipo": "buscador",
     "licencia": "abierta", "idioma": "es", "hosts": {"es.wikiversity.org"},
     "base": "https://es.wikiversity.org", "buscar": "mediawiki",
     "mazos": {"matematicas": TODOS, "datos": TODOS}},
    {"id": "archwiki", "nombre": "ArchWiki", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "en", "hosts": {"wiki.archlinux.org"},
     "base": "https://wiki.archlinux.org", "buscar": "mediawiki_corto",
     "mazos": {"linux": TODOS}},
    {"id": "gentoo", "nombre": "Gentoo Wiki", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "en", "hosts": {"wiki.gentoo.org"},
     "base": "https://wiki.gentoo.org", "buscar": "mediawiki_corto",
     "mazos": {"linux": TODOS}},
    {"id": "arxiv", "nombre": "arXiv", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "en", "hosts": {"export.arxiv.org", "arxiv.org"},
     "base": "https://export.arxiv.org", "buscar": "arxiv",
     "mazos": {"ia": ["Avanzado"], "datos": ["Avanzado"]}},
    {"id": "mdn", "nombre": "MDN Web Docs", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "es", "hosts": {"developer.mozilla.org"},
     "base": "https://developer.mozilla.org", "buscar": "mdn",
     "mazos": {"python": TODOS}},
    {"id": "gutenberg", "nombre": "Project Gutenberg", "tipo": "buscador",
     "licencia": "abierta", "idioma": "en", "hosts": {"gutendex.com", "www.gutenberg.org"},
     "base": "https://gutendex.com", "buscar": "gutendex",
     "mazos": {"ingles": ["B2", "C1"]}},
    # ------------------------------------------------------------ índices
    {"id": "libretexts_workforce", "nombre": "LibreTexts Workforce", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"workforce.libretexts.org"},
     "base": "https://workforce.libretexts.org", "buscar": "sitemap",
     "mazos": {"automotriz": TODOS, "maquinaria": TODOS, "electricidad": TODOS}},
    {"id": "libretexts_esp", "nombre": "LibreTexts en español", "tipo": "indice",
     "licencia": "abierta", "idioma": "es", "hosts": {"espanol.libretexts.org"},
     "base": "https://espanol.libretexts.org", "buscar": "sitemap",
     "mazos": {"matematicas": TODOS, "electricidad": TODOS, "datos": TODOS}},
    {"id": "libretexts_eng", "nombre": "LibreTexts Engineering", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"eng.libretexts.org"},
     "base": "https://eng.libretexts.org", "buscar": "sitemap",
     "mazos": {"electricidad": TODOS, "automotriz": TODOS, "maquinaria": TODOS}},
    {"id": "man7", "nombre": "Páginas de manual de Linux", "tipo": "indice",
     "licencia": "solo-enlace", "idioma": "en", "hosts": {"man7.org"},
     "base": "https://man7.org/linux/man-pages/dir_all_alphabetic.html",
     "buscar": "indice_html", "mazos": {"linux": TODOS}},
    {"id": "tldp", "nombre": "The Linux Documentation Project", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"tldp.org"},
     "base": "https://tldp.org/LDP/intro-linux/html/index.html",
     "buscar": "indice_html", "mazos": {"linux": ["Básico", "Intermedio"]}},
    {"id": "pydocs", "nombre": "Documentación de Python", "tipo": "indice",
     "licencia": "abierta", "idioma": "es", "hosts": {"docs.python.org"},
     "base": "https://docs.python.org/es/3/py-modindex.html",
     "buscar": "indice_html", "mazos": {"python": TODOS}},
    {"id": "pandas", "nombre": "Guía de usuario de pandas", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"pandas.pydata.org"},
     "base": "https://pandas.pydata.org/docs/user_guide/index.html",
     "buscar": "indice_html", "mazos": {"datos": TODOS, "python": TODOS}},
    {"id": "sklearn", "nombre": "Guía de usuario de scikit-learn", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"scikit-learn.org"},
     "base": "https://scikit-learn.org/stable/user_guide.html",
     "buscar": "indice_html", "mazos": {"datos": ["Intermedio", "Avanzado"]}},
    {"id": "huggingface", "nombre": "Documentación de Hugging Face", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"huggingface.co"},
     "base": "https://huggingface.co/docs/transformers/index",
     "buscar": "indice_html", "mazos": {"ia": TODOS}},
    {"id": "ibiblio", "nombre": "Lessons In Electric Circuits", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"www.ibiblio.org"},
     "base": "https://www.ibiblio.org/kuphaldt/electricCircuits/DC/index.html",
     "buscar": "indice_html", "mazos": {"electricidad": TODOS}},
    {"id": "voa", "nombre": "VOA Learning English", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"learningenglish.voanews.com"},
     "base": "https://learningenglish.voanews.com/",
     "buscar": "indice_html", "mazos": {"ingles": ["A2", "B1", "B2"]}},
    {"id": "saylor", "nombre": "Saylor Academy", "tipo": "indice",
     "licencia": "abierta", "idioma": "en", "hosts": {"learn.saylor.org"},
     "base": "https://learn.saylor.org/", "buscar": "indice_html",
     "mazos": {"datos": TODOS, "matematicas": TODOS}},
    # ---------------------------------------------------------- catálogos
    {"id": "openstax", "nombre": "OpenStax", "tipo": "catalogo",
     "licencia": "abierta", "idioma": "es", "hosts": {"openstax.org", "assets.openstax.org"},
     "base": "https://openstax.org", "buscar": "catalogo",
     "mazos": {"matematicas": TODOS, "datos": TODOS, "electricidad": TODOS}},
    {"id": "mit", "nombre": "MIT OpenCourseWare", "tipo": "catalogo",
     "licencia": "abierta", "idioma": "en", "hosts": {"ocw.mit.edu", "live.ocw.mit.edu"},
     "base": "https://ocw.mit.edu", "buscar": "catalogo",
     "mazos": {"matematicas": ["Avanzado"], "electricidad": ["Avanzado"],
               "python": ["Intermedio"]}},
]

_POR_ID = {f["id"]: f for f in FUENTES}


def por_id(ident: str) -> dict:
    return _POR_ID[ident]


def hosts() -> set:
    return set().union(*(f["hosts"] for f in FUENTES))


def abierta(ident: str) -> bool:
    return _POR_ID[ident]["licencia"] == "abierta"


def fuentes_de(deck_key: str, nivel: str | None = None) -> list:
    """Las fuentes que sirven a ese mazo, y a ese nivel si se pide uno."""
    salida = []
    for f in FUENTES:
        niveles = f["mazos"].get(deck_key)
        if niveles is None:
            continue
        if nivel is None or not niveles or nivel in niveles:
            salida.append(f)
    return salida
```

- [ ] **Step 4: Ampliar `fuentes.DOMINIOS` para que la lista blanca cubra los hosts nuevos**

En `appstudy/fuentes.py`, sustituir el diccionario `DOMINIOS` por uno construido desde el catálogo, conservando las entradas que ya había:

```python
DOMINIOS = {"wikipedia": {"es.wikipedia.org", "en.wikipedia.org"},
            "openstax": {"openstax.org", "assets.openstax.org"},
            "mit": {"ocw.mit.edu", "live.ocw.mit.edu"}}


def _registrar_catalogo():
    """Cada fuente del catálogo es también un proveedor con su lista blanca.

    Se hace aquí y no en `catalogo.py` para no invertir la dependencia: el
    catálogo son datos y no debe saber nada de descargas.
    """
    from . import catalogo
    for f in catalogo.FUENTES:
        DOMINIOS.setdefault(f["id"], set()).update(f["hosts"])


_registrar_catalogo()
```

Colocarlo justo después de la definición de `DOMINIOS`, antes de `class FuenteError`. La importación va dentro de la función porque `catalogo` no importa `fuentes`, pero el orden de carga de los módulos sí puede variar.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_catalogo.py tests/test_fuentes.py tests/test_fuentes_extensiones.py -q` → PASS

- [ ] **Step 6: Commit**

```bash
git add appstudy/catalogo.py appstudy/fuentes.py tests/test_catalogo.py
git commit -m "Catálogo: 25 fuentes abiertas declaradas con licencia y mazos"
```

---

### Task 3: Los conectores de búsqueda nuevos

**Files:**
- Modify: `appstudy/fuentes.py` (función `buscar`, línea ~150)
- Test: `tests/test_fuentes_catalogo.py`

**Interfaces:**
- Consumes: `catalogo.por_id`, `catalogo.FUENTES` (Task 2)
- Produces: `fuentes.buscar(provider, consulta, config)` acepta cualquier `id` del catálogo y devuelve la misma lista de documentos que ya devolvía para Wikipedia.

- [ ] **Step 1: Write the failing test**

```python
import json
import unittest

from appstudy import fuentes


class BuscadoresTest(unittest.TestCase):
    def grabar(self, cuerpo: bytes, tipo="application/json"):
        """Sustituye la descarga por una respuesta grabada. Nada sale a la red."""
        original = fuentes.descargar
        fuentes.descargar = lambda url, dominios, limite=None: (cuerpo, tipo)
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))

    def test_mediawiki_sirve_para_cualquier_host_del_catalogo(self):
        self.grabar(json.dumps({"pages": [
            {"key": "Systemd", "title": "systemd", "excerpt": "gestor de <b>servicios</b>"}]}).encode())
        r = fuentes.buscar("archwiki", "systemd")
        self.assertEqual(r[0]["title"], "systemd")
        self.assertEqual(r[0]["origin"], "https://wiki.archlinux.org/title/Systemd")

    def test_arxiv_lee_el_atom_y_se_queda_con_el_resumen(self):
        self.grabar(b"""<?xml version='1.0' encoding='UTF-8'?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry><id>https://arxiv.org/abs/2401.00001v1</id>
                <title>Retrieval Augmented Generation</title>
                <summary>Un resumen de prueba.</summary>
                <author><name>A. Autora</name></author></entry>
            </feed>""", "application/atom+xml")
        r = fuentes.buscar("arxiv", "rag")
        self.assertEqual(r[0]["title"], "Retrieval Augmented Generation")
        self.assertEqual(r[0]["origin"], "https://arxiv.org/abs/2401.00001v1")
        self.assertIn("resumen de prueba", r[0]["summary"])

    def test_gutendex_solo_devuelve_libros_con_texto_plano(self):
        self.grabar(json.dumps({"results": [
            {"title": "Hard Times", "authors": [{"name": "Dickens, Charles"}],
             "formats": {"text/plain; charset=utf-8": "https://www.gutenberg.org/ebooks/786.txt.utf-8"}},
            {"title": "Sin texto", "authors": [], "formats": {"image/jpeg": "x"}}]}).encode())
        r = fuentes.buscar("gutenberg", "dickens")
        self.assertEqual([x["title"] for x in r], ["Hard Times"])

    def test_una_respuesta_ilegible_da_un_error_de_fuente_no_una_excepcion_cruda(self):
        self.grabar(b"esto no es json")
        with self.assertRaises(fuentes.FuenteError):
            fuentes.buscar("wikipedia_es", "ohm")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fuentes_catalogo.py -q`
Expected: FAIL — `FuenteError: Fuente no reconocida`

- [ ] **Step 3: Write minimal implementation**

En `appstudy/fuentes.py`, añadir antes de `def buscar` los cuatro buscadores y despachar por `f["buscar"]`. `_mediawiki` sirve a los siete hosts wiki: la única diferencia entre ellos es el prefijo `/w` y la ruta del artículo.

```python
def _mediawiki(f, consulta, corto=False):
    """Wikipedia, Wikilibros, Wikiversidad, Wiktionary, ArchWiki y Gentoo.

    ArchWiki y Gentoo montan la API en la raíz y los artículos en /title/;
    los proyectos de Wikimedia usan /w y /wiki. Por lo demás, misma API.
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
            for p in paginas]


def _arxiv(f, consulta):
    """Resúmenes, nunca el PDF: la licencia de arXiv cambia con cada artículo."""
    url = (f["base"] + "/api/query?" + urllib.parse.urlencode(
        {"search_query": "all:" + consulta, "max_results": 10}))
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        import xml.etree.ElementTree as ET
        raiz = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except Exception as e:                     # ET lanza ParseError, hija de SyntaxError
        raise FuenteError("arXiv devolvió una respuesta no reconocible") from e
    ns = {"a": "http://www.w3.org/2005/Atom"}
    salida = []
    for e in raiz.findall("a:entry", ns):
        ident = (e.findtext("a:id", "", ns) or "").strip()
        titulo = " ".join((e.findtext("a:title", "", ns) or "").split())
        resumen = " ".join((e.findtext("a:summary", "", ns) or "").split())
        autores = [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)]
        if ident and titulo:
            salida.append(documento(f["id"], ident, titulo, summary=resumen,
                                    author=", ".join(filter(None, autores)),
                                    license="Licencia propia de cada artículo · véase arXiv"))
    return salida


def _mdn(f, consulta):
    url = f["base"] + "/api/v1/search?" + urllib.parse.urlencode({"q": consulta, "locale": "es"})
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        docs = json.loads(raw)["documents"]
    except (KeyError, TypeError, ValueError) as e:
        raise FuenteError("MDN devolvió una respuesta no reconocible") from e
    return [documento(f["id"], f["base"] + d["mdn_url"], d["title"],
                      summary=d.get("summary", ""))
            for d in docs if d.get("mdn_url")]


def _gutendex(f, consulta):
    """Solo los libros con texto plano: un EPUB no se puede leer en un capítulo."""
    url = f["base"] + "/books/?" + urllib.parse.urlencode({"search": consulta})
    raw, _ = descargar(url, DOMINIOS[f["id"]])
    try:
        libros = json.loads(raw)["results"]
    except (KeyError, TypeError, ValueError) as e:
        raise FuenteError("Project Gutenberg devolvió una respuesta no reconocible") from e
    salida = []
    for libro in libros:
        texto = next((v for k, v in libro.get("formats", {}).items()
                      if k.startswith("text/plain")), "")
        if texto:
            salida.append(documento(
                f["id"], texto, libro["title"],
                author=", ".join(a.get("name", "") for a in libro.get("authors", [])),
                license="Dominio público · Project Gutenberg",
                summary="Libro completo en texto plano"))
    return salida
```

Y al principio de `buscar`, antes del `if provider == "wikipedia"` que ya existe:

```python
    from . import catalogo
    try:
        f = catalogo.por_id(provider)
    except KeyError:
        f = None
    if f is not None:
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
        if modo in ("sitemap", "indice_html", "catalogo"):
            return indice(f, consulta)      # Task 4
```

Los proveedores antiguos (`wikipedia`, `openstax`, `mit`, `markdown`) siguen funcionando: sus ramas quedan intactas detrás de este bloque, y la ventana de Fuentes no cambia.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_fuentes_catalogo.py tests/test_fuentes.py tests/test_fuentes_ui.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/fuentes.py tests/test_fuentes_catalogo.py
git commit -m "Fuentes: conectores de MediaWiki multi-host, arXiv, MDN y Gutenberg"
```

---

### Task 4: Recorrido de índices con caché

**Files:**
- Modify: `appstudy/fuentes.py` (función nueva `indice`)
- Test: `tests/test_fuentes_indice.py`

**Interfaces:**
- Produces: `fuentes.indice(f, consulta="", refrescar=False) -> list[dict]`, misma forma de documento que `buscar`.
- Caché en `db.DATA_DIR / "fuentes" / "indices" / <id>.json`, con `{"ts": float, "items": [[titulo, url], ...]}`. Se refresca si tiene más de 30 días.

- [ ] **Step 1: Write the failing test**

```python
import json
import time
import unittest

from appstudy import catalogo, db, fuentes
from tests.apoyo import BaseTemporal

SITEMAP = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://workforce.libretexts.org/Bookshelves/Automotive/Brakes</loc></url>
<url><loc>https://workforce.libretexts.org/Bookshelves/Automotive/Engines</loc></url>
<url><loc>https://workforce.libretexts.org/Special:Search</loc></url>
</urlset>"""


class IndiceTest(BaseTemporal):
    def grabar(self, cuerpo, tipo="application/xml"):
        original = fuentes.descargar
        self.llamadas = []

        def falso(url, dominios, limite=None):
            self.llamadas.append(url)
            return cuerpo, tipo
        fuentes.descargar = falso
        self.addCleanup(lambda: setattr(fuentes, "descargar", original))

    def test_el_sitemap_da_paginas_y_descarta_las_de_servicio(self):
        self.grabar(SITEMAP)
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"))
        self.assertEqual([x["title"] for x in r], ["Brakes", "Engines"])

    def test_la_consulta_filtra_por_titulo(self):
        self.grabar(SITEMAP)
        r = fuentes.indice(catalogo.por_id("libretexts_workforce"), "brakes")
        self.assertEqual(len(r), 1)

    def test_el_indice_se_cachea_y_no_se_vuelve_a_descargar(self):
        self.grabar(SITEMAP)
        f = catalogo.por_id("libretexts_workforce")
        fuentes.indice(f)
        fuentes.indice(f)
        self.assertEqual(len(self.llamadas), 1, "el índice se descargó dos veces")

    def test_un_indice_caducado_se_vuelve_a_pedir(self):
        self.grabar(SITEMAP)
        f = catalogo.por_id("libretexts_workforce")
        fuentes.indice(f)
        ruta = db.DATA_DIR / "fuentes" / "indices" / "libretexts_workforce.json"
        datos = json.loads(ruta.read_text())
        datos["ts"] = time.time() - fuentes.CADUCIDAD_INDICE - 1
        ruta.write_text(json.dumps(datos))
        fuentes.indice(f)
        self.assertEqual(len(self.llamadas), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fuentes_indice.py -q`
Expected: FAIL — `AttributeError: module 'appstudy.fuentes' has no attribute 'indice'`

- [ ] **Step 3: Write minimal implementation**

En `appstudy/fuentes.py`:

```python
CADUCIDAD_INDICE = 30 * 86400
MAX_INDICE = 20 * 1024 * 1024      # el sitemap de LibreTexts pasa de 3 MB

# Páginas de servicio que no son material de estudio en ningún wiki ni manual
_RUIDO = ("Special:", "Talk:", "/index", "/search", "/login", "/genindex",
          "Sandbox", "Template:", "Category:", "Help:")


def _indice_paginas(f, raw, tipo):
    """Convierte un sitemap XML o una página índice en pares (título, URL)."""
    if f["buscar"] == "sitemap":
        import xml.etree.ElementTree as ET
        raiz = ET.fromstring(raw.decode("utf-8", errors="replace"))
        urls = [n.text.strip() for n in raiz.iter() if n.tag.endswith("}loc") and n.text]
        pares = [(urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1]).replace("_", " "), u)
                 for u in urls]
    else:
        pagina = Pagina(raw.decode("utf-8", errors="replace"))
        pares = [(" ".join(t.split()), urllib.parse.urljoin(f["base"], href).split("#")[0])
                 for href, t in pagina.enlaces if t and t.strip()]
    salida, vistos = [], set()
    for titulo, url in pares:
        if not titulo or url in vistos or any(r in url for r in _RUIDO):
            continue
        try:
            validar_url(url, DOMINIOS[f["id"]])
        except ValueError:
            continue
        vistos.add(url)
        salida.append([titulo, url])
    return salida


def indice(f, consulta="", refrescar=False):
    """Las páginas de una fuente sin buscador, desde su índice y con caché.

    El sitemap de LibreTexts pesa megas: se baja una vez al mes, no en cada
    arranque. Si la descarga falla pero hay copia guardada, se usa la copia.
    """
    if f["buscar"] == "catalogo":
        pares = [[t, u] for t, u in CATALOGOS.get(f["id"], CATALOGOS.get("mit", []))]
    else:
        carpeta = db.DATA_DIR / "fuentes" / "indices"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / (f["id"] + ".json")
        guardado = None
        if ruta.exists():
            try:
                guardado = json.loads(ruta.read_text(encoding="utf-8"))
            except ValueError:
                guardado = None
        vigente = guardado and time.time() - guardado.get("ts", 0) < CADUCIDAD_INDICE
        if vigente and not refrescar:
            pares = guardado["items"]
        else:
            url = f["base"] + "/sitemap.xml" if f["buscar"] == "sitemap" else f["base"]
            try:
                raw, tipo = descargar(url, DOMINIOS[f["id"]], MAX_INDICE)
                pares = _indice_paginas(f, raw, tipo)
                ruta.write_text(json.dumps({"ts": time.time(), "items": pares},
                                           ensure_ascii=False), encoding="utf-8")
            except (FuenteError, OSError, ValueError):
                if not guardado:
                    raise
                pares = guardado["items"]
    terminos = clave(consulta).split()
    return [documento(f["id"], url, titulo, summary=f["nombre"])
            for titulo, url in pares
            if all(t in clave(titulo) for t in terminos)][:200]
```

Nota sobre `f["base"]` en las fuentes `sitemap`: es la raíz del host (`https://workforce.libretexts.org`), así que `base + "/sitemap.xml"` da la URL correcta. En las `indice_html`, `base` ya es la página índice completa.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_fuentes_indice.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/fuentes.py tests/test_fuentes_indice.py
git commit -m "Fuentes: recorrido de índices y sitemaps con caché mensual"
```

---

### Task 5: `selector.py` — qué toca hoy

**Files:**
- Create: `appstudy/selector.py`
- Test: `tests/test_selector.py`

**Interfaces:**
- Consumes: `catalogo.fuentes_de` (Task 2)
- Produces: `selector.plan(con, ahora=None) -> dict | None` con
  `{"deck": sqlite3.Row, "nivel": str, "nivel_num": int, "terminos": list[str], "fuentes": list[dict], "motivo": str}`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from appstudy import db, selector
from tests.apoyo import BaseTemporal


class SelectorTest(BaseTemporal):
    def test_sin_mazos_no_hay_plan(self):
        self.assertIsNone(selector.plan(self.con))

    def test_elige_el_mazo_con_menos_material(self):
        pobre = db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "")
        rico = db.upsert_deck(self.con, "linux", "Linux", "🐧", "")
        for i in range(40):
            db.add_card(self.con, rico, "linux", "card", f"Pregunta {i}", "Respuesta")
        db.add_card(self.con, pobre, "electricidad", "card", "¿Qué es un ohmio?", "Resistencia")
        self.con.commit()
        p = selector.plan(self.con)
        self.assertEqual(p["deck"]["key"], "electricidad")

    def test_los_terminos_salen_de_las_etiquetas_de_lo_que_fallas(self):
        did = db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "")
        cid = db.add_card(self.con, did, "electricidad", "card",
                          "¿Qué es un transistor?", "Un semiconductor", tags="transistores")
        self.con.execute("INSERT OR REPLACE INTO state(card_id,lapses,last) VALUES(?,?,?)",
                         (cid if isinstance(cid, int) else cid[0], 6, 1.0))
        self.con.commit()
        p = selector.plan(self.con)
        self.assertIn("transistores", p["terminos"])

    def test_no_propone_una_fuente_apagada_en_ajustes(self):
        from appstudy import extensiones
        db.upsert_deck(self.con, "linux", "Linux", "🐧", "")
        self.con.commit()
        for f in selector.plan(self.con)["fuentes"]:
            extensiones.activar(self.con, {"id": f["id"]}, False)
        self.assertIsNone(selector.plan(self.con))

    def test_el_plan_trae_siempre_un_motivo_legible(self):
        db.upsert_deck(self.con, "linux", "Linux", "🐧", "")
        self.con.commit()
        self.assertTrue(selector.plan(self.con)["motivo"].strip())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_selector.py -q`
Expected: FAIL — `ModuleNotFoundError: appstudy.selector`

- [ ] **Step 3: Write minimal implementation**

```python
"""Qué contenido pedir hoy. Solo mira la base: aquí no se toca la red.

La regla es sencilla y se puede explicar en una frase: alimenta al mazo que
menos material tiene, y pídele lo que más fallas dentro de él. Si no fallas
nada todavía, pide por el nombre del mazo y su nivel.
"""
from __future__ import annotations

import time

from . import catalogo, db, extensiones

MINIMO_POR_NIVEL = 40      # por debajo de esto, un nivel se considera flojo
MAX_TERMINOS = 3


def _niveles(deck) -> list:
    return [n for n in (deck["levels"] or "").split(",") if n.strip()] or \
           ["Básico", "Intermedio", "Avanzado"]


def _mazo_mas_flojo(con):
    """El mazo con menos tarjetas. A igualdad, el que lleva más sin alimentarse."""
    return con.execute("""
        SELECT d.*, COUNT(c.id) AS cuantas,
               COALESCE((SELECT MAX(imported) FROM source_imports s
                         WHERE s.deck_id = d.id), 0) AS ultima
          FROM decks d LEFT JOIN cards c ON c.deck_id = d.id
         GROUP BY d.id ORDER BY cuantas ASC, ultima ASC LIMIT 1""").fetchone()


def _terminos(con, deck) -> tuple[list, str]:
    """Las etiquetas de lo que más fallas en ese mazo, y por qué se piden."""
    filas = con.execute("""
        SELECT c.tags, s.lapses FROM cards c JOIN state s ON s.card_id = c.id
         WHERE c.deck_id = ? AND s.lapses > 0 AND c.tags <> ''
         ORDER BY s.lapses DESC LIMIT 20""", (deck["id"],)).fetchall()
    cuenta = {}
    for fila in filas:
        for etiqueta in (e.strip() for e in fila["tags"].split(",")):
            if etiqueta and etiqueta != "inversa":
                cuenta[etiqueta] = cuenta.get(etiqueta, 0) + fila["lapses"]
    if cuenta:
        mejores = sorted(cuenta, key=cuenta.get, reverse=True)[:MAX_TERMINOS]
        return mejores, "porque fallas " + ", ".join(mejores)
    return [deck["name"]], f"para ampliar {deck['name']}, que va corto de material"


def _nivel_por_llenar(con, deck) -> tuple:
    """El primer nivel del mazo que no llega al mínimo. Si todos llegan, el último."""
    niveles = _niveles(deck)
    for i, nombre in enumerate(niveles, start=1):
        cuantas = con.execute("SELECT COUNT(*) c FROM cards WHERE deck_id=? AND level=?",
                              (deck["id"], i)).fetchone()["c"]
        if cuantas < MINIMO_POR_NIVEL:
            return nombre, i
    return niveles[-1], len(niveles)


def plan(con, ahora: float | None = None) -> dict | None:
    deck = _mazo_mas_flojo(con)
    if not deck:
        return None
    nivel, nivel_num = _nivel_por_llenar(con, deck)
    disponibles = [f for f in catalogo.fuentes_de(deck["key"], nivel)
                   if extensiones.habilitada(con, f["id"])]
    if not disponibles:
        return None
    terminos, motivo = _terminos(con, deck)
    return {"deck": deck, "nivel": nivel, "nivel_num": nivel_num,
            "terminos": terminos, "fuentes": disponibles, "motivo": motivo,
            "ts": ahora or time.time()}
```

Comprobar antes de dar por bueno: `extensiones.habilitada(con, ident)` debe devolver `True` para una fuente que nunca se ha tocado. Si su implementación devuelve `False` por omisión para las que no están en `INCLUIDAS`, añadir las del catálogo a `extensiones.INCLUIDAS` en este mismo paso, generándolas desde `catalogo.FUENTES`:

```python
INCLUIDAS = [...] + [(f["id"], f["nombre"], "source", ["network"])
                     for f in _catalogo_fuentes()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_selector.py tests/test_fuentes_extensiones.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/selector.py appstudy/extensiones.py tests/test_selector.py
git commit -m "Selector: alimenta al mazo más flojo por lo que más fallas"
```

---

### Task 6: Los filtros de calidad

**Files:**
- Create: `appstudy/cosecha.py` (solo la parte de filtros)
- Test: `tests/test_filtros.py`

**Interfaces:**
- Produces: `cosecha.filtrar(con, doc, plan) -> dict` con `{"ok": bool, "score": float, "nivel": int, "motivo": str}`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from appstudy import catalogo, cosecha, db, fuentes, selector
from tests.apoyo import BaseTemporal

BUENO = ("La resistencia eléctrica se opone al paso de la corriente. " * 8 +
         "Un conductor tiene una resistencia que depende de su longitud y de su sección. " * 8 +
         "La ley de Ohm relaciona la tensión, la corriente y la resistencia del circuito. " * 40)


class FiltrosTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡",
                       "Básico,Intermedio,Avanzado")
        self.con.commit()
        self.plan = selector.plan(self.con)

    def doc(self, texto, provider="wikipedia_es", titulo="Resistencia eléctrica"):
        return fuentes.documento(provider, "https://es.wikipedia.org/wiki/R", titulo, text=texto)

    def test_un_texto_bueno_pasa(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO), self.plan)
        self.assertTrue(r["ok"], r["motivo"])

    def test_un_esbozo_se_rechaza_por_corto(self):
        r = cosecha.filtrar(self.con, self.doc("Dos frases. Nada más."), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("corto", r["motivo"])

    def test_una_lista_de_enlaces_se_rechaza_por_no_ser_prosa(self):
        r = cosecha.filtrar(self.con, self.doc("\n".join(["Ver también"] * 400)), self.plan)
        self.assertFalse(r["ok"])

    def test_el_ingles_se_rechaza_en_un_mazo_en_espanol(self):
        ingles = ("The electrical resistance of a conductor depends on its length. " * 60)
        r = cosecha.filtrar(self.con, self.doc(ingles), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("idioma", r["motivo"])

    def test_una_fuente_solo_enlace_nunca_pasa_con_texto_completo(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO, provider="arxiv"), self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("licencia", r["motivo"])

    def test_un_texto_ya_importado_se_rechaza_por_duplicado(self):
        doc = self.doc(BUENO)
        deck = dict(self.plan["deck"])
        self.con.execute(
            "INSERT INTO source_imports VALUES(?,?,?,?,?,?,?)",
            (doc["provider"], doc["origin"], deck["id"], None, fuentes.huella(doc), "{}", 1.0))
        self.con.commit()
        r = cosecha.filtrar(self.con, doc, self.plan)
        self.assertFalse(r["ok"])
        self.assertIn("ya", r["motivo"])

    def test_el_nivel_sale_de_la_dificultad_del_texto(self):
        r = cosecha.filtrar(self.con, self.doc(BUENO), self.plan)
        self.assertIn(r["nivel"], (1, 2, 3))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_filtros.py -q`
Expected: FAIL — `ModuleNotFoundError: appstudy.cosecha`

- [ ] **Step 3: Write minimal implementation**

```python
"""Trae contenido nuevo y decide si vale la pena. El único módulo con red.

«Calidad» tiene que ser algo que el código pueda decidir, así que son siete
comprobaciones con un motivo legible cada una. El motivo se guarda también
cuando se rechaza: sin eso, «no me trae nada» sería indepurable.
"""
from __future__ import annotations

import re
import time

from . import catalogo, db, fuentes, selector

MIN_PALABRAS, MAX_PALABRAS = 400, 20000
MIN_PROSA = 0.35          # proporción de frases largas frente a renglones sueltos
MIN_RELEVANCIA = 0.15
UMBRAL = 0.5

# Palabras vacías: bastan para distinguir un idioma de otro sin dependencias
_ES = {"de", "la", "que", "el", "en", "y", "los", "se", "del", "las", "un", "por",
       "con", "una", "para", "es", "al", "lo", "como", "más", "o", "si", "su"}
_EN = {"the", "of", "and", "to", "in", "a", "is", "that", "for", "it", "as", "with",
       "on", "be", "by", "this", "are", "from", "or", "an", "which", "you"}


def idioma(texto: str) -> str:
    palabras = re.findall(r"[a-záéíóúñü]+", texto.lower())[:2000]
    if not palabras:
        return "?"
    es = sum(p in _ES for p in palabras)
    en = sum(p in _EN for p in palabras)
    return "es" if es >= en else "en"


def nivel_de(texto: str, cuantos: int) -> int:
    """Frases largas y palabras largas: lo más parecido a dificultad que se
    puede medir sin entender el texto."""
    frases = [f for f in re.split(r"[.!?]+", texto) if f.strip()]
    if not frases:
        return 1
    palabras = texto.split()
    media = len(palabras) / len(frases)
    largas = sum(len(p) > 9 for p in palabras) / max(1, len(palabras))
    if media < 16 and largas < 0.14:
        return 1
    if media < 24 and largas < 0.22:
        return min(2, cuantos)
    return min(3, cuantos)


def _prosa(texto: str) -> float:
    renglones = [l.strip() for l in texto.splitlines() if l.strip()]
    if not renglones:
        return 0.0
    return sum(len(l.split()) >= 8 for l in renglones) / len(renglones)


def _relevancia(doc: dict, plan: dict) -> float:
    campo = fuentes.clave(doc["title"] + " " + doc["text"][:2000])
    terminos = [fuentes.clave(t) for t in plan["terminos"]]
    partes = [p for t in terminos for p in t.split() if len(p) > 3]
    if not partes:
        return 1.0
    return sum(p in campo for p in partes) / len(partes)


def filtrar(con, doc: dict, plan: dict) -> dict:
    """Devuelve si el documento entra, con qué nota y por qué."""
    def no(motivo, score=0.0):
        return {"ok": False, "score": score, "nivel": 1, "motivo": motivo}

    if not catalogo.abierta(doc["provider"]):
        return no("licencia: la fuente solo permite enlace, no texto completo")
    texto = doc.get("text", "")
    palabras = len(texto.split())
    if palabras < MIN_PALABRAS:
        return no(f"demasiado corto: {palabras} palabras")
    if palabras > MAX_PALABRAS:
        return no(f"demasiado largo: {palabras} palabras")
    bajo = fuentes.clave(doc["title"])
    if "desambiguacion" in bajo or "disambiguation" in bajo:
        return no("es una página de desambiguación, no un artículo")
    prosa = _prosa(texto)
    if prosa < MIN_PROSA:
        return no(f"no es prosa: solo el {prosa:.0%} de los renglones son frases")
    esperado = "en" if plan["deck"]["key"] == "ingles" else "es"
    if idioma(texto) != esperado:
        return no(f"idioma equivocado: se esperaba {esperado}")
    relevancia = _relevancia(doc, plan)
    if relevancia < MIN_RELEVANCIA:
        return no(f"poco que ver con {', '.join(plan['terminos'])}", relevancia)
    huella = fuentes.huella(doc)
    ya = con.execute("SELECT 1 FROM source_imports WHERE fingerprint=? AND deck_id=?",
                     (huella, plan["deck"]["id"])).fetchone()
    if ya:
        return no("ya lo tienes importado en este mazo")
    if con.execute("SELECT 1 FROM inbox WHERE provider=? AND origin=? AND deck_id=?",
                   (doc["provider"], doc["origin"], plan["deck"]["id"])).fetchone():
        return no("ya está esperando en la bandeja")
    score = round(0.5 * min(1.0, relevancia * 2) + 0.3 * prosa +
                  0.2 * min(1.0, palabras / 1500), 3)
    niveles = len(selector._niveles(plan["deck"]))
    return {"ok": score >= UMBRAL, "score": score, "nivel": nivel_de(texto, niveles),
            "motivo": plan["motivo"] if score >= UMBRAL else f"nota baja: {score}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_filtros.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/cosecha.py tests/test_filtros.py
git commit -m "Cosecha: siete filtros de calidad con motivo legible"
```

---

### Task 7: `bandeja.py` — la cola del visto bueno

**Files:**
- Create: `appstudy/bandeja.py`
- Test: `tests/test_bandeja.py` (ampliar el de la Task 1)

**Interfaces:**
- Consumes: `fuentes.importar`, `db.add_card`, `db.set_card_source`, `ia.generar_desde_texto`
- Produces:
  - `bandeja.guardar(con, doc, plan, veredicto) -> int` (id de la fila)
  - `bandeja.pendientes(con) -> list[sqlite3.Row]`
  - `bandeja.cuantas(con) -> int`
  - `bandeja.aceptar(con, inbox_id, cards=None) -> sqlite3.Row` (el capítulo)
  - `bandeja.descartar(con, inbox_id) -> None`

- [ ] **Step 1: Write the failing test**

```python
import json

from appstudy import bandeja, db, fuentes, selector
from tests.apoyo import BaseTemporal

TEXTO = "La ley de Ohm relaciona tensión, corriente y resistencia. " * 90


class BandejaTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡",
                       "Básico,Intermedio,Avanzado")
        self.con.commit()
        self.plan = selector.plan(self.con)
        self.doc = fuentes.documento("wikipedia_es", "https://es.wikipedia.org/wiki/Ohm",
                                     "Ley de Ohm", text=TEXTO)
        self.veredicto = {"ok": True, "score": 0.9, "nivel": 1, "motivo": "porque fallas ohm"}

    def guardar(self, cards=None):
        return bandeja.guardar(self.con, {**self.doc, "cards": cards or []},
                               self.plan, self.veredicto)

    def test_lo_guardado_aparece_como_pendiente(self):
        self.guardar()
        self.assertEqual(bandeja.cuantas(self.con), 1)
        self.assertEqual(bandeja.pendientes(self.con)[0]["title"], "Ley de Ohm")

    def test_aceptar_crea_el_capitulo_y_las_tarjetas_elegidas(self):
        fila = self.guardar([{"front": "¿Qué dice la ley de Ohm?", "back": "V = I · R"},
                             {"front": "¿En qué se mide la resistencia?", "back": "En ohmios"}])
        capitulo = bandeja.aceptar(self.con, fila, cards=[0])
        self.assertIn("Ley de Ohm", capitulo["title"])
        frentes = [r["front"] for r in self.con.execute("SELECT front FROM cards")]
        self.assertEqual(frentes, ["¿Qué dice la ley de Ohm?"])
        self.assertEqual(bandeja.cuantas(self.con), 0)

    def test_la_tarjeta_creada_sabe_de_que_capitulo_salio(self):
        fila = self.guardar([{"front": "¿Qué dice la ley de Ohm?", "back": "V = I · R"}])
        capitulo = bandeja.aceptar(self.con, fila, cards=[0])
        card_id = self.con.execute("SELECT id FROM cards").fetchone()["id"]
        self.assertEqual(db.source_for_card(self.con, card_id)["chapter_id"], capitulo["id"])

    def test_descartar_lo_saca_de_la_cola_y_no_se_vuelve_a_proponer(self):
        fila = self.guardar()
        bandeja.descartar(self.con, fila)
        self.assertEqual(bandeja.cuantas(self.con), 0)
        estado = self.con.execute("SELECT estado FROM inbox WHERE id=?", (fila,)).fetchone()
        self.assertEqual(estado["estado"], "descartado")

    def test_guardar_dos_veces_el_mismo_origen_no_duplica(self):
        self.guardar()
        self.guardar()
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM inbox").fetchone()["c"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bandeja.py -q`
Expected: FAIL — `ModuleNotFoundError: appstudy.bandeja`

- [ ] **Step 3: Write minimal implementation**

```python
"""La cola de lo que ha llegado solo y espera tu visto bueno.

Nada entra a un mazo sin pasar por aquí. Aceptar reutiliza
`fuentes.importar()`, que ya conserva la identidad y el progreso al reimportar.
"""
from __future__ import annotations

import json
import time

from . import db, fuentes


def guardar(con, doc: dict, plan: dict, veredicto: dict) -> int:
    deck_id = plan["deck"]["id"]
    con.execute("""
        INSERT INTO inbox(provider,origin,deck_id,title,summary,text,author,license,
                          score,motivo,cards,estado,created)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,'pendiente',?)
        ON CONFLICT(provider,origin,deck_id) DO NOTHING""",
        (doc["provider"], doc["origin"], deck_id, doc["title"], doc.get("summary", ""),
         doc.get("text", ""), doc.get("author", ""), doc.get("license", ""),
         veredicto["score"], veredicto["motivo"],
         json.dumps(doc.get("cards", []), ensure_ascii=False), time.time()))
    con.commit()
    return con.execute("SELECT id FROM inbox WHERE provider=? AND origin=? AND deck_id=?",
                       (doc["provider"], doc["origin"], deck_id)).fetchone()["id"]


def pendientes(con) -> list:
    return con.execute("""SELECT i.*, d.name AS deck_name, d.key AS deck_key
                            FROM inbox i JOIN decks d ON d.id = i.deck_id
                           WHERE i.estado = 'pendiente'
                           ORDER BY i.score DESC, i.created DESC""").fetchall()


def cuantas(con) -> int:
    return con.execute("SELECT COUNT(*) c FROM inbox WHERE estado='pendiente'").fetchone()["c"]


def descartar(con, inbox_id: int) -> None:
    """Se marca, no se borra: así no se vuelve a proponer lo mismo mañana."""
    con.execute("UPDATE inbox SET estado='descartado' WHERE id=?", (inbox_id,))
    con.commit()


def aceptar(con, inbox_id: int, cards=None):
    """Crea el capítulo y las tarjetas elegidas. `cards` son índices; None, todas."""
    fila = con.execute("SELECT * FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    if not fila:
        raise fuentes.FuenteError("Ese elemento ya no está en la bandeja")
    deck = con.execute("SELECT * FROM decks WHERE id=?", (fila["deck_id"],)).fetchone()
    item = {"provider": fila["provider"], "origin": fila["origin"], "title": fila["title"],
            "text": fila["text"], "author": fila["author"], "license": fila["license"],
            "retrieved": fila["created"]}
    capitulo = fuentes.importar(con, item, deck, commit=False)
    propuestas = json.loads(fila["cards"] or "[]")
    elegidas = propuestas if cards is None else [propuestas[i] for i in cards
                                                 if 0 <= i < len(propuestas)]
    for t in elegidas:
        cid = db.add_card(con, deck["id"], deck["key"], "card", t["front"], t.get("back", ""),
                          tags=f"fuente-{fila['provider']}", level=capitulo["level"])
        card_id = cid[0] if isinstance(cid, tuple) else cid
        db.set_card_source(con, card_id, {"kind": "chapter", "chapter_uid": capitulo["uid"],
                                          "title": capitulo["title"]})
    con.execute("UPDATE inbox SET estado='aceptado' WHERE id=?", (inbox_id,))
    con.commit()
    return capitulo
```

Comprobar la firma real de `db.add_card` (devuelve id o tupla) y de `db.set_card_source` antes de dar el paso por bueno; ajustar sin cambiar el test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_bandeja.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/bandeja.py tests/test_bandeja.py
git commit -m "Bandeja: aceptar crea capítulo y tarjetas; descartar no se repite"
```

---

### Task 8: `cosecha.cosechar` y `auto_si_toca`

**Files:**
- Modify: `appstudy/cosecha.py`
- Test: `tests/test_cosecha.py`

**Interfaces:**
- Consumes: `selector.plan`, `fuentes.buscar`, `fuentes.previsualizar`, `cosecha.filtrar`, `bandeja.guardar`, `ia.generar_desde_texto`
- Produces:
  - `cosecha.cosechar(con, plan=None, cuantas=1) -> list[int]` (ids de `inbox`)
  - `cosecha.auto_si_toca(con, cada=86400) -> bool`
  - `cosecha.CADA = 86400`

- [ ] **Step 1: Write the failing test**

```python
import time
import unittest

from appstudy import bandeja, cosecha, db, fuentes, ia, selector
from tests.apoyo import BaseTemporal

TEXTO = ("La ley de Ohm relaciona la tensión, la corriente y la resistencia de un "
         "circuito eléctrico sencillo. " * 60)


class CosechaTest(BaseTemporal):
    def setUp(self):
        super().setUp()
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡",
                       "Básico,Intermedio,Avanzado")
        self.con.commit()
        self.buscados = []
        self.parchear()

    def parchear(self, fallan=()):
        def buscar(provider, consulta="", config=None):
            self.buscados.append(provider)
            if provider in fallan:
                raise fuentes.FuenteError("caída simulada")
            return [fuentes.documento(provider, f"https://es.wikipedia.org/wiki/{provider}",
                                      "Ley de Ohm")]

        def previsualizar(item):
            return {**item, "text": TEXTO, "author": "Colaboradores", "license": "CC BY-SA"}

        for nombre, valor in (("buscar", buscar), ("previsualizar", previsualizar)):
            original = getattr(fuentes, nombre)
            setattr(fuentes, nombre, valor)
            self.addCleanup(lambda n=nombre, o=original: setattr(fuentes, n, o))
        # Sin IA: la cosecha debe seguir trayendo la lectura
        original_ia = ia.generar_desde_texto
        ia.generar_desde_texto = lambda *a, **k: (_ for _ in ()).throw(ia.IAError("sin modelo"))
        self.addCleanup(lambda: setattr(ia, "generar_desde_texto", original_ia))

    def test_una_cosecha_deja_algo_en_la_bandeja(self):
        self.assertTrue(cosecha.cosechar(self.con))
        self.assertEqual(bandeja.cuantas(self.con), 1)

    def test_sin_ia_el_capitulo_llega_igual_y_sin_tarjetas(self):
        cosecha.cosechar(self.con)
        fila = bandeja.pendientes(self.con)[0]
        self.assertEqual(fila["cards"], "[]")
        self.assertTrue(fila["text"])

    def test_una_fuente_caida_no_tumba_a_las_demas(self):
        plan = selector.plan(self.con)
        caida = plan["fuentes"][0]["id"]
        self.parchear(fallan={caida})
        self.assertTrue(cosecha.cosechar(self.con))

    def test_auto_si_toca_cosecha_una_vez_al_dia(self):
        self.assertTrue(cosecha.auto_si_toca(self.con))
        self.assertFalse(cosecha.auto_si_toca(self.con))
        db.set_meta(self.con, "cosecha_last", time.time() - cosecha.CADA - 1)
        self.assertTrue(cosecha.auto_si_toca(self.con))

    def test_apagada_en_ajustes_no_cosecha(self):
        db.set_meta(self.con, "cosecha_auto", "0")
        self.assertFalse(cosecha.auto_si_toca(self.con))

    def test_un_fallo_se_anota_y_no_se_propaga(self):
        def revienta(*a, **k):
            raise fuentes.FuenteError("sin conexión")
        fuentes.buscar = revienta
        self.assertFalse(cosecha.auto_si_toca(self.con))
        self.assertIn("conexión", db.get_meta(self.con, "cosecha_error", ""))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cosecha.py -q`
Expected: FAIL — `AttributeError: module 'appstudy.cosecha' has no attribute 'cosechar'`

- [ ] **Step 3: Write minimal implementation**

Añadir al final de `appstudy/cosecha.py`:

```python
CADA = 86400
POR_RACION = 1
TARJETAS_POR_LECTURA = 6


def _tarjetas(con, doc: dict) -> list:
    """Tarjetas de la IA local, validadas contra el texto de origen.

    Si el modelo no está, no pasa nada: el capítulo se guarda igual y la
    bandeja ofrece generarlas más tarde.
    """
    from . import ia
    cfg = ia.config(con)
    if not cfg.get("activa", True):
        return []
    try:
        propuestas = ia.generar_desde_texto(cfg, doc["text"][:6000], doc["title"],
                                            TARJETAS_POR_LECTURA)
    except Exception:                    # IAError, red, modelo ausente: da igual
        return []
    cuerpo = fuentes.clave(doc["text"])
    ya = {fuentes.clave(r["front"]) for r in
          con.execute("SELECT front FROM cards")}
    salida = []
    for t in propuestas:
        # Contra las invenciones del modelo: la respuesta tiene que estar en el texto
        pistas = [p for p in fuentes.clave(t.get("back", "")).split() if len(p) > 4]
        if pistas and sum(p in cuerpo for p in pistas) / len(pistas) < 0.5:
            continue
        if fuentes.clave(t["front"]) in ya:
            continue
        ya.add(fuentes.clave(t["front"]))
        salida.append({"front": t["front"], "back": t.get("back", "")})
    return salida


def cosechar(con, plan: dict | None = None, cuantas: int = POR_RACION) -> list:
    """Ejecuta el plan del día y deja en la bandeja lo que pase los filtros."""
    from . import bandeja
    plan = plan or selector.plan(con)
    if not plan:
        return []
    consulta = " ".join(plan["terminos"])
    guardados, rechazos = [], []
    for f in plan["fuentes"]:
        if len(guardados) >= cuantas:
            break
        try:
            candidatos = fuentes.buscar(f["id"], consulta)
        except fuentes.FuenteError as e:
            rechazos.append(f"{f['id']}: {e}")
            continue                       # una fuente caída no tumba a las demás
        for candidato in candidatos[:5]:
            if len(guardados) >= cuantas:
                break
            try:
                doc = fuentes.previsualizar(candidato)
            except fuentes.FuenteError as e:
                rechazos.append(f"{candidato['origin']}: {e}")
                continue
            veredicto = filtrar(con, doc, plan)
            if not veredicto["ok"]:
                rechazos.append(f"{doc['title']}: {veredicto['motivo']}")
                continue
            doc["cards"] = _tarjetas(con, doc)
            guardados.append(bandeja.guardar(con, doc, plan, veredicto))
    db.set_meta(con, "cosecha_rechazos", json.dumps(rechazos[:40], ensure_ascii=False))
    return guardados


def auto_si_toca(con, cada: float = CADA) -> bool:
    """Una ración al día, al abrir. Calcado de `respaldo.auto_si_toca`.

    Si falla no se dice nada por pantalla: no poder descargar no debe impedirte
    estudiar. El motivo queda en `meta` y se ve en Ajustes.
    """
    if str(db.get_meta(con, "cosecha_auto", "1")) in ("0", "False"):
        return False
    try:
        ultimo = float(db.get_meta(con, "cosecha_last", 0) or 0)
    except (TypeError, ValueError):
        ultimo = 0
    if time.time() - ultimo < cada:
        return False
    try:
        salida = bool(cosechar(con))
        db.set_meta(con, "cosecha_last", time.time())
        db.set_meta(con, "cosecha_error", "")
        return salida
    except Exception as e:
        db.set_meta(con, "cosecha_error", str(e))
        return False
```

Añadir `import json` arriba del módulo.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cosecha.py tests/test_filtros.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/cosecha.py tests/test_cosecha.py
git commit -m "Cosecha: una ración diaria en segundo plano, callada si falla"
```

---

### Task 9: Engancharlo al arranque

**Files:**
- Modify: `appstudy/app.py` (`do_startup`, línea ~82, junto a `respaldo.auto_si_toca`)
- Test: `tests/test_cosecha.py` (ampliar)

**Interfaces:**
- Consumes: `cosecha.auto_si_toca` (Task 8)
- Produces: `App.cosechar_en_silencio()`

- [ ] **Step 1: Write the failing test**

```python
    def test_el_trabajo_de_arranque_usa_su_propia_conexion(self):
        """Una conexión de SQLite pertenece a su hilo: el trabajo abre la suya."""
        import inspect
        from appstudy import app
        fuente = inspect.getsource(app.App.cosechar_en_silencio)
        self.assertIn("db.connect()", fuente)
        self.assertIn("largo=True", fuente)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cosecha.py -q`
Expected: FAIL — `AttributeError: type object 'App' has no attribute 'cosechar_en_silencio'`

- [ ] **Step 3: Write minimal implementation**

En `appstudy/app.py`, importar `cosecha` y `bandeja` arriba, y añadir el método junto a `sincronizar_nube_en_silencio`:

```python
    def cosechar_en_silencio(self):
        """Una ración de contenido nuevo al día, al abrir. Nunca estorba.

        Si no hay red o la fuente falla, se anota en `meta` y se ve en Ajustes:
        un aviso por cada arranque sin internet sería insufrible.
        """
        def trabajo():
            otra = db.connect()          # una conexión de SQLite es de su hilo
            try:
                return cosecha.auto_si_toca(otra)
            finally:
                otra.close()

        def listo(hubo):
            if hubo and self.main_window:
                self.main_window.refresh()

        util.hilo(trabajo, listo, lambda e: None, largo=True)
```

Y en `do_startup`, justo después del bloque de `respaldo.auto_si_toca`:

```python
        # Igual que el respaldo: una vez al día, al abrir, y en su propio hilo
        # para no retrasar el arranque ni un milisegundo.
        self.cosechar_en_silencio()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -q` → PASS (suite entera)

- [ ] **Step 5: Commit**

```bash
git add appstudy/app.py tests/test_cosecha.py
git commit -m "Arranque: la cosecha diaria se lanza en su hilo al abrir"
```

---

### Task 10: La bandeja en la ventana principal y en Ajustes

**Files:**
- Modify: `appstudy/main_window.py` (una página nueva y su contador)
- Modify: `appstudy/fuentes_window.py` (interruptor, último intento, rechazos)
- Test: `tests/test_bandeja_ui.py`

**Interfaces:**
- Consumes: `bandeja.pendientes`, `bandeja.cuantas`, `bandeja.aceptar`, `bandeja.descartar`, `cosecha.cosechar`

- [ ] **Step 1: Write the failing test**

Seguir el patrón de `tests/test_fuentes_ui.py`, que ya construye widgets sin abrir ventana:

```python
from appstudy import bandeja, db, fuentes, selector
from tests.apoyo import BaseTemporal


class BandejaUITest(BaseTemporal):
    def test_la_pagina_lista_lo_pendiente_y_acepta(self):
        from appstudy.bandeja_ui import PaginaBandeja
        db.upsert_deck(self.con, "electricidad", "Electricidad", "⚡", "Básico")
        self.con.commit()
        plan = selector.plan(self.con)
        doc = fuentes.documento("wikipedia_es", "https://es.wikipedia.org/wiki/Ohm",
                                "Ley de Ohm", text="La ley de Ohm. " * 300)
        doc["cards"] = [{"front": "¿Ohm?", "back": "V = I · R"}]
        bandeja.guardar(self.con, doc, plan, {"ok": True, "score": 1.0, "nivel": 1,
                                              "motivo": "porque fallas ohm"})
        pagina = PaginaBandeja(self.con)
        self.assertEqual(len(pagina.filas), 1)
        self.assertIn("porque fallas ohm", pagina.filas[0].get_subtitle())
        pagina.filas[0].aceptar()
        self.assertEqual(bandeja.cuantas(self.con), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bandeja_ui.py -q`
Expected: FAIL — `ModuleNotFoundError: appstudy.bandeja_ui`

- [ ] **Step 3: Write minimal implementation**

Crear `appstudy/bandeja_ui.py` con `PaginaBandeja(Gtk.Box)`: un `Adw.PreferencesGroup` por elemento con título, fuente, licencia, `motivo` como subtítulo, el texto en un `Gtk.Expander`, una `Gtk.CheckButton` por tarjeta propuesta, y los botones **Aceptar**, **Descartar** y **Buscar ahora** (este último llama a `cosecha.cosechar` con `util.hilo`). Exponer `self.filas` con un método `aceptar()` por fila, para que la prueba no dependa de pulsar botones.

En `main_window.py`, añadir la página al `Adw.ViewStack` que ya existe con una insignia que muestre `bandeja.cuantas(con)` cuando sea mayor que cero, y refrescarla desde `refresh()`.

En `fuentes_window.py`, añadir un `Adw.SwitchRow` sobre `meta["cosecha_auto"]`, una fila con la fecha de `meta["cosecha_last"]`, otra con `meta["cosecha_error"]` si no está vacío, y un `Gtk.Expander` con lo guardado en `meta["cosecha_rechazos"]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/ -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add appstudy/bandeja_ui.py appstudy/main_window.py appstudy/fuentes_window.py tests/test_bandeja_ui.py
git commit -m "Bandeja: pantalla de novedades y controles en Ajustes › Fuentes"
```

---

### Task 11: Documentación

**Files:**
- Modify: `README.md`
- Modify: `docs/extensiones.md`

- [ ] **Step 1: Escribir la sección del README**

Bajo la tabla de mazos, una sección «Contenido que llega solo» que explique: una ración al día al abrir, la bandeja donde se aprueba, la lista de fuentes por mazo, la distinción entre abierta y solo-enlace, y cómo apagarlo en Ajustes › Fuentes. Decir también lo que no hace: no traduce, no descarga PDF sola, y maquinaria amarilla se alimenta poco porque casi no hay fuentes abiertas.

- [ ] **Step 2: Añadir las fuentes nuevas a `docs/extensiones.md`**

Cada una con su identificador, su licencia y sus permisos, siguiendo la tabla que ya está ahí.

- [ ] **Step 3: Verificar la suite entera**

Run: `python3 -m pytest tests/ -q`

- [ ] **Step 4: Commit**

```bash
git add README.md docs/extensiones.md
git commit -m "Documentar la autoalimentación de contenido y sus fuentes"
```
