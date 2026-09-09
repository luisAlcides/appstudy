"""Qué fuentes existen ahí fuera y a qué mazo sirve cada una.

Datos, no comportamiento: aquí no se toca la red ni la base. Así el resto del
subsistema se prueba sin salir a internet, y añadir una fuente es añadir una
fila.

`licencia` decide qué se puede importar entero. `abierta` es dominio público o
licencia libre con atribución —que es justo lo que `fuentes.importar()` ya
añade al pie del capítulo—; `solo-enlace` es todo lo demás, y de eso se guarda
título, resumen y enlace, nada más. La distinción importa porque la aplicación
sincroniza y publica mazos: el texto ajeno puede salir de este equipo.

Todas las direcciones se comprobaron con peticiones reales el 2026-09-09.
"""
from __future__ import annotations

TODOS: list = []       # una lista de niveles vacía significa «todos los niveles»

FUENTES = [
    # ------------------------------------------------------------ buscadores
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
    # ArchWiki y Gentoo montan la API en la raíz, sin el /w de Wikimedia
    {"id": "archwiki", "nombre": "ArchWiki", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "en", "hosts": {"wiki.archlinux.org"},
     "base": "https://wiki.archlinux.org", "buscar": "mediawiki_corto",
     "mazos": {"linux": TODOS}},
    {"id": "gentoo", "nombre": "Gentoo Wiki", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "en", "hosts": {"wiki.gentoo.org"},
     "base": "https://wiki.gentoo.org", "buscar": "mediawiki_corto",
     "mazos": {"linux": TODOS}},
    {"id": "arxiv", "nombre": "arXiv", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "en",
     "hosts": {"export.arxiv.org", "arxiv.org"},
     "base": "https://export.arxiv.org", "buscar": "arxiv",
     "mazos": {"ia": ["Avanzado"], "datos": ["Avanzado"]}},
    {"id": "mdn", "nombre": "MDN Web Docs", "tipo": "buscador",
     "licencia": "solo-enlace", "idioma": "es", "hosts": {"developer.mozilla.org"},
     "base": "https://developer.mozilla.org", "buscar": "mdn",
     "mazos": {"python": TODOS}},
    {"id": "gutenberg", "nombre": "Project Gutenberg", "tipo": "buscador",
     "licencia": "abierta", "idioma": "en",
     "hosts": {"gutendex.com", "www.gutenberg.org"},
     "base": "https://gutendex.com", "buscar": "gutendex",
     "mazos": {"ingles": ["B2", "C1"]}},
    # --------------------------------------------------------------- índices
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
    # -------------------------------------------------------------- catálogos
    {"id": "openstax", "nombre": "OpenStax", "tipo": "catalogo",
     "licencia": "abierta", "idioma": "es",
     "hosts": {"openstax.org", "assets.openstax.org"},
     "base": "https://openstax.org", "buscar": "catalogo",
     "mazos": {"matematicas": TODOS, "datos": TODOS, "electricidad": TODOS}},
    {"id": "mit", "nombre": "MIT OpenCourseWare", "tipo": "catalogo",
     "licencia": "abierta", "idioma": "en",
     "hosts": {"ocw.mit.edu", "live.ocw.mit.edu"},
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
    """Si de esta fuente se puede guardar el texto entero, no solo el enlace."""
    return ident in _POR_ID and _POR_ID[ident]["licencia"] == "abierta"


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
